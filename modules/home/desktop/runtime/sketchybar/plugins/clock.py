#!@python@
import os
from datetime import datetime
from common import update

def main():
    update(os.environ.get('NAME', 'clock'), label=datetime.now().strftime('%H:%M'))

if __name__ == '__main__':
    main()
