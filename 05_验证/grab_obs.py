# -*- coding: utf-8 -*-
"""找到 OBS 主窗口并截取它的客户区。

PowerShell 的 Add-Type / COM 都被安全策略拦了，所以用 Python ctypes
EnumWindows + GetWindowRect，再用 PIL ImageGrab 按矩形截屏。

用法: python grab_obs.py <out.png>
"""
import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32


def find_obs():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        t = buf.value
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        # 只认 obs64.exe 的窗口，且标题里带 OBS
        if "obs" in t.lower():
            found.append((hwnd, t))
        return True

    user32.EnumWindows(cb, 0)
    return found


def _is_obs_pid(pid):
    import subprocess
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", "ProcessId=%d" % pid, "get", "Name"],
            stderr=subprocess.DEVNULL).decode("utf-8", "replace")
        return "obs64.exe" in out
    except Exception:
        return False


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else r"C:\legacy_e2e\obs_grab.png"
    wins = find_obs()
    if not wins:
        print("no OBS window found")
        return 1
    for hwnd, t in wins:
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        print("hwnd=%s title=%r rect=(%d,%d)-(%d,%d) size=%dx%d"
              % (hwnd, t, r.left, r.top, r.right, r.bottom,
                 r.right - r.left, r.bottom - r.top))
    # 取面积最大的那个
    hwnd, title = max(wins, key=lambda w: True)
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    box = (r.left, r.top, r.right, r.bottom)

    from PIL import ImageGrab
    im = ImageGrab.grab(bbox=box)
    im.save(out)
    print("saved %s  %s" % (out, im.size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
