#!@python@
"""Move the nearest available BSP boundary by 50 pixels."""

import json
import shutil
import subprocess
import sys

RESIZE_AMOUNT = 50
RESIZE_MAP = {
    "left": (f"left:-{RESIZE_AMOUNT}:0", f"right:-{RESIZE_AMOUNT}:0"),
    "right": (f"right:{RESIZE_AMOUNT}:0", f"left:{RESIZE_AMOUNT}:0"),
    "up": (f"top:0:-{RESIZE_AMOUNT}", f"bottom:0:-{RESIZE_AMOUNT}"),
    "down": (f"bottom:0:{RESIZE_AMOUNT}", f"top:0:{RESIZE_AMOUNT}"),
}


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
    if len(args) != 1 or args[0] not in RESIZE_MAP:
        print("Usage: resize-window.py <left|right|up|down>", file=sys.stderr)
        return 1
    try:
        executable = find_yabai()
        window_id = focused_window(executable)
        # Keep both attempts on the window that was focused at keypress time.
        for resize in RESIZE_MAP[args[0]]:
            result = run_yabai(executable, "window", window_id, "--resize", resize)
            if not result.returncode:
                return 0
        raise RuntimeError(failure(result))
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"resize-window: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
