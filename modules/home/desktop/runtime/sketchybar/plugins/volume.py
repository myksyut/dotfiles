#!@python@
import os
from common import update

def main():
    # SketchyBar provides volume directly. No AppleScript/UI automation.
    try:
        volume = min(100, max(0, round(float(os.environ['INFO']))))
    except (KeyError, ValueError):
        return
    icon = '󰝟' if volume == 0 else ('󰕿' if volume < 35 else ('󰖀' if volume < 70 else '󰕾'))
    update(os.environ.get('NAME', 'volume'), icon=icon, label=f'{volume}%')

if __name__ == '__main__':
    main()
