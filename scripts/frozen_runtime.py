"""Point notebook templates and optional bundled Chromium at packaged assets."""

import os
from pathlib import Path
import sys

root = Path(sys._MEIPASS)
os.environ['JUPYTER_PATH'] = str(root / 'share' / 'jupyter') + os.pathsep + os.environ.get('JUPYTER_PATH', '')
if (root / 'playwright' / 'driver' / 'package' / '.local-browsers').is_dir():
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
elif 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
    # Playwright defaults frozen apps to a hermetic install. For builds without
    # a bundled browser, explicitly use the same user cache as its installer.
    if sys.platform == 'win32':
        cache = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    elif sys.platform == 'darwin':
        cache = Path.home() / 'Library' / 'Caches'
    else:
        cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(cache / 'ms-playwright')
