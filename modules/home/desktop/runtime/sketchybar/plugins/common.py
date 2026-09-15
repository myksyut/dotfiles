"""Bounded local command helpers; no shell, network requests, or settings writes."""
import json
import os
from pathlib import Path
import shutil
import subprocess

os.environ['PATH'] = ':'.join([
    '/opt/homebrew/bin', '/usr/local/bin', str(Path.home() / '.nix-profile/bin'),
    '/etc/profiles/per-user/' + os.environ.get('USER', Path.home().name) + '/bin',
    '/run/current-system/sw/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin',
    os.environ.get('PATH', ''),
])

def command(name, *args):
    executable = shutil.which(name)
    if not executable:
        return ''
    try:
        result = subprocess.run([executable, *args], capture_output=True,
                                text=True, timeout=5, check=False)
        return result.stdout if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''

def query(name, *args, default=None):
    try:
        return json.loads(command(name, *args))
    except (ValueError, TypeError):
        return default

def update(name, **properties):
    command('sketchybar', '--set', name,
            *(key + '=' + str(value) for key, value in properties.items()))
