#!@python@
"""Reserve the SketchyBar row uniformly; native menu/Dock areas stay OS-managed."""
import os
from pathlib import Path
import shutil
import subprocess

BAR_HEIGHT = 37
WINDOW_GAP = 10

def main():
    os.environ['PATH'] = ':'.join(['/opt/homebrew/bin', '/usr/local/bin', str(Path.home() / '.nix-profile/bin'),
        '/etc/profiles/per-user/' + os.environ.get('USER', Path.home().name) + '/bin',
        '/run/current-system/sw/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin', os.environ.get('PATH', '')])
    yabai = shutil.which('yabai')
    if not yabai:
        return
    for setting, value in [('external_bar', f'all:{BAR_HEIGHT}:0'), ('top_padding', str(WINDOW_GAP))]:
        subprocess.run([yabai, '-m', 'config', setting, value], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)

if __name__ == '__main__':
    main()
