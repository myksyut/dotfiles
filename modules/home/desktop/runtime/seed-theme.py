#!@python@
"""Seed writable state on a new machine; never reset an existing palette."""
from datetime import datetime, timezone
from pathlib import Path
import shutil


def seed(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    # Preserve broken links before installing a writable regular file.
    if destination.is_symlink():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        destination.rename(destination.with_name(destination.name + '.before-seed-' + stamp))
    shutil.copyfile(source, destination)


def main():
    seed('@paletteSeed@', Path.home() / '.cache/wal/colors.json')
    seed('@zedSeed@', Path.home() / '.config/zed/themes/pywal.json')


if __name__ == '__main__':
    main()
