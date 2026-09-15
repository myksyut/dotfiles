"""Validate the prepared store before any root daemon/client execution."""

import hashlib
import os
import re
import stat
from pathlib import Path

from .boundary import directory, read_json  # pyright: ignore[reportMissingImports]
from .provision import (  # pyright: ignore[reportMissingImports]
    BUILD_GID,
    BUILD_UIDS,
    CACERT,
    CONFIG_SHA256,
    RUNTIME,
    SEED_SHA256,
    STATE,
    validate_accounts,
    validate_config,
    validate_mounts,
)


def validate_state(value):
    expected = {
        "schema": 2,
        "nix_mode": "multi-user",
        "phase": "prepared",
        "seed_digest": SEED_SHA256,
        "config_digest": CONFIG_SHA256,
        "runtime_path": RUNTIME,
        "build_uids": BUILD_UIDS,
    }
    if (
        not isinstance(value, dict)
        or type(value.get("schema")) is not int
        or any(value.get(key) != val for key, val in expected.items())
    ):
        raise ValueError("Nix store is not a compatible prepared generation")
    if any(type(uid) is not int for uid in value["build_uids"]):
        raise ValueError("Invalid Nix build UID record")
    store_id = value.get("store_id")
    if not isinstance(store_id, str) or re.fullmatch("[0-9a-f]{32}", store_id) is None:
        raise ValueError("Missing Nix store provenance")
    digest = hashlib.sha256(
        (store_id + SEED_SHA256 + CONFIG_SHA256).encode()
    ).hexdigest()
    if value.get("generation_digest") != digest:
        raise ValueError("Nix generation digest mismatch")
    return value


def seed_path(path):
    """Check each immutable component before following an in-store symlink."""
    base = Path("/nix/store")
    current = Path(path)
    for _ in range(40):
        if not current.is_relative_to(base) or ".." in current.parts:
            raise ValueError("Runtime link escapes the Nix store")
        changed = False
        parts = current.relative_to(base).parts
        for index in range(1, len(parts) + 1):
            component = base.joinpath(*parts[:index])
            info = component.lstat()
            if info.st_uid != 0:
                raise ValueError("Runtime component is not root-owned")
            if stat.S_ISLNK(info.st_mode):
                target = component.readlink()
                target = target if target.is_absolute() else component.parent / target
                current = Path(os.path.normpath(target)).joinpath(*parts[index:])
                changed = True
                break
            if info.st_mode & 0o022 or not (
                stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
            ):
                raise ValueError("Unsafe runtime component mode or type")
        if not changed:
            return current
    raise ValueError("Runtime link cycle")


def prepared_state():
    state = validate_state(read_json(STATE))
    validate_mounts()
    validate_accounts()
    validate_config()
    store = Path("/nix/store").lstat()
    if (
        not stat.S_ISDIR(store.st_mode)
        or store.st_uid != 0
        or store.st_gid != BUILD_GID
        or stat.S_IMODE(store.st_mode) != 0o1775
    ):
        raise ValueError("Invalid Nix store ownership or sticky-group mode")
    for relative in (
        "var/nix/db",
        "var/nix/gcroots",
        "var/nix/profiles",
        "var/nix/daemon-socket",
    ):
        directory(Path("/nix") / relative)
    for label, target in (("devbox-runtime", RUNTIME), ("devbox-cacert", CACERT)):
        link = Path("/nix/var/nix/gcroots") / label
        info = link.lstat()
        if (
            not stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or str(link.readlink()) != target
        ):
            raise ValueError("Missing or replaced root runtime GC root")
    for binary in ("nix", "nix-store", "nix-daemon"):
        target = seed_path(Path(RUNTIME) / "bin" / binary)
        info = target.stat()
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
            raise ValueError("Invalid fixed Nix executable")
    if not seed_path(Path(CACERT) / "etc/ssl/certs/ca-bundle.crt").is_file():
        raise ValueError("Missing fixed Nix CA bundle")
    return state
