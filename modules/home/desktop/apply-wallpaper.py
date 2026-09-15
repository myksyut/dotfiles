#!/usr/bin/env python3
"""Apply a Nix wallpaper once per image hash, preserving later manual choices."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def image_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def console_session_ready():
    try:
        return os.geteuid() != 0 and Path('/dev/console').stat().st_uid == os.getuid()
    except OSError:
        return False


def read_state(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def current_pictures(desktoppr):
    result = subprocess.run(
        [desktoppr, 'all'], check=True, capture_output=True, text=True, timeout=15,
    )
    pictures = [line for line in result.stdout.splitlines() if line]
    if any(not Path(path).is_absolute() for path in pictures):
        raise RuntimeError('desktoppr returned an unexpected wallpaper path')
    return pictures


def matches_image(paths, wanted_hash):
    if not paths:
        return False
    try:
        return all(image_hash(path) == wanted_hash for path in paths)
    except OSError:
        return False


def write_state(path, value):
    # Do not publish a success marker until the complete JSON is on disk.
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.wallpaper-',
                                     suffix='.json', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write('\n')
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_wallpaper(desktoppr, image, state, force=False):
    image = Path(image).expanduser().resolve(strict=True)
    if not image.is_file():
        raise RuntimeError('The declared wallpaper is not an image file')
    wanted_hash = image_hash(image)
    state = Path(state).expanduser()
    if not force and read_state(state).get('sha256') == wanted_hash:
        print('Wallpaper already initialized for this image; keeping the current choice.')
        return 'unchanged'
    if not console_session_ready():
        print('No active GUI session for this user; wallpaper will be retried on the next switch.')
        return 'deferred'

    state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = state.with_suffix('.lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another wallpaper application is already running.')
            return 'deferred'
        # A concurrent activation may have finished while we acquired the lock.
        previous_state = read_state(state)
        if not force and previous_state.get('sha256') == wanted_hash:
            return 'unchanged'
        before = current_pictures(desktoppr)
        if not before:
            print('No connected display is available; wallpaper will be retried on the next switch.')
            return 'deferred'
        source_changed = previous_state.get('sha256') not in (None, wanted_hash)
        changed = force or source_changed or not matches_image(before, wanted_hash)
        if changed:
            # A single call sets all currently connected displays. Avoid scale/color
            # calls so the user's placement choices are not changed separately.
            subprocess.run([desktoppr, 'all', str(image)], check=True,
                           capture_output=True, text=True, timeout=20)
            # The wallpaper agent applies changes asynchronously.
            for delay in (0.25, 0.75, 1.5):
                time.sleep(delay)
                after = current_pictures(desktoppr)
                if len(after) == len(before) and matches_image(after, wanted_hash):
                    break
            else:
                raise RuntimeError('Wallpaper could not be verified on every connected display; no success marker was saved')
        write_state(state, {
            'sha256': wanted_hash,
            'image': str(image),
            'verified_at': datetime.now(timezone.utc).isoformat(),
            'display_count': len(before),
            'previous_paths': before,
        })
        print(f'Wallpaper initialized on {len(before)} display(s).')
        return 'applied' if changed else 'already-matching'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktoppr', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--state', default=str(Path.home() / '.local/state/desktop-theme/wallpaper.json'))
    parser.add_argument('--force', action='store_true', help='Reapply this image even after a manual wallpaper change')
    args = parser.parse_args(argv)
    try:
        apply_wallpaper(args.desktoppr, args.image, args.state, args.force)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'desktop-wallpaper: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
