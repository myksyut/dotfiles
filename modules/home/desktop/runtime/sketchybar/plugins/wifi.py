#!@python@
import os
import re
from common import command, update

def main():
    # Discover Wi-Fi's interface rather than assuming en0. Neither read exposes SSIDs.
    ports = command('networksetup', '-listallhardwareports')
    match = re.search(r'Hardware Port: (?:Wi-Fi|AirPort)\nDevice: (\S+)', ports)
    name = os.environ.get('NAME', 'wifi')
    if not match:
        update(name, icon='󰤭', label='')
        return
    interface = match.group(1)
    power = command('networksetup', '-getairportpower', interface)
    active = bool(re.search(r'^\s*status: active\s*$', command('ifconfig', interface), re.M))
    icon = '󰤭' if 'On' not in power else ('󰤨' if active else '󰤯')
    update(name, icon=icon, label='')

if __name__ == '__main__':
    main()
