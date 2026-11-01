# -*- coding: utf-8 -*-
"""用 PrintWindow 抓 OBS 窗口内容。

普通截屏（ImageGrab / BitBlt）拿不到被其他窗口遮住的内容，PrintWindow 会让
目标窗口自己重绘到一个 DC 里，所以 OBS 被 Firefox / WorkBuddy 盖住也能抓到
干净的预览画面。

用法: python print_obs.py <out.png>
"""
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020


def find_obs():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if "obs" in buf.value.lower():
            out.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


def print_window(hwnd, path, client_only=False):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        print("bad rect", r)
        return None
    hdc_screen = user32.GetDC(0)
    hdc = gdi32.CreateCompatibleDC(hdc_screen)
    bmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc, bmp)
    flags = (PW_RENDERFULLCONTENT | PW_CLIENTONLY) if client_only else PW_RENDERFULLCONTENT
    ok = user32.PrintWindow(hwnd, hdc, flags)
    if not ok:
        print("PrintWindow failed, err=", ctypes.get_last_error())
        return None

    # 读出 DIB
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h          # 自上而下
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0       # BI_RGB
    buf = ctypes.create_string_buffer(w * h * 4)
    lines = gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    print("GetDIBits lines =", lines)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(0, hdc_screen)

    # BGRA -> RGB，再用 PIL 存 PNG
    from PIL import Image
    px = bytearray(w * h * 3)
    for i in range(w * h):
        o = i * 4
        px[i * 3 + 0] = buf[o + 2]
        px[i * 3 + 1] = buf[o + 1]
        px[i * 3 + 2] = buf[o + 0]
    Image.frombytes("RGB", (w, h), bytes(px)).save(path)
    print("saved %s  %dx%d" % (path, w, h))
    return (w, h)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\legacy_e2e\obs_pw.png"
    wins = find_obs()
    if not wins:
        print("no OBS window")
        return 1
    hwnd, title = wins[0]
    print("target: hwnd=%s title=%r" % (hwnd, title))
    print_window(hwnd, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
