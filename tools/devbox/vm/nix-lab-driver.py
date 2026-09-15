"""Credential-free db-mu1 harness. Uses production runtime, never a drain override.

Only bounded fixture diagnostics are exported. Never deploy this lab driver on
Fly or run it with a populated/authenticated HOME. No forced cleanup or retry.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE = Path("/var/lib/devbox-nix-multi-v1")


def public_result(name, value):
    temporary = STATE / (name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream)
        stream.write("\n")
    temporary.chmod(0o644)
    temporary.replace(STATE / name)


def supervise():
    # The harness runs under -I with the verified /opt/devbox package path.
    from nix.runtime import NixRuntime  # pyright: ignore[reportMissingImports]

    runtime = NixRuntime()
    previous = None
    while True:
        status = runtime.tick()
        if status != previous:
            public_result("runtime.json", status)
            previous = status
        time.sleep(0.1)


def bootstrap():
    public_result("result.json", {"phase": "running", "pid": os.getpid()})
    # No timeout-kill: production controller owns its bounded waits and preserves
    # pending clients/workers on timeout. Neither this driver nor Lima kills them.
    with (STATE / "controller.log").open("xb") as log:
        result = subprocess.run(
            ["/opt/devbox/bootstrap.sh", "/home/miyakishota/source"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            check=False,
        )
    summary = {
        "phase": "passed" if result.returncode == 0 else "failed",
        "exit": result.returncode,
        "scope": "native-no-auth-bootstrap-only",
    }
    try:
        record = json.loads(Path("/data/meta/bootstrap-state.json").read_text())
        summary["bootstrap_stage"] = record.get("stage")
    except (OSError, ValueError):
        summary["bootstrap_stage"] = "unavailable"
    # This log is the controller's own bounded errors, not arbitrary HOME data.
    with (STATE / "controller.log").open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 4096))
        summary["controller_tail"] = stream.read().decode(errors="replace")
    public_result("result.json", summary)


def main():
    if os.getuid() != 0 or os.uname().nodename != "lima-db-mu1":
        raise ValueError("Only the approved fresh root lab")
    os.umask(0o077)
    sys.path.insert(0, "/opt/devbox")
    if sys.argv[1:] == ["supervise"]:
        supervise()
    elif sys.argv[1:] == ["bootstrap"]:
        bootstrap()
    else:
        raise ValueError("Expected supervise or bootstrap")


if __name__ == "__main__":
    main()
