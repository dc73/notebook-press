"""Encode the generated logo in the native app icon formats."""

from pathlib import Path

from PIL import Image


def main():
    assets = Path(__file__).resolve().parent.parent / "notebook_press" / "assets"
    with Image.open(assets / "logo.png") as logo:
        icon = logo.convert("RGBA")
        icon.save(assets / "app.ico", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
        icon.save(assets / "app.icns", sizes=[(size, size) for size in (16, 32, 64, 128, 256, 512, 1024)])
        icon.resize((64, 64), Image.Resampling.LANCZOS).save(assets / "icon-64.png")
    print("Windows, macOS, and desktop icons created.")


if __name__ == "__main__":
    main()
