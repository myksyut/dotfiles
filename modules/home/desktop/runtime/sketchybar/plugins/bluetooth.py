#!@python@
import os
from common import command, query, update

def main():
    name = os.environ.get('NAME', 'bluetooth')
    power = command('blueutil', '--power').strip()
    if power != '1':
        update(name, icon='󰂲', label='')
        return
    connected = query('blueutil', '--connected', '--format', 'json', default=[])
    count = len(connected) if isinstance(connected, list) else 0
    update(name, icon='󰂱' if count else '󰂯', label=str(count) if count else '')

if __name__ == '__main__':
    main()
