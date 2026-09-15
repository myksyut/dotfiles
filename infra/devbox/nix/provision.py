"""Explicit fresh-store bootstrap from the pinned official Nix binary archive.

No installer, user profile, migration, recursive chown or automatic repair.
Run only as root under bootstrap/admission locks. Failed stores are preserved.
"""

import contextlib
import grp
import hashlib
import os
import posixpath
import pwd
import secrets
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

# Deployed at /opt/devbox/nix, with its parent on the script import path.
# Package resolution is covered by the native import and boundary unit tests.
from .boundary import (  # pyright: ignore[reportMissingImports]
    atomic_json,
    directory,
    opened,
)

VERSION = "2.35.2"
SEED_SHA256 = "0c3960a9792331a22081c3c7a5d8465db9b17c50b3acdf18587fa4c6f2cb1158"
RUNTIME = "/nix/store/irfrbndi76zhkvqsfhmsn4a99iafck29-nix-2.35.2"
CACERT = "/nix/store/zdl7dn1gmi1cxdw5a8hw6xsf4cz0rjmg-nss-cacert-3.123"
BUILD_GID = 30000
BUILD_UIDS = [30001, 30002, 30003, 30004]
STATE = Path("/data/meta/nix-state.json")
CONFIG_PATH = Path("/etc/nix/nix.conf")
ARCHIVE = Path("/opt/artifacts/nix.tar.xz")
CONFIG = """experimental-features = nix-command flakes
trusted-users = root
allowed-users = miyakishota
build-users-group = nixbld
auto-allocate-uids = false
sandbox = true
sandbox-fallback = false
require-sigs = true
builders =
max-jobs = 1
cores = 2
"""
CONFIG_SHA256 = hashlib.sha256(CONFIG.encode()).hexdigest()


def root_environment(*, daemon=True):
    return {
        "HOME": "/root",
        "USER": "root",
        "LOGNAME": "root",
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "NIX_REMOTE": "daemon" if daemon else "local",
        "NIX_CONF_DIR": "/etc/nix",
        "NIX_USER_CONF_FILES": "/dev/null",
        "NIX_SSL_CERT_FILE": CACERT + "/etc/ssl/certs/ca-bundle.crt",
    }


def validate_accounts():
    users = pwd.getpwall()
    groups = grp.getgrall()
    for uid in [10001, *BUILD_UIDS]:
        if sum(user.pw_uid == uid for user in users) != 1:
            raise ValueError("Missing or aliased developer/build UID")
    for name, gid in (("miyakishota", 10001), ("nixbld", BUILD_GID)):
        matching = [group for group in groups if group.gr_gid == gid]
        if len(matching) != 1 or matching[0].gr_name != name:
            raise ValueError("Missing or aliased developer/build GID")
    developer = pwd.getpwnam("miyakishota")
    group = grp.getgrnam("nixbld")
    if (
        developer.pw_uid != 10001
        or developer.pw_gid != 10001
        or group.gr_gid != BUILD_GID
        or os.getgrouplist("miyakishota", 10001) != [10001]
    ):
        raise ValueError("Unexpected developer/build group identity or membership")
    expected = {f"nixbld{i}" for i in range(1, 5)}
    if set(group.gr_mem) != expected:
        raise ValueError("Unexpected build group members")
    for index, uid in enumerate(BUILD_UIDS, 1):
        user = pwd.getpwnam(f"nixbld{index}")
        if (
            user.pw_uid != uid
            or user.pw_gid != BUILD_GID
            or user.pw_shell not in ("/usr/sbin/nologin", "/bin/false")
            or pwd.getpwuid(uid).pw_name != user.pw_name
            or os.getgrouplist(user.pw_name, BUILD_GID) != [BUILD_GID]
        ):
            raise ValueError("Unexpected build user identity, shell or groups")
    if any(u.pw_gid == BUILD_GID and u.pw_name not in expected for u in pwd.getpwall()):
        raise ValueError("Unexpected primary member of build group")


def validate_config():
    with opened(CONFIG_PATH, private=False) as stream:
        if stream.read(16385) != CONFIG.encode():
            raise ValueError("Nix configuration differs from fixed policy")


def verify_mount_identity(text, store_info, source_info):
    records = {"/nix": [], "/data": []}
    for line in text.splitlines():
        before, separator, after = line.partition(" - ")
        fields = before.split()
        filesystem = after.split()
        if not separator or len(fields) < 6 or len(filesystem) < 3:
            raise ValueError("Malformed mount inventory")
        if fields[4] in records:
            records[fields[4]].append((fields, filesystem))
    expected_device = f"{os.major(store_info.st_dev)}:{os.minor(store_info.st_dev)}"
    if (store_info.st_dev, store_info.st_ino) != (
        source_info.st_dev,
        source_info.st_ino,
    ):
        raise ValueError("Nix mount is not the intended /data/nix directory")
    for entries in records.values():
        if len(entries) != 1:
            raise ValueError("Missing or overlapping Nix/data mounts")
        fields, filesystem = entries[0]
        if (
            fields[2] != expected_device
            or "rw" not in fields[5].split(",")
            or filesystem[0] in ("tmpfs", "ramfs", "proc", "sysfs", "overlay")
        ):
            raise ValueError("Unexpected Nix/data mount device or persistence")


def validate_mounts():
    store, source = Path("/nix"), Path("/data/nix")
    directory(store)
    directory(source)
    with Path("/proc/self/mountinfo").open() as stream:
        text = stream.read(1024 * 1024 + 1)
    if len(text) > 1024 * 1024:
        raise ValueError("Mount inventory exceeds limit")
    verify_mount_identity(text, store.stat(), source.stat())


def require_fresh(store, state, *, owner=0):
    directory(store, owner=owner)
    info = store.lstat()
    if info.st_uid != owner or stat.S_IMODE(info.st_mode) != 0o755:
        raise ValueError("Fresh Nix mount must be root-owned mode 755")
    if state.exists() or state.is_symlink() or any(store.iterdir()):
        raise ValueError("Nix initialization already attempted or store is not empty")


def _link_target(name, link):
    if link.startswith("/"):
        if not link.startswith("/nix/store/"):
            raise ValueError("Archive link escapes Nix store")
        target = link[len("/nix/") :]
    else:
        target = posixpath.join(str(name.parent), link)
    target = PurePosixPath(posixpath.normpath(target))
    if len(target.parts) < 2 or target.parts[0] != "store" or ".." in target.parts:
        raise ValueError("Archive link escapes Nix store")
    return target


def _resolve_link(name, members):
    target = name
    for _ in range(40):
        changed = False
        for count in range(1, len(target.parts) + 1):
            prefix = PurePosixPath(*target.parts[:count])
            item = members.get(prefix)
            if item is not None and item.issym():
                target = _link_target(prefix, item.linkname).joinpath(
                    *target.parts[count:]
                )
                changed = True
                break
        if not changed:
            if target not in members:
                raise ValueError("Archive link target missing from seed closure")
            return
    raise ValueError("Archive link cycle or excessive indirection")


def _members(archive):
    members = {}
    top = None
    total_bytes = 0
    for count, item in enumerate(archive, 1):
        total_bytes += item.size if item.isfile() else 0
        if count > 10000 or total_bytes > 1024 * 1024 * 1024:
            raise ValueError("Seed archive exceeds member/expanded-size budget")
        raw = PurePosixPath(item.name)
        if raw.is_absolute() or ".." in raw.parts or not raw.parts:
            raise ValueError("Archive path traversal")
        top = top or raw.parts[0]
        if raw.parts[0] != top:
            raise ValueError("Multiple archive roots")
        name = PurePosixPath(*raw.parts[1:])
        if name in members or not (item.isdir() or item.isfile() or item.issym()):
            raise ValueError("Duplicate archive path or unsupported member type")
        if item.mode & 0o7000 or item.size > 512 * 1024 * 1024:
            raise ValueError("Unsafe archive mode or excessive member size")
        members[name] = item
    for name, item in members.items():
        if any(
            parent in members and not members[parent].isdir() for parent in name.parents
        ):
            raise ValueError("Archive member has a non-directory parent")
        if item.issym():
            if name.parts[0] != "store":
                raise ValueError("Link outside seed closure")
            _resolve_link(name, members)
    return members


@contextlib.contextmanager
def verified_archive(path, digest, *, owner=0):
    with opened(path, owner=owner, private=False) as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError("Seed digest mismatch")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:xz") as archive:
            members = _members(archive)
            yield archive, members


def inspect_archive(path, digest=SEED_SHA256, *, owner=0):
    with verified_archive(path, digest, owner=owner) as (_, members):
        return tuple(str(name) for name in members)


def _copy_seed(archive, members, store):
    # Parents before children, symlinks last. Never extract through a link.
    selected = [
        (name, item)
        for name, item in members.items()
        if name.parts and name.parts[0] == "store" and len(name.parts) > 1
    ]
    selected.sort(key=lambda pair: (pair[1].issym(), len(pair[0].parts), str(pair[0])))
    for name, item in selected:
        destination = store.joinpath(*name.parts)
        if item.isdir():
            destination.mkdir(mode=0o755)
        elif item.issym():
            destination.symlink_to(item.linkname)
        else:
            source = archive.extractfile(item)
            if source is None:
                raise ValueError("Archive file body absent")
            fd = os.open(
                destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with source, os.fdopen(fd, "wb") as output:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fchmod(output.fileno(), 0o555 if item.mode & 0o111 else 0o444)
    # Only newly created seed directories. Never change ownership of old content.
    for name, item in reversed(selected):
        if item.isdir():
            store.joinpath(*name.parts).chmod(0o555)


def _management_directories(store):
    for relative in (
        "var",
        "var/log",
        "var/log/nix",
        "var/log/nix/drvs",
        "var/nix",
        "var/nix/db",
        "var/nix/gcroots",
        "var/nix/gcroots/per-user",
        "var/nix/profiles",
        "var/nix/profiles/per-user",
        "var/nix/temproots",
        "var/nix/userpool",
        "var/nix/daemon-socket",
    ):
        target = store / relative
        target.mkdir(mode=0o755)
        target.chmod(0o755)  # bootstrap uses umask 077; clients need traversal.


def provision(*, archive_path=ARCHIVE, state_path=STATE, store=Path("/nix")):
    if os.getuid() != 0 or store != Path("/nix"):
        raise ValueError("Provision requires root and the dedicated /nix mount")
    validate_mounts()
    validate_accounts()
    validate_config()
    require_fresh(store, state_path)
    state = {
        "schema": 2,
        "nix_mode": "multi-user",
        "phase": "preparing",
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "seed_digest": SEED_SHA256,
        "config_digest": CONFIG_SHA256,
        "runtime_path": RUNTIME,
        "build_uids": BUILD_UIDS,
        "store_id": secrets.token_hex(16),
    }
    state["generation_digest"] = hashlib.sha256(
        (state["store_id"] + SEED_SHA256 + CONFIG_SHA256).encode()
    ).hexdigest()
    atomic_json(state_path, state)
    try:
        with verified_archive(archive_path, SEED_SHA256) as (archive, members):
            required = (
                PurePosixPath(".reginfo"),
                PurePosixPath("store") / Path(RUNTIME).name,
                PurePosixPath("store") / Path(CACERT).name,
            )
            if (
                any(name not in members for name in required)
                or not members[required[0]].isfile()
            ):
                raise ValueError(
                    "Seed is missing registration/runtime/certificate closure"
                )
            (store / "store").mkdir(mode=0o755)
            os.chown(store / "store", 0, BUILD_GID)
            (store / "store").chmod(0o1775)
            _copy_seed(archive, members, store)
            _management_directories(store)
            registration = archive.extractfile(members[required[0]])
            if registration is None:
                raise ValueError("Missing registration body")
            with registration:
                body = registration.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise ValueError("Registration exceeds size limit")
                result = subprocess.run(
                    [RUNTIME + "/bin/nix-store", "--load-db"],
                    input=body,
                    env=root_environment(daemon=False),
                    capture_output=True,
                    timeout=120,
                )
            if result.returncode:
                raise ValueError("Seed registration failed; inspect preserved store")
        for label, target in (("devbox-runtime", RUNTIME), ("devbox-cacert", CACERT)):
            (store / "var/nix/gcroots" / label).symlink_to(target)
        os.sync()
        state["phase"] = "prepared"
        atomic_json(state_path, state)
        return state
    except (
        OSError,
        ValueError,
        KeyError,
        tarfile.TarError,
        subprocess.SubprocessError,
    ):
        state["phase"] = "failed"
        with contextlib.suppress(OSError, ValueError):
            atomic_json(state_path, state)
        raise
