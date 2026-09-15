"""Linux inactivity observations for the fixed Orca 1.4.197 process layout.

This is a candidate observation, not proof of saved/drained application state.
The caller also checks Orca terminals, holds, Nix root workers and a continuous
IdleWindow, then rechecks these process identities around its stop fence.
"""

from pathlib import Path
import shlex


DEVELOPER_UID = 10001
BUILD_UIDS = frozenset(range(30001, 30005))
ORCA = "/opt/Orca/orca-ide"
SERVICES = frozenset((ORCA, "/opt/Orca/chrome_crashpad_handler", "/usr/bin/Xvfb"))
CLI = "/opt/Orca/resources/app.asar.unpacked/out/cli/index.js"
PTY = "/opt/Orca/resources/app.asar.unpacked/out/main/daemon-entry.js"
PORTS = frozenset((443, 6768))


def _text(path):
    with path.open() as stream:
        value = stream.read(65537)
    if len(value) > 65536:
        raise ValueError("observation too large")
    return value


def connected(proc):
    """Include setup and closing connections; only LISTEN/TIME_WAIT are idle."""
    found = False
    for name in ("tcp", "tcp6"):
        lines = _text(proc / "net" / name).splitlines()
        if not lines or "local_address" not in lines[0] or "st" not in lines[0]:
            raise ValueError("invalid TCP table header")
        for line in lines[1:]:
            fields = line.split()
            if len(fields) < 4:
                raise ValueError("invalid TCP table row")
            port = int(fields[1].rsplit(":", 1)[1], 16)
            state = int(fields[3], 16)
            if not 0 <= port <= 65535 or not 1 <= state <= 12:
                raise ValueError("invalid TCP port/state")
            if port in PORTS and state not in (0x0A, 0x06):
                found = True
    return found


def _argv(path):
    raw = path.read_bytes()
    if not raw or len(raw) > 65536:
        raise ValueError("missing/oversized service command")
    args = [arg.decode("utf-8", errors="strict") for arg in raw.split(b"\0") if arg]
    # Electron can replace its process title with one space-joined argument.
    if len(args) == 1 and args[0].startswith(ORCA + " "):
        args = shlex.split(args[0])
    return args


def _service(exe, args):
    if exe not in SERVICES or not args:
        return False
    if exe != ORCA:
        return True
    # Electron is also a Node executable. Never whitelist arbitrary Node scripts
    # or evaluation flags merely because /proc/PID/exe names the Orca binary.
    for arg in args[1:]:
        key, _, value = arg.partition("=")
        if key in ("-e", "--eval", "-p", "--print", "--require", "-r", "--import",
                   "--run-as-node", "--command", "-c"):
            return False
        candidate = value if value else arg
        if candidate.endswith((".js", ".cjs", ".mjs")) and candidate not in (CLI, PTY):
            return False
        if arg in ("node", "nodejs", "terminal", "pty", "worker"):
            return False
        if arg.startswith("--utility-sub-type=node."):
            return False
    if CLI in args:
        return len(args) > 2 and args[1:3] == [CLI, "serve"] and PTY not in args
    if PTY in args:
        # The caller separately verifies an empty host-complete terminal list.
        return len(args) > 2 and args[1] == PTY and "--socket" in args
    return "--serve" in args or any(arg.startswith("--type=") for arg in args)


def service_identity(observation):
    return tuple((item["pid"], item["start"], item["exe"])
                 for item in observation["services"])


def observe(proc=Path("/proc"), *, require_orca=True):
    proc = Path(proc)
    result = {"idle": False, "connected": False, "services": [], "blockers": []}
    try:
        result["connected"] = connected(proc)
        if result["connected"]:
            result["blockers"].append("client connection")
        for entry in sorted(proc.iterdir(), key=lambda p: int(p.name) if p.name.isdecimal() else -1):
            if not entry.name.isascii() or not entry.name.isdecimal():
                continue
            pid = int(entry.name)
            try:
                line = next(line for line in _text(entry / "status").splitlines()
                            if line.startswith("Uid:"))
                uids = tuple(int(uid) for uid in line.split()[1:])
                if len(uids) != 4:
                    raise ValueError("invalid Uid observation")
                if BUILD_UIDS.intersection(uids) or DEVELOPER_UID in uids:
                    fields = _text(entry / "stat").rsplit(")", 1)[1].split()
                    if fields[0] == "Z":
                        continue
                if BUILD_UIDS.intersection(uids):
                    result["blockers"].append(f"Nix build process {pid}")
                elif DEVELOPER_UID in uids:
                    exe = str((entry / "exe").readlink())
                    args = _argv(entry / "cmdline")
                    start = fields[19]
                    if not start.isascii() or not start.isdecimal():
                        raise ValueError("invalid process start")
                    if not _service(exe, args):
                        result["blockers"].append(f"developer process {pid}")
                    else:
                        role = "serve-cli" if exe == ORCA and args[1:3] == [CLI, "serve"] else "service"
                        result["services"].append({"pid": pid, "start": start, "exe": exe, "role": role})
            except FileNotFoundError:
                continue  # A process exited during enumeration.
        if require_orca and not any(item["exe"] == ORCA for item in result["services"]):
            result["blockers"].append("Orca service absent")
        result["idle"] = not result["blockers"]
    except (OSError, ValueError, IndexError, StopIteration):
        result["blockers"].append("incomplete observation")
    return result
