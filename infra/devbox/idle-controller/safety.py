"""Shared registration/stop fence. Installed root-owned under /opt/devbox.
This protects cooperative tooling, not malicious code running as the same UID.
Orca, schedulers and direct CLI entry still require a validated site drain hook.
"""

import contextlib
import fcntl
import json
import os
import secrets
import stat
from pathlib import Path

ADMISSION = Path("/run/devbox-admission")
RECOVERY = Path("/data/meta/shutdown-state.json")
DEVELOPER_HOME = Path("/home/miyakishota")
DEVELOPER_UID = 10001
ROOT_UID = 0


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def validate_stat(info, owners):
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid not in owners
        or info.st_mode & 0o022
        or info.st_nlink != 1
    ):
        raise ValueError(
            "Unsafe control/registry file type, ownership, permissions or link count"
        )


def validate_directories(path, owners):
    for parent in [path, *path.parents]:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in owners
            or info.st_mode & 0o022
        ):
            # OS temp ancestors are used only by isolated unprivileged tests.
            if (
                parent in (Path("/tmp"), Path("/private/tmp"))
                and info.st_mode & stat.S_ISVTX
            ):
                continue
            raise ValueError("Unsafe registry/control directory")


@contextlib.contextmanager
def checked_file(path, *, owners, writable=False, create=False):
    flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK
    if create:
        flags |= os.O_CREAT
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "r+" if writable else "r") as stream:
            validate_stat(os.fstat(stream.fileno()), owners)
            yield stream
    except OSError as exc:
        raise ValueError(
            f"Cannot safely access {path.name}; operation blocked"
        ) from exc


def load_object(stream):
    try:
        stream.seek(0)
        data = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError("Invalid/unknown control JSON; operation blocked") from exc
    if not isinstance(data, dict):
        raise ValueError("Control JSON must be an object")
    return data


def save_locked(stream, value):
    stream.seek(0)
    json.dump(value, stream)
    stream.truncate()
    stream.flush()
    os.fsync(stream.fileno())


@contextlib.contextmanager
def admission(*, exclusive=False, require_open=True):
    # A missing file or stale boot is NEVER treated as permission to start work.
    with checked_file(ADMISSION, owners={ROOT_UID}, writable=exclusive) as stream:
        fcntl.flock(
            stream, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
        )
        value = load_object(stream)
        if value.get("boot_id") != boot_id() or value.get("state") not in (
            "open",
            "draining",
        ):
            raise ValueError("Unknown/stale admission fence")
        if require_open and value["state"] != "open":
            raise ValueError(
                "Devbox is draining; new work and registry changes are refused"
            )
        yield stream


def durable_state(path, value):
    # Fixed root-owned metadata path; fail closed on symlinks/non-regular files.
    validate_directories(path.parent, {0, ROOT_UID})
    with checked_file(path, owners={ROOT_UID}, writable=True, create=True) as stream:
        save_locked(stream, value)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def initialize_admission():
    if os.getuid() != ROOT_UID:
        raise ValueError("Only the entrypoint may initialize admission")
    with checked_file(
        ADMISSION, owners={ROOT_UID}, writable=True, create=True
    ) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save_locked(
            stream,
            {
                "state": "draining" if recovery_required() else "open",
                "boot_id": boot_id(),
            },
        )
        os.fchmod(stream.fileno(), 0o644)


def begin_drain():
    drain_id = secrets.token_hex(16)
    with admission(exclusive=True) as stream:
        # Persist recovery intent BEFORE any hook can stop a service.
        durable_state(
            RECOVERY, {"phase": "draining", "boot_id": boot_id(), "drain_id": drain_id}
        )
        save_locked(
            stream, {"state": "draining", "boot_id": boot_id(), "drain_id": drain_id}
        )
    return drain_id


def recovery_required():
    if not RECOVERY.exists() and not RECOVERY.is_symlink():
        return False
    try:
        with checked_file(RECOVERY, owners={ROOT_UID}) as stream:
            value = load_object(stream)
        return value.get("phase") != "stopped"
    except (OSError, ValueError):
        return True


def validate_registry(data):
    if (
        not isinstance(data, dict)
        or data.get("schema") != 1
        or not isinstance(data.get("records"), dict)
    ):
        raise ValueError("Unknown registry schema; stop blocked")
    for key, item in data["records"].items():
        if (
            not isinstance(key, str)
            or not isinstance(item, dict)
            or item.get("kind") not in ("hold", "job")
            or type(item.get("owner")) is not int
            or item.get("state")
            not in ("held", "starting", "running", "completed-unverified", "released")
        ):
            raise ValueError("Malformed registry record; stop blocked")
    return data


@contextlib.contextmanager
def registry_file(home, *, owner, write=False):
    root = Path(home) / ".local/state/devbox"
    owners = {0, ROOT_UID, owner}
    validate_directories(root, owners)
    if write:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "registry.json"
    if not path.exists() and not path.is_symlink() and not write:
        yield {"schema": 1, "records": {}}
        return
    with checked_file(
        root / "registry.lock", owners=owners, writable=write, create=write
    ) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if write else (fcntl.LOCK_SH | fcntl.LOCK_NB))
        if path.exists() or path.is_symlink():
            with checked_file(path, owners=owners) as stream:
                data = validate_registry(load_object(stream))
        else:
            data = {"schema": 1, "records": {}}
        yield data
        if write:
            validate_registry(data)
            # Same lock is used by the stop reader. Keep complete JSON across failures.
            import tempfile

            fd, name = tempfile.mkstemp(prefix="registry.", suffix=".tmp", dir=root)
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)


def check_registry():
    with registry_file(DEVELOPER_HOME, owner=DEVELOPER_UID) as data:
        if any(item["state"] != "released" for item in data["records"].values()):
            raise ValueError("Hold/job remains; inspect and release explicitly")


def proc_info(pid, proc=Path("/proc")):
    try:
        fields = (proc / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return {"start": fields[19], "pgid": int(fields[2]), "sid": int(fields[3])}
    except (ValueError, IndexError) as exc:
        raise ValueError("Malformed process identity; operation blocked") from exc


def verify_job_absent(item, proc=Path("/proc")):
    if item.get("state") != "completed-unverified":
        raise ValueError(
            "Job did not complete normally; operator reconciliation required"
        )
    if item.get("boot_id") != boot_id():
        raise ValueError("Old boot record requires separate operator reconciliation")
    if not item.get("child_start") or any(
        type(item.get(key)) is not int or item[key] <= 0
        for key in ("child_pid", "pgid", "sid")
    ):
        raise ValueError("Missing child identity; operator reconciliation required")
    pid = item["child_pid"]
    try:
        current = proc_info(pid, proc)
    except FileNotFoundError:
        current = None
    if current:
        if current["start"] != item["child_start"]:
            raise ValueError("PID reused; cannot validate this job")
        raise ValueError("Direct child is still present")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            info = proc_info(int(entry.name), proc)
        except FileNotFoundError:
            continue
        if info["pgid"] == item.get("pgid") or info["sid"] == item.get("sid"):
            raise ValueError("Job process group/session still has members")
    # Detached setsid descendants can escape this scope. Explicit human confirmation
    # is STILL required; this is not a replacement for cgroup-based containment.


if __name__ == "__main__":
    initialize_admission()
