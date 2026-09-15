#!@python@
"""Toggle a Ghostty terminal using window operations available with SIP enabled."""

import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

TITLE = "scratchpad"
YABAI = shutil.which("yabai") or next(
    (p for p in ("/opt/homebrew/bin/yabai", "/usr/local/bin/yabai")
     if Path(p).is_file()),
    "yabai",
)

# A tab-title override stays stable when shell integration changes the title.
CREATE_SCRIPT = '''
tell application "Ghostty"
    set scratchWindow to new window
    set scratchTerminal to focused terminal of selected tab of scratchWindow
    if not (perform action "set_tab_title:scratchpad" on scratchTerminal) then
        error "Could not set the Ghostty scratchpad title"
    end if
    activate window scratchWindow
end tell
'''


def yabai(*args):
    result = subprocess.run(
        [YABAI, "-m", *map(str, args)], capture_output=True, text=True, timeout=5
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "yabai command failed")
    return result.stdout


def find_window():
    windows = json.loads(yabai("query", "--windows"))
    return next(
        (w for w in windows if w.get("app") == "Ghostty" and w.get("title") == TITLE),
        None,
    )


def create_window():
    subprocess.run(["/usr/bin/osascript", "-e", CREATE_SCRIPT], check=True, timeout=30)
    for _ in range(40):
        window = find_window()
        if window:
            return window
        time.sleep(0.05)
    raise RuntimeError("Ghostty scratchpad did not become available to yabai")


def show_window(window, current_space):
    window_id = window["id"]
    if window.get("is-minimized"):
        yabai("window", "--deminimize", window_id)
    if not window.get("is-floating"):
        yabai("window", window_id, "--toggle", "float")
    if window.get("space") != current_space:
        yabai("window", window_id, "--space", current_space)
    yabai("window", "--focus", window_id)
    yabai("window", window_id, "--grid", "10:10:1:1:8:7")


def toggle():
    # Capture the user's destination before creating/focusing Ghostty.
    current_space = json.loads(yabai("query", "--spaces", "--space"))["index"]
    window = find_window()
    if window and window.get("has-focus") and not window.get("is-minimized"):
        yabai("window", "--minimize", window["id"])
        return
    show_window(window or create_window(), current_space)


def main():
    # Prevent rapid repeated key presses from creating duplicate scratchpads.
    lock_path = Path(tempfile.gettempdir()) / f"yabai-ghostty-scratchpad-{os.getuid()}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        toggle()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(f"scratchpad: {exc}", file=sys.stderr)
        sys.exit(1)
