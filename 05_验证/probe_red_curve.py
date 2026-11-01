# -*- coding: utf-8 -*-
"""扫描 SDK red_level 的真实有效范围，判断「红润偏弱」是映射保守还是 SDK 上限。

做法：面板红润恒 0，改用 BEAUTY_EXTRA_PARAMS_FILE 直接把 red_level 怼到目标值，
在固定皮肤像素集上测 dRed / dLuma / dSat。若 red_level > 1 仍线性生效，说明
我们面板 100 -> sdk 1.0 的映射太保守，直接放宽映射即可，不必自己写 CPU 曲线。
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

W, H = 640, 394
RAW = os.path.join(HERE, "probe_in.raw")


def is_skin(r, g, b):
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b
    if y < 30 or not (77 <= cb <= 127) or not (133 <= cr <= 173):
        return False
    mx, mn = max(r, g), min(r, g)
    mx = max(mx, b); mn = min(mn, b)
    if mx > 0 and (mx - mn) / mx > 0.55:
        return False
    return True


def main():
    img = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "frame_0.png")
    rgba, w, h = read_png_rgba(img)
    raw_in = os.path.join(OUT, "_rd_in.raw")
    raw_out = os.path.join(OUT, "_rd_out.raw")
    open(raw_in, "wb").write(rgba)

    skin = []
    for i in range(w * h):
        o = i * 4
        if is_skin(rgba[o], rgba[o + 1], rgba[o + 2]):
            skin.append(i)
    n = len(skin)
    print("固定皮肤像素集：%d / %d (%.1f%%)  %dx%d" % (n, w * h, 100.0 * n / (w * h), w, h))

    sl0 = sr0 = ss0 = 0.0
    for i in skin:
        o = i * 4
        r, g, b = rgba[o], rgba[o + 1], rgba[o + 2]
        sl0 += 0.299 * r + 0.587 * g + 0.114 * b
        sr0 += r - b
        mx, mn = max(r, g, b), min(r, g, b)
        ss0 += 0.0 if mx == 0 else (mx - mn) / mx

    open(os.path.join(HERE, "panel.txt"), "w").write("3:0")   # 面板红润关掉
    os.environ["BEAUTY_EXTRA_PARAMS_FILE"] = EXTRA

    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int]

    print("")
    print("red_level    dRed    dLuma    dSat   备注")
    print("-" * 56)
    rows = [("panel", 0.0, "3:0"), ("panel", 0.75, "3:75"), ("panel", 1.0, "3:100")]
    rows += [("extra", x, "3:0") for x in [0.0, 0.75, 1.0, 1.5, 2.0, 3.0]]
    for how, x, panel in rows:
        if how == "extra":
            open(EXTRA, "w").write("red_level=%g" % x)
        else:
            open(EXTRA, "w").write("")
        open(os.path.join(HERE, "panel.txt"), "w").write(panel)
        msg = ctypes.create_string_buffer(2048)
        ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                               raw_out.encode("ascii"), w, h, 0.0, 0.0, msg, 2048)
        if ret != 0:
            print("FAIL", msg.value.decode("utf-8", "replace"))
            return 1
        b = open(raw_out, "rb").read()
        sl = sr = ss = 0.0
        for i in skin:
            o = i * 4
            r, g, bb = b[o], b[o + 1], b[o + 2]
            sl += 0.299 * r + 0.587 * g + 0.114 * bb
            sr += r - bb
            mx, mn = max(r, g, bb), min(r, g, bb)
            ss += 0.0 if mx == 0 else (mx - mn) / mx
        note = ""
        if how == "panel" and x == 0.75:
            note = "<- 面板路径（九项回归同参数）"
        if how == "extra" and x == 0.75:
            note = "<- 注入口路径，同值"
        print("%-6s %-6.2f %+7.2f %+7.2f %+7.3f  %s"
              % (how, x, sr / n - sr0 / n, sl / n - sl0 / n, ss / n - ss0 / n, note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
