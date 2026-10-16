"""Build a native application on the current OS, optionally bundling Chromium."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-browser", action="store_true", help="Include Chromium for offline notebook PDF export")
    parser.add_argument("--onefile", action="store_true", help="Build one executable instead of an application folder")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    if args.onefile:
        env["NOTEBOOK_PRESS_ONEFILE"] = "1"
    if args.with_browser:
        env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], env=env, check=True)
        env["NOTEBOOK_PRESS_BUNDLE_BROWSER"] = "1"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(root / "NotebookPress.spec")],
                   cwd=root, env=env, check=True)
    print(f"Application created in {root / 'dist'}")


if __name__ == "__main__":
    main()
