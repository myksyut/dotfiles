#!@python@
"""Preserve unmanaged configuration before Home Manager replaces its links."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

TARGETS = (
    '.yabairc', '.skhdrc', '.config/skhd/skhdrc', '.config/skhd/scripts',
    '.config/sketchybar', '.config/borders/bordersrc',
    '.local/bin/reload-theme', '.local/bin/yabai-config-tool',
    'Library/Application Support/com.mitchellh.ghostty/config.ghostty',
)


def main():
    home = Path.home()
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup = home / '.local/state/yabai-config/backups' / timestamp
    for relative in TARGETS:
        source = home / relative
        if not source.exists() and not source.is_symlink():
            continue
        # Home Manager's own previous generation is already retained by Nix.
        if source.is_symlink() and str(source.resolve()).startswith('/nix/store/'):
            continue
        backup.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination, follow_symlinks=False)
    if backup.exists():
        print(f'Previous desktop configuration saved in {backup}')


if __name__ == '__main__':
    main()
