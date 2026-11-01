# -*- coding: utf-8 -*-
"""对照实验：同一个 red=75 的输出，用「输入肤色集」和「输出肤色集」两种口径测 dRed。

measure_all_effects.py（九项回归）是在**输出图**上重新判肤色，而美白/红润会把像素
推过判据边界，导致输出集整体偏移 —— 这正是 measure_whiten_fixed.py 的 docstring
里记录过的坑，但九项回归一直没修。这里把两种口径的差量化出来。
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
    img = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "frame_0.png")
    rgba, w, h = read_png_rgba(img)
    raw_in = os.path.join(OUT, "_sk_in.raw")
    raw_out = os.path.join(OUT, "_sk_out.raw")
    open(raw_in, "wb").write(rgba)

    open(os.path.join(HERE, "panel.txt"), "w").write("3:75")   # 只开红润 75
    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int]
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                           raw_out.encode("ascii"), w, h, 0.0, 0.0, msg, 2048)
    print("ret=%d %s" % (ret, msg.value.decode("utf-8", "replace")[:70]))
    if ret != 0:
        return 1
    b = open(raw_out, "rb").read()

    set_in, set_out = [], []
    for i in range(w * h):
        o = i * 4
        if is_skin(rgba[o], rgba[o + 1], rgba[o + 2]):
            set_in.append(i)
        if is_skin(b[o], b[o + 1], b[o + 2]):
            set_out.append(i)
    print("输入肤色集 %d (%.1f%%)   输出肤色集 %d (%.1f%%)"
          % (len(set_in), 100.0 * len(set_in) / (w * h),
             len(set_out), 100.0 * len(set_out) / (w * h)))

    def stat(s):
        d0 = d1 = l0 = l1 = 0.0
        for i in s:
            o = i * 4
            d0 += rgba[o] - rgba[o + 2]
            d1 += b[o] - b[o + 2]
            l0 += 0.299 * rgba[o] + 0.587 * rgba[o + 1] + 0.114 * rgba[o + 2]
            l1 += 0.299 * b[o] + 0.587 * b[o + 1] + 0.114 * b[o + 2]
        n = len(s)
        return d1 / n - d0 / n, l1 / n - l0 / n

    dr_in, dl_in = stat(set_in)
    dr_out, dl_out = stat(set_out)
    print("")
    print("口径                dRed    dLuma")
    print("-" * 44)
    print("输入肤色集（正确）  %+6.2f  %+6.2f" % (dr_in, dl_in))
    print("输出肤色集（回归用）%+6.2f  %+6.2f" % (dr_out, dl_out))
    print("")
    print("=> 九项回归把红润高报了 %.1f 个 dRed，把变暗少报了 %.1f 个 dLuma"
          % (dr_out - dr_in, dl_in - dl_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
