#!@python@
import sys
from common import command, query

def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        return
    sid = int(sys.argv[1])
    spaces = query('yabai', '-m', 'query', '--spaces', default=[])
    if any(space.get('index') == sid for space in spaces):
        # Current yabai supports this command without the scripting addition.
        command('yabai', '-m', 'space', '--focus', str(sid))

if __name__ == '__main__':
    main()
