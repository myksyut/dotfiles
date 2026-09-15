#!@python@
import os
from common import query, update

def main():
    app = os.environ.get('INFO', '') if os.environ.get('SENDER') == 'front_app_switched' else ''
    if not app:
        window = query('yabai', '-m', 'query', '--windows', '--window', default={}) or {}
        app = window.get('app', '')
    # INFO also covers apps that have no standard yabai-managed window.
    update(os.environ.get('NAME', 'front_app'), label=app)

if __name__ == '__main__':
    main()
