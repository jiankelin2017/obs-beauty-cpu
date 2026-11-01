# -*- coding: utf-8 -*-
"""单个参数组合的安全性+效果测试（每次调用一个独立进程）。

用法：python probe_one.py "<k=v;k=v>" [image]
为什么一个进程只测一组：SDK 的注入口只增量下发、不重置，粘滞会让后面的行全部
变成累积效果；而且某些参数（实测至少一个）会让 fuRenderItemsEx 抛访问违例，
一旦抛了整个进程的 SDK 就停用，后面全废。
"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from measure_whiten_fixed import read_png_rgba  # noqa: E402

DLL = os.path.join(HERE, "legacy_engine_test.dll")
ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
OUT = os.path.join(HERE, "out")
EXTRA = os.path.join(HERE, "extra.txt")
PANEL = os.path.join(HERE, "panel.txt")


def is_skin(r, g, b):
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b
    if y < 30 or not (77 <= cb <= 127) or not (133 <= cr <= 173):
        return False
    mx, mn = max(r, g, b), min(r, g, b)
    if mx > 0 and (mx - mn) / mx > 0.55:
        return False
    return True


def main():
    combo = sys.argv[1]
    img = sys.argv[2] if len(sys.argv) > 2 else os.path.join(OUT, "frame_0.png")
    rgba, w, h = read_png_rgba(img)
    raw_in = os.path.join(OUT, "_one_in.raw")
    raw_out = os.path.join(OUT, "_one_out.raw")
    open(raw_in, "wb").write(rgba)

    skin = [i for i in range(w * h)
            if is_skin(rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2])]
    n = len(skin)
    b_l = b_r = b_s = b_d = 0.0

    def L(buf, i):
        o = i * 4
        return 0.299 * buf[o] + 0.587 * buf[o + 1] + 0.114 * buf[o + 2]

    for i in skin:
        o = i * 4
        r, g, bb = rgba[o], rgba[o + 1], rgba[o + 2]
        b_l += L(rgba, i)
        b_r += r - bb
        mx, mn = max(r, g, bb), min(r, g, bb)
        b_s += 0.0 if mx == 0 else (mx - mn) / mx
    b_l /= n; b_r /= n; b_s /= n
    acc = 0.0
    cnt = 0
    for i in skin:
        y, x = divmod(i, w)
        if y == 0 or x == 0 or y == h - 1 or x == w - 1:
            continue
        acc += abs(4 * L(rgba, i) - L(rgba, i - 1) - L(rgba, i + 1)
                   - L(rgba, i - w) - L(rgba, i + w))
        cnt += 1
    b_d = acc / cnt if cnt else 0.0

    open(PANEL, "w").write("")
    open(EXTRA, "w").write(combo)
    os.environ["BEAUTY_EXTRA_PARAMS_FILE"] = EXTRA

    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int]
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                           raw_out.encode("ascii"), w, h, 0.0, 0.0, msg, 2048)
    txt = msg.value.decode("utf-8", "replace")
    if ret != 0:
        print("%-40s CRASH/FAIL  %s" % (combo, txt[:60]))
        return 2
    b = open(raw_out, "rb").read()
    sl = sr = ss = 0.0
    cov = 0
    for i in skin:
        o = i * 4
        r, g, bb = b[o], b[o + 1], b[o + 2]
        sl += L(b, i)
        sr += r - bb
        mx, mn = max(r, g, bb), min(r, g, bb)
        ss += 0.0 if mx == 0 else (mx - mn) / mx
        if (abs(r - rgba[o]) > 4 or abs(g - rgba[o + 1]) > 4
                or abs(bb - rgba[o + 2]) > 4):
            cov += 1
    acc = 0.0
    cnt = 0
    for i in skin:
        y, x = divmod(i, w)
        if y == 0 or x == 0 or y == h - 1 or x == w - 1:
            continue
        acc += abs(4 * L(b, i) - L(b, i - 1) - L(b, i + 1)
                   - L(b, i - w) - L(b, i + w))
        cnt += 1
    d = acc / cnt if cnt else 0.0
    print("%-40s %7.2f %+8.2f %+8.2f %+8.2f %+8.3f"
          % (combo, 100.0 * cov / n, sl / n - b_l, d - b_d, sr / n - b_r, ss / n - b_s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
