#!/usr/bin/env python3
"""Capture diagnostic CLI evidence without inventing an Orca safety schema.
Run as the Orca user. Files can contain private data; never send them to Fly logs.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

COMMANDS = {
    "status": ["status", "--json"],
    "worktrees": ["worktree", "ps", "--json"],
    "terminals": ["terminal", "list", "--json"],
    "hooks": ["agent", "hooks", "status", "--json"],
}


def observe(cli, output):
    os.umask(0o077)
    if not Path(cli).is_absolute():
        raise ValueError("Use the verified absolute Orca CLI path")
    # Each observation gets a fresh directory: no overwrite of prior evidence.
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    errors = ["unverified connection count, host scope, save completion and drain"]
    for name, args in COMMANDS.items():
        try:
            proc = subprocess.run(
                [cli, *args], capture_output=True, timeout=15, check=False
            )
            if proc.returncode != 0 or len(proc.stdout) > 1024 * 1024:
                errors.append(name + ": failed or oversized output")
                continue
            value = json.loads(proc.stdout)
            if not isinstance(value, (dict, list)):
                raise ValueError("not a JSON container")
            (output / (name + ".json")).write_bytes(proc.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            errors.append(name + ": unavailable/invalid JSON")
    observation = {
        "schema": 1,
        "observed_at": time.time(),
        "runtime_id": None,
        "auto_stop": False,
        "errors": errors,
    }
    try:
        observation["boot_id"] = (
            Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        )
    except OSError:
        observation["boot_id"] = None
    (output / "observation.json").write_text(json.dumps(observation, indent=2))
    return observation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        observe(args.cli, args.output)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Observation failed: {exc}") from exc
    print("Evidence saved privately. Automatic stop remains disabled.")
