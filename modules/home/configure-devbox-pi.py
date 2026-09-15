"""Keep Devbox Pi autonomous while retaining the agent-pi tools and security hooks."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile

path = Path(sys.argv[1])
if path.is_symlink() or not path.is_file():
    raise SystemExit("Expected a regular Pi settings file")
original = path.read_bytes()
settings = json.loads(original)
excluded = [
    "!extensions/mode-cycler.ts",
    "!extensions/plan-grill-gate.ts",
    "!extensions/completion-report.ts",
]
matched = 0
for i, entry in enumerate(settings.get("packages", [])):
    source = entry if isinstance(entry, str) else entry.get("source", "")
    if not re.search(r"(?:^|/)\w+-agent-pi-[^/]+$", source):
        continue
    matched += 1
    if isinstance(entry, str):
        entry = {"source": entry}
        settings["packages"][i] = entry
    current = entry.setdefault("extensions", [])
    for item in excluded:
        if item not in current:
            current.append(item)
if matched != 1:
    raise SystemExit(f"Expected one Nix agent-pi package, found {matched}")
updated = (json.dumps(settings, ensure_ascii=False, indent=2) + "\n").encode()
if json.loads(original) != settings:
    backup = path.with_name("settings.before-devbox-autonomy.json")
    if not backup.exists():
        with backup.open("xb") as output:
            os.chmod(backup, 0o600)
            output.write(original)
    fd, temporary = tempfile.mkstemp(prefix=".devbox-autonomy-", dir=path.parent)
    try:
        os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "wb") as output:
            output.write(updated)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
print(json.dumps({"devbox_autonomy": True, "excluded_extensions": excluded}))
