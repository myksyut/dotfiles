#!@python@
import os
import re
from common import command, update

def main():
    state = command('pmset', '-g', 'batt')
    match = re.search(r'(\d+)%', state)
    name = os.environ.get('NAME', 'battery')
    if not match:
        update(name, drawing='off')
        return
    percent = min(100, int(match.group(1)))
    icon = '󰂄' if 'AC Power' in state else ('󰁹' if percent >= 90 else '󰂀' if percent >= 60 else '󰁾' if percent >= 30 else '󰁻' if percent >= 10 else '󰁺')
    update(name, drawing='on', icon=icon, label=f'{percent}%')

if __name__ == '__main__':
    main()
