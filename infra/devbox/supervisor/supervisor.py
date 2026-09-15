#!/usr/bin/python3 -I
"""Primary application process (not necessarily PID 1 under Fly's init).
No automatic restarts that could duplicate an Orca runtime/PTY daemon.
Validated empty-host idle shutdown or approved manual stop exits zero.
Private child logs can contain pairing URLs and are never copied to Fly logs.
"""

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "idle-controller"))
# Sibling script is shipped at the path added above (not a site-package).
from manual_stop import developer_processes  # type: ignore[import-not-found]  # noqa: E402, I001
import autostop
import safety  # type: ignore[import-not-found]  # noqa: E402, I001
from tailscale_state import startup_state  # type: ignore[import-not-found]  # noqa: E402, I001

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nix import runtime as nix_runtime  # type: ignore[import-not-found]  # noqa: E402
from nix.boundary import read_json  # type: ignore[import-not-found]  # noqa: E402

RUN = Path("/run/devbox")


def approval_valid(approval, boot, now, *, orca_exited, developer_pids):
    if not isinstance(approval, dict):
        return False
    at = approval.get("at")
    return (
        bool(boot)
        and approval.get("boot_id") == boot
        and approval.get("mode") == "manual-validated-hook"
        and isinstance(approval.get("nix_stop_request_id"), str)
        and re.fullmatch("[0-9a-f]{32}", approval["nix_stop_request_id"]) is not None
        and isinstance(at, (int, float))
        and not isinstance(at, bool)
        and 0 <= now - at < 30
        and orca_exited
        and not developer_pids
    )


def terminate_requested(*_):
    raise SystemExit(1)  # External provider stop is NOT a verified clean stop.


def publish_status(status):
    try:
        tmp = Path("/run/devbox-status.tmp")
        tmp.write_text(json.dumps(status) + "\n")
        tmp.chmod(0o644)  # Only redacted status is readable by the developer.
        tmp.replace("/run/devbox-status.json")
    except OSError:
        # Status IO must not turn a fenced stop failure into an on-failure reboot.
        print(
            "Cannot publish status; inspect root console. No automatic recovery.",
            file=sys.stderr,
        )


def require_nix_stop(check):
    verified = check()
    if not isinstance(verified, bool) or not verified:
        raise ValueError("Nix stopped state is not verified")


def finalize_stop(
    approval,
    tailscale,
    *,
    registry_check=None,
    process_check=None,
    sync=None,
    write_state=None,
    service_groups=(),
    nix_check=None,
):
    registry_check = registry_check or safety.check_registry
    process_check = process_check or developer_processes
    sync = sync or os.sync
    write_state = write_state or safety.durable_state
    nix_check = nix_check or (
        lambda: nix_runtime.assert_stopped(approval.get("nix_stop_request_id"))
    )
    try:
        # Same root-owned inode as devbox run/hold. Keep exclusive ownership until
        # all checks/IO finish. The persisted draining state remains after unlock.
        with safety.admission(exclusive=True, require_open=False) as fence:
            if safety.load_object(fence)["state"] != "draining":
                raise ValueError("Shutdown requires a closed admission fence")
            registry_check()
            if process_check():
                raise ValueError("New developer process before finalization")
            require_nix_stop(nix_check)
            tailscale.terminate()
            if tailscale.wait(timeout=30) != 0:
                raise ValueError("Unclean Tailscale exit")
            registry_check()
            if process_check() or service_group_members(service_groups):
                raise ValueError(
                    "Developer/service group members remain after Tailscale exit"
                )
            require_nix_stop(nix_check)
            sync()
            write_state(safety.RECOVERY.parent / "last-clean-stop.json", approval)
            sync()
            write_state(
                safety.RECOVERY, {"phase": "stopped", "boot_id": safety.boot_id()}
            )
            return True
    except (OSError, ValueError, subprocess.SubprocessError):
        # Leave the supervisor alive and never reopen admission automatically.
        # Recovery intent was durable before any service was stopped.
        # If recording the failure also fails, retain the existing draining intent.
        with contextlib.suppress(OSError, ValueError):
            safety.durable_state(
                safety.RECOVERY, {"phase": "needs-review", "boot_id": safety.boot_id()}
            )
        return False


def service_group_members(groups, proc=Path("/proc")):
    if not groups:
        return []
    members = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            info = safety.proc_info(int(entry.name), proc)
            if info["pgid"] in groups or info["sid"] in groups:
                members.append(entry.name)
        except FileNotFoundError:
            continue
    return members


def home_ready(nix_generation=None):
    if (
        not isinstance(nix_generation, str)
        or re.fullmatch("[0-9a-f]{64}", nix_generation) is None
    ):
        return False
    try:
        marker = read_json(Path("/data/meta/home-ready"), owner=safety.ROOT_UID)
        state = read_json(
            Path("/data/meta/bootstrap-state.json"), owner=safety.ROOT_UID
        )
        return (
            type(state.get("schema")) is int
            and state["schema"] == 2
            and state.get("nix_mode") == "multi-user"
            and state.get("phase") == "home-ready"
            and state.get("nix_generation") == nix_generation
            and type(state.get("exit_code")) is int
            and state["exit_code"] == 0
            and type(marker.get("schema")) is int
            and marker["schema"] == 2
            and marker.get("generation_digest") == nix_generation
        )
    except (OSError, ValueError):
        return False


def reap_untracked(processes, *, proc=Path("/proc"), parent=None, waitpid=None):
    parent = parent or os.getpid()
    waitpid = waitpid or os.waitpid
    tracked = {process.pid for process in processes if process is not None}
    with (proc / str(parent) / "task" / str(parent) / "children").open() as stream:
        children = stream.read(65537)
    if len(children) > 65536:
        raise ValueError("Child inventory exceeds limit")
    for raw in children.split():
        try:
            child = int(raw)
            if child > 0 and child not in tracked:
                waitpid(child, os.WNOHANG)
        except ChildProcessError:
            continue


def probe_network(expected_node_id, *, runner=None, interface_present=None):
    blocked = {
        "address": None,
        "network": "unverified",
        "reason_code": "TAILSCALE_PROBE_FAILED",
    }
    runner = runner or subprocess.run
    try:
        result = runner(
            [
                "/opt/tailscale/tailscale",
                "--socket=/run/tailscale/tailscaled.sock",
                "status",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return blocked
        state = startup_state(json.loads(result.stdout), expected_node_id)
        present = (
            interface_present()
            if interface_present
            else Path("/sys/class/net/tailscale0").is_dir()
        )
        if not present:
            return {**blocked, "reason_code": "TAILSCALE_TUN_MISSING"}
        return state
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return blocked


def network_state():
    try:
        with safety.checked_file(
            Path("/data/meta/tailscale-node.json"), owners={0}
        ) as stream:
            identity = safety.load_object(stream)
        return probe_network(identity.get("node_id"))
    except (OSError, ValueError):
        return {
            "address": None,
            "network": "unverified",
            "reason_code": "TAILSCALE_IDENTITY_UNVERIFIED",
        }


def private_address():
    return network_state()["address"]


def spawn(name, argv, **kwargs):
    kwargs.setdefault("start_new_session", True)
    try:
        with open(RUN / "logs" / (name + ".log"), "ab", buffering=0) as log:
            return subprocess.Popen(argv, stdout=log, stderr=log, **kwargs)
    except OSError as exc:
        raise SystemExit(f"{name}: cannot launch service ({exc.errno})") from exc


def admitted_orca_spawn(nix, argv, environment):
    with safety.admission():
        if not nix.available:
            raise ValueError("Nix became unavailable before Orca spawn")
        return spawn("orca", argv, env=environment)


def main():
    if os.getuid() != 0 or not Path("/etc/devbox-host").is_file():
        raise SystemExit("Must be launched by the entrypoint inside the devbox image")
    os.umask(0o077)
    signal.signal(signal.SIGTERM, terminate_requested)
    signal.signal(signal.SIGINT, terminate_requested)
    try:
        nix = nix_runtime.NixRuntime()
    except (OSError, ValueError):
        nix = None  # Invalid control state stays diagnosable; never auto-repair.
    ts = spawn(
        "tailscale",
        [
            "/opt/tailscale/tailscaled",
            "--state=/data/tailscale/tailscaled.state",
            "--socket=/run/tailscale/tailscaled.sock",
            "--port=41641",
        ],
    )
    orca = None
    attempted = False
    finalization_failed = False
    idle = autostop.Controller()
    while True:
        # Process intermediate Nix requests before network probes/final approval.
        nix_state = (
            nix.tick()
            if nix
            else {"state": "needs-review", "reason_code": "NIX_CONTROL_UNSAFE"}
        )
        network = (
            network_state()
            if ts.poll() is None
            else {
                "address": None,
                "network": "failed",
                "reason_code": "TAILSCALE_EXITED",
            }
        )
        status = {
            "boot_id": safety.boot_id(),
            "network": network["network"],
            "reason_code": network["reason_code"],
            "machine": "started",
            "orca": "not-started",
            "nix": nix_state,
            "ready": "unknown",
            "auto_stop": False,
            "reason": "Orca safety/drain contract unverified",
        }
        if finalization_failed or safety.recovery_required():
            status["reason"] = (
                "Shutdown/recovery fence active; operator review required"
            )
            status["reason_code"] = "SHUTDOWN_REVIEW_REQUIRED"
        elif ts.poll() is not None:
            status["reason"] = "Tailscale exited; operator recovery required"
        elif os.environ.get("DEVBOX_MODE", "maintenance") == "serve":
            if nix is None or not nix.available:
                status["reason"] = "Nix unavailable; no new Orca startup"
                status["reason_code"] = nix_state["reason_code"]
            elif not home_ready(nix.generation):
                status["reason"] = "Home Manager bootstrap incomplete"
                status["reason_code"] = "HOME_BOOTSTRAP_INCOMPLETE"
            elif not attempted:
                address = network["address"]
                if address:
                    attempted = True
                    # Do not forward management/backup secrets from the service environment.
                    child_env = {
                        "PATH": "/usr/bin:/bin",
                        "LANG": "C.UTF-8",
                        "ORCA_CLI": os.environ.get("ORCA_CLI", ""),
                        "DEVBOX_TAILSCALE_ADDRESS": address,
                    }
                    try:
                        orca = admitted_orca_spawn(
                            nix,
                            [
                                "/usr/sbin/runuser",
                                "-u",
                                "miyakishota",
                                "--",
                                "/bin/bash",
                                "/opt/devbox/orca/serve.sh",
                            ],
                            child_env,
                        )
                    except (OSError, ValueError, SystemExit):
                        status["reason_code"] = "ORCA_START_FAILED"
        else:
            status["reason"] = "Maintenance mode; provision and authenticate manually"
            status["reason_code"] = "MAINTENANCE_MODE"
        if orca:
            status["orca"] = "running" if orca.poll() is None else "failed"
            # A live process is not proof that pairing, agents or saved state work.
        elif attempted:
            status["orca"] = "failed"
            status["reason_code"] = "ORCA_START_FAILED"
        status["auto_stop"] = idle.state["enabled"]
        status["idle_stop"] = idle.state
        status["reason"] = "Idle stop waits for an empty, disconnected host" if not finalization_failed and not safety.recovery_required() else status["reason"]
        publish_status(status)
        if not finalization_failed and not safety.recovery_required():
            if idle.tick(nix, ts, orca):
                return 0
        request = RUN / "stop-approved.json"
        if (request.exists() or request.is_symlink()) and not finalization_failed:
            try:
                approval = read_json(request)
            except (OSError, ValueError):
                approval = {}
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            if approval_valid(
                approval,
                boot,
                time.time(),
                orca_exited=orca is None or orca.poll() is not None,
                developer_pids=[],
            ):
                if finalize_stop(
                    approval,
                    ts,
                    service_groups=tuple(
                        p.pid
                        for p in (ts, orca, nix.process if nix else None)
                        if p is not None
                    ),
                ):
                    return 0
                finalization_failed = True
                status["reason"] = (
                    "Stop finalization failed; fence retained, no automatic retry"
                )
                publish_status(status)
        # Never consume tracked Popen statuses, including a just-exited daemon.
        try:
            reap_untracked((ts, orca, nix.process if nix else None))
        except (OSError, ValueError):
            finalization_failed = True
            status["reason_code"] = "CHILD_OBSERVATION_FAILED"
            publish_status(status)
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
