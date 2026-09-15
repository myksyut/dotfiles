#!@python@
"""Keep space components in sync with actual Mission Control spaces."""
import fcntl
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
from common import command, query

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from palette import load_palette

def reconcile(spaces, items, python, plugin_dir):
    live = {f"space.{int(space['index'])}": space for space in spaces}
    existing = {item for item in items if re.fullmatch(r'space\.\d+', item)}
    args = []
    for stale in sorted(existing - live.keys()):
        args += ['--remove', stale]
    colors = load_palette()['colors']
    accent, inactive = '0xff' + colors['color1'][1:], '0xff' + colors['color4'][1:]
    for name, space in sorted(live.items(), key=lambda entry: int(entry[1]['index'])):
        sid = int(space['index'])
        display = int(space['display'])
        if name not in existing:
            args += ['--add', 'space', name, 'left']
        click = ' '.join(shlex.quote(token) for token in [python, str(plugin_dir / 'focus_space.py'), str(sid)])
        args += ['--set', name, f'space={sid}', f'display={display}', f'icon={sid}',
                 'label.drawing=off', 'icon.padding_left=6', 'icon.padding_right=6',
                 'background.drawing=off', f"icon.color={accent if space.get('is-visible') else inactive}",
                 f'click_script={click}', '--move', name, 'before', 'front_app']
    return args

def main():
    lock = Path(tempfile.gettempdir()) / f'yabai-config-space-sync-{os.getuid()}.lock'
    with lock.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        spaces = query('yabai', '-m', 'query', '--spaces')
        bar = query('sketchybar', '--query', 'bar')
        if not isinstance(spaces, list) or not isinstance(bar, dict):
            return
        args = reconcile(spaces, bar.get('items', []), sys.executable, Path(__file__).resolve().parent)
        if args:
            command('sketchybar', *args)

if __name__ == '__main__':
    main()
