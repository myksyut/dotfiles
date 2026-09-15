"""Bounded, root-owned control IO. Test owners are explicit arguments, never env."""

import contextlib
import fcntl
import json
import math
import os
import secrets
import stat
from pathlib import Path

LIMIT = 16384


def directory(path, *, owner=0):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Control path must be absolute without traversal")
    for parent in reversed((path, *path.parents)):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Directory symlinks are not allowed")
        if (
            parent in (Path("/tmp"), Path("/private/tmp"))
            and info.st_mode & stat.S_ISVTX
        ):
            continue
        if info.st_uid not in (0, owner) or info.st_mode & 0o022:
            raise ValueError("Unsafe control directory ownership/mode")


def regular(info, *, owner=0, private=True):
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != owner
        or info.st_nlink != 1
        or info.st_mode & 0o022
        or (private and stat.S_IMODE(info.st_mode) != 0o600)
    ):
        raise ValueError("Unsafe control file ownership/mode/type/link count")


@contextlib.contextmanager
def opened(path, *, owner=0, private=True, create=False):
    path = Path(path)
    directory(path.parent, owner=owner)
    flags = (
        os.O_NOFOLLOW
        | os.O_NONBLOCK
        | (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY)
    )
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValueError("Cannot safely open control file") from exc
    with os.fdopen(fd, "r+b" if create else "rb") as stream:
        regular(os.fstat(stream.fileno()), owner=owner, private=private)
        yield stream


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError("Non-finite JSON value")


def _finite_float(text):
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid JSON number") from exc
    if not math.isfinite(value):
        raise ValueError("Non-finite JSON value")
    return value


def read_json(path, *, owner=0):
    with opened(path, owner=owner) as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Control JSON exceeds limit")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique,
            parse_constant=_invalid_constant,
            parse_float=_finite_float,
        )
    except (ValueError, RecursionError) as exc:
        raise ValueError("Malformed control JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Control JSON must be an object")
    # Do not rely on the Python version's JSON parser recursion limit.
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise ValueError("Control JSON nesting exceeds limit")
        children = (
            item.values()
            if isinstance(item, dict)
            else item
            if isinstance(item, list)
            else ()
        )
        pending.extend((child, depth + 1) for child in children)
    return value


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value, *, owner=0):
    path = Path(path)
    directory(path.parent, owner=owner)
    if path.exists() or path.is_symlink():
        with opened(path, owner=owner):
            pass
    raw = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(raw) > LIMIT:
        raise ValueError("Control JSON exceeds limit")
    # Same filesystem; failed temporary files are preserved as failure evidence.
    tmp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        regular(os.fstat(stream.fileno()), owner=owner)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    sync_directory(path.parent)


@contextlib.contextmanager
def locked(path, *, owner=0):
    with opened(path, owner=owner, create=True) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
