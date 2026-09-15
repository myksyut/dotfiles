"""Linux-only bounded daemon operations; never infer drain from an empty scan."""

import json
import os
import socket
import stat
import struct
import subprocess
from pathlib import Path

from .boundary import directory, opened  # pyright: ignore[reportMissingImports]
from .provision import (  # pyright: ignore[reportMissingImports]
    BUILD_UIDS,
    RUNTIME,
    VERSION,
    root_environment,
)

SOCKET = Path("/nix/var/nix/daemon-socket/socket")


def identity(pid, proc=Path("/proc")):
    raw = (proc / str(pid) / "stat").read_text()
    try:
        fields = raw.rsplit(")", 1)[1].split()
        return {"start": fields[19], "pgid": int(fields[2]), "sid": int(fields[3])}
    except (IndexError, ValueError) as exc:
        raise ValueError("Malformed Nix process identity") from exc


def worker_pids(*, group=None, exclude=(), extra_uids=(), proc=Path("/proc")):
    managed_uids = {*BUILD_UIDS, *extra_uids}
    result = []
    for entry in proc.iterdir():
        if not entry.name.isascii() or not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
            if pid in exclude:
                continue
            with (entry / "status").open() as stream:
                text = stream.read(65537)
            if len(text) > 65536:
                raise ValueError("Process status exceeds observation bound")
            line = next(
                (line for line in text.splitlines() if line.startswith("Uid:")), ""
            )
            uids = [int(value) for value in line.split()[1:]]
            if len(uids) != 4:
                raise ValueError("Missing process UID observation")
            info = identity(pid, proc)
            if any(uid in managed_uids for uid in uids) or (
                group is not None and (info["pgid"] == group or info["sid"] == group)
            ):
                result.append(pid)
        except FileNotFoundError:
            continue
    return result


def prepare_socket():
    target = SOCKET.parent
    source = Path("/run/devbox/nix-socket")
    directory(target)
    directory(source.parent)
    environment = root_environment()
    filesystem = subprocess.run(
        ["/usr/bin/findmnt", "-n", "-o", "FSTYPE", "--target", "/run"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    if filesystem.stdout.strip() != "tmpfs":
        raise ValueError("Nix socket requires boot-local tmpfs /run")
    mounted = subprocess.run(
        ["/usr/bin/mountpoint", "-q", str(target)], env=environment, timeout=5
    )
    if mounted.returncode != 32 or any(target.iterdir()):
        raise ValueError(
            "Existing or ambiguous daemon socket mount; no automatic cleanup"
        )
    source.mkdir(mode=0o755)
    source.chmod(0o755)
    subprocess.run(
        ["/usr/bin/mount", "--bind", str(source), str(target)],
        env=environment,
        timeout=5,
        check=True,
    )
    if (source.stat().st_dev, source.stat().st_ino) != (
        target.stat().st_dev,
        target.stat().st_ino,
    ):
        raise ValueError("Daemon socket bind identity mismatch")


def start_daemon():
    prepare_socket()
    logs = Path("/run/devbox/logs")
    directory(logs)
    with opened(logs / "nix.log", create=True) as log:
        log.seek(0, os.SEEK_END)
        return subprocess.Popen(
            [RUNTIME + "/bin/nix-daemon", "--daemon"],
            env=root_environment(daemon=False),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def probe_daemon(process, start):
    if process.poll() is not None or identity(process.pid)["start"] != start:
        return False
    info = SOCKET.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0:
        raise ValueError("Invalid daemon socket")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect(str(SOCKET))
        peercred = getattr(socket, "SO_PEERCRED", None)
        if not isinstance(peercred, int):
            raise ValueError("Linux peer PID/UID credentials are required")
        pid, uid, _ = struct.unpack(
            "3i", connection.getsockopt(socket.SOL_SOCKET, peercred, 12)
        )
        if pid != process.pid or uid != 0:
            raise ValueError("Daemon socket belongs to another process")
    result = subprocess.run(
        [RUNTIME + "/bin/nix", "store", "ping", "--store", "daemon", "--json"],
        env=root_environment(),
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode or len(result.stdout) > 16384:
        return False
    try:
        response = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("Invalid daemon IPC response") from exc
    return isinstance(response, dict) and response.get("version") == VERSION
