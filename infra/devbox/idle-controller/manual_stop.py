#!/usr/bin/python3 -I
"""Operator-only stop protocol. No default hook => refuse, never guess safety.
The reviewed site hook must fence ingress/local scheduling and save/stop Orca.
A hook failure keeps the Machine running and requires explicit recovery.
"""

import contextlib
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safety  # type: ignore[import-not-found]  # noqa: E402, I001

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nix import runtime as nix_runtime  # type: ignore[import-not-found]  # noqa: E402
from nix.boundary import (  # type: ignore[import-not-found]  # noqa: E402
    atomic_json,
    locked,
)
from nix.daemon import worker_pids  # type: ignore[import-not-found]  # noqa: E402

HOOK = Path("/etc/devbox/stop-hook")
RUN = Path("/run/devbox")


def check_hook(path):
    for item in [path, *path.parents]:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError(
                "Stop hook and ancestors must be root-owned, non-writable, not symlinks"
            )
    try:
        executable = path.is_file() and os.access(path, os.X_OK)
    except OSError as exc:
        raise ValueError("Cannot verify stop hook; stop blocked") from exc
    if not executable:
        raise ValueError("Validated executable stop hook is not installed")


def check_registry():
    safety.check_registry()


def developer_processes(proc=Path("/proc")):
    """Include real/effective/saved/filesystem developer and dedicated build UIDs."""
    return [str(pid) for pid in worker_pids(proc=proc, extra_uids=(10001,))]


def stop_nix(drain_id):
    request = nix_runtime.request_stop(drain_id)
    nix_runtime.await_ack(request, phase="stopped", timeout=45)
    nix_runtime.assert_stopped(request["request_id"])
    return request["request_id"]


def phase(name, runner=subprocess.run):
    # Logs may contain secrets: root-only local log, not shared stdout/stderr.
    try:
        with open(RUN / "logs/stop-hook.log", "ab") as log:
            runner(
                [str(HOOK), name],
                stdout=log,
                stderr=log,
                timeout=300,
                check=True,
                env={
                    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                    "HOME": "/root",
                    "LANG": "C.UTF-8",
                },
            )
    except OSError as exc:
        raise ValueError("Cannot execute/log stop hook; stop blocked") from exc


def stop_protocol(
    run_phase=phase,
    registry_check=check_registry,
    process_check=developer_processes,
    begin_fence=None,
    *,
    nix_stop=None,
):
    registry_check()
    # Contract of validate: verify recorded version-specific acceptance tests.
    run_phase("validate")
    if nix_stop is None:
        if not nix_runtime.stop_contract_verified():
            raise ValueError("Nix drain contract unverified; no stop effects performed")
        nix_stop = stop_nix
    try:
        drain_id = (begin_fence or safety.begin_drain)()
        run_phase("drain")
        run_phase("verify-quiescent")
        registry_check()
        run_phase("save-and-stop")
        if process_check():
            raise ValueError("Developer/build processes remain before Nix shutdown")
        nix_request_id = nix_stop(drain_id)
        if (
            not isinstance(nix_request_id, str)
            or re.fullmatch("[0-9a-f]{32}", nix_request_id) is None
        ):
            raise ValueError("Missing intermediate Nix stop acknowledgement")
        run_phase("backup")
        run_phase("verify-stopped")
        registry_check()
        if process_check():
            raise ValueError(
                "Developer processes remain; no PID-name whitelist or forced kill"
            )
        return nix_request_id
    except Exception:
        # Must not reopen tasks or restart a second runtime automatically.
        # Hook abort reports the state/required recovery, keeping ingress fenced.
        run_phase("abort")
        raise


@contextlib.contextmanager
def stop_lock():
    try:
        with locked(RUN / "stop.lock"):
            yield
    except OSError as exc:
        raise ValueError("Cannot acquire/use stop lock; stop blocked") from exc


def main():
    if (
        os.getuid() != 0
        or not Path("/etc/devbox-host").exists()
        or not sys.stdin.isatty()
    ):
        raise ValueError(
            "Use a root operator console inside the devbox, with an interactive TTY"
        )
    os.umask(0o077)
    check_hook(HOOK)
    with stop_lock():
        if (RUN / "stop-approved.json").exists() or (
            RUN / "stop-approved.json"
        ).is_symlink():
            raise ValueError(
                "Prior stop request remains; inspect it before another attempt"
            )
        answer = input(
            "Saved editors, closed all clients, checked children and backup? Type STOP SAVED DEVBOX: "
        )
        if answer != "STOP SAVED DEVBOX":
            raise ValueError("Stop not confirmed")
        nix_request_id = stop_protocol()
        approval = {
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "at": time.time(),
            "mode": "manual-validated-hook",
            "nix_stop_request_id": nix_request_id,
        }
        with safety.admission(exclusive=True, require_open=False):
            check_registry()
            if developer_processes():
                raise ValueError(
                    "New developer processes before approval; stop aborted"
                )
            nix_runtime.assert_stopped(nix_request_id)
            atomic_json(RUN / "stop-approved.json", approval)
    print(
        "Approved stop submitted. Confirm stopped from the management Mac; not just this message."
    )


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"Stop refused/aborted: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
