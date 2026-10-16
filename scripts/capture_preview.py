"""Capture only our Windows app window, including when another app covers it."""

import argparse
import ctypes as ct
from ctypes import wintypes as wt
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from notebook_press.app import App


def capture(app, path):
    user, gdi = ct.windll.user32, ct.windll.gdi32
    user.GetParent.argtypes, user.GetParent.restype = [wt.HWND], wt.HWND
    user.GetDC.argtypes, user.GetDC.restype = [wt.HWND], wt.HDC
    user.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user.GetClientRect.argtypes = [wt.HWND, ct.POINTER(wt.RECT)]
    user.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [wt.HDC], wt.HDC
    gdi.CreateCompatibleBitmap.argtypes, gdi.CreateCompatibleBitmap.restype = [wt.HDC, ct.c_int, ct.c_int], wt.HBITMAP
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [wt.HDC, wt.HANDLE], wt.HANDLE
    gdi.DeleteObject.argtypes = [wt.HANDLE]
    gdi.DeleteDC.argtypes = [wt.HDC]
    gdi.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ct.c_void_p, ct.c_void_p, wt.UINT]
    hwnd = user.GetParent(app.winfo_id()) or app.winfo_id()
    rect = wt.RECT()
    user.GetClientRect(hwnd, ct.byref(rect))
    width, height = rect.right, rect.bottom
    dc = user.GetDC(hwnd)
    memory = gdi.CreateCompatibleDC(dc)
    bitmap = gdi.CreateCompatibleBitmap(dc, width, height)
    previous = gdi.SelectObject(memory, bitmap)
    try:
        if not user.PrintWindow(hwnd, memory, 3):
            raise RuntimeError("Could not capture the app window")
        # BITMAPINFOHEADER, top-down 32-bit BGR pixels.
        import struct
        header = ct.create_string_buffer(struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0))
        pixels = ct.create_string_buffer(width * height * 4)
        if not gdi.GetDIBits(memory, bitmap, 0, height, pixels, header, 0):
            raise RuntimeError("Could not read captured pixels")
        picture = Image.frombuffer('RGB', (width, height), pixels.raw, 'raw', 'BGRX', 0, 1)
        picture.save(path)
    finally:
        gdi.SelectObject(memory, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(hwnd, dc)


if __name__ == '__main__':
    if sys.platform != 'win32':
        raise SystemExit('This screenshot helper uses Windows PrintWindow.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--width', type=int, default=1180)
    parser.add_argument('--height', type=int, default=850)
    parser.add_argument('--output', default='preview.png')
    parser.add_argument('--details', action='store_true')
    args = parser.parse_args()
    app = App()
    app.source.set('examples/research.ipynb')
    app.destination.set('exports')
    app.want_pdf.set(True)
    app.want_latex.set(True)
    app.pdf_engine.set('browser')
    app.include_code.set(True)
    app.geometry(f'{args.width}x{args.height}')
    if args.details:
        app._toggle_details()
    app.update()
    app.after(700, app.quit)
    app.mainloop()
    capture(app, args.output)
    app.destroy()
