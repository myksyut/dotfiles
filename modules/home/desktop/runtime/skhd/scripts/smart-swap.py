#!@python@
"""Swap the focused window using the upstream alternate-split fallback."""

import json
import shutil
import subprocess
import sys

VALID_DIRECTIONS = {"west", "east", "north", "south"}


def find_yabai():
    # skhd's launchd shell can have a minimal or overridden PATH.
    for candidate in ("/opt/homebrew/bin/yabai", "/usr/local/bin/yabai", "yabai"):
        executable = shutil.which(candidate)
        if executable:
            return executable
    raise RuntimeError("yabai executable was not found")


def run_yabai(executable, *args):
    return subprocess.run(
        [executable, "-m", *map(str, args)],
        capture_output=True, text=True, timeout=5,
    )


def failure(result):
    return result.stderr.strip() or "yabai command failed"


def focused_window(executable):
    result = run_yabai(executable, "query", "--windows", "--window")
    if result.returncode:
        raise RuntimeError(failure(result))
    window = json.loads(result.stdout)
    if not isinstance(window, dict) or not isinstance(window.get("id"), int):
        raise RuntimeError("no focused window is available")
    return window["id"]


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in VALID_DIRECTIONS:
        print("Usage: smart-swap.py <west|east|north|south>", file=sys.stderr)
        return 1
    try:
        executable = find_yabai()
        window_id = focused_window(executable)
        result = run_yabai(executable, "window", window_id, "--swap", args[0])
        if not result.returncode:
            return 0
        # Preserve upstream's alternate-split fallback. Do not toggle twice:
        # with auto_balance enabled, every toggle also resets BSP ratios.
        split = run_yabai(executable, "window", window_id, "--toggle", "split")
        if split.returncode:
            raise RuntimeError(failure(result))
        result = run_yabai(executable, "window", window_id, "--swap", args[0])
        if not result.returncode:
            return 0
        raise RuntimeError(failure(result))
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"smart-swap: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
