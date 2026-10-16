"""PyInstaller entry point (absolute imports also work outside a package)."""

from notebook_press.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
