# -*- coding: utf-8 -*-
"""扫一批 SDK 隐藏参数组合，看谁能补上我们的功能缺口。

用法：python probe_sdk_params.py [image]
每个组合用 BEAUTY_EXTRA_PARAMS_FILE 注入，面板全 0，测 cover/dLuma/dDetail/dRed/dSat。
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

# 每个组合必须**显式写全所有参数**（含置 0）—— 注入口只增量下发，不重置，
# 上一次注入的 red_level 会一直粘在 SDK 里，后面的行全是累积效果（踩过）。
ALL_PARAMS = ["use_new_red", "red_level", "whiten_v2", "use_new_whiten",
              "delspot_level", "tooth_whiten", "eye_bright_v2",
              "remove_pouch_strength_v2", "remove_nasolabial_folds_strength_v2",
              "clarity", "saturation", "blur_level"]


def combo(**kw):
    """kw 里指定的参数用给定值，其余显式置 0，避免粘滞。"""
    return ";".join("%s=%g" % (k, kw.get(k, 0.0)) for k in ALL_PARAMS)


COMBOS = [
    ("基线（全关）", combo()),
    ("red_level=0.75（当前路径）", combo(red_level=0.75)),
    ("use_new_red=1", combo(use_new_red=1)),
    ("use_new_red=1 + red=0.75", combo(use_new_red=1, red_level=0.75)),
    ("use_new_red=1 + red=1.0", combo(use_new_red=1, red_level=1.0)),
    ("use_new_red=1 + red=2.0", combo(use_new_red=1, red_level=2.0)),
    ("whiten_v2=0.75", combo(whiten_v2=0.75)),
    ("delspot_level=0.75", combo(delspot_level=0.75)),
    ("delspot_level=1.0", combo(delspot_level=1.0)),
    ("tooth_whiten=0.75", combo(tooth_whiten=0.75)),
    ("eye_bright_v2=0.75", combo(eye_bright_v2=0.75)),
    ("remove_pouch_v2=0.75", combo(remove_pouch_strength_v2=0.75)),
    ("nasolabial_v2=0.75", combo(remove_nasolabial_folds_strength_v2=0.75)),
    ("clarity=1.0", combo(clarity=1.0)),
    ("saturation=0.5", combo(saturation=0.5)),
    ("blur_level=3", combo(blur_level=3)),
]


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


def detail_of(buf, w, h, skin):
    def L(i):
        o = i * 4
        return 0.299 * buf[o] + 0.587 * buf[o + 1] + 0.114 * buf[o + 2]
    acc = 0.0
    n = 0
    for i in skin:
        y, x = divmod(i, w)
        if y == 0 or x == 0 or y == h - 1 or x == w - 1:
            continue
        acc += abs(4 * L(i) - L(i - 1) - L(i + 1) - L(i - w) - L(i + w))
        n += 1
    return acc / n if n else 0.0


def main():
    img = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "frame_0.png")
    rgba, w, h = read_png_rgba(img)
    raw_in = os.path.join(OUT, "_sp_in.raw")
    raw_out = os.path.join(OUT, "_sp_out.raw")
    open(raw_in, "wb").write(rgba)

    skin = [i for i in range(w * h)
            if is_skin(rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2])]
    n = len(skin)
    b_l = b_r = b_s = b_d = 0.0
    for i in skin:
        o = i * 4
        r, g, bb = rgba[o], rgba[o + 1], rgba[o + 2]
        b_l += 0.299 * r + 0.587 * g + 0.114 * bb
        b_r += r - bb
        mx, mn = max(r, g, bb), min(r, g, bb)
        b_s += 0.0 if mx == 0 else (mx - mn) / mx
    b_l /= n; b_r /= n; b_s /= n
    b_d = detail_of(rgba, w, h, skin)

    open(PANEL, "w").write("")          # 面板全 0，只靠注入口
    os.environ["BEAUTY_EXTRA_PARAMS_FILE"] = EXTRA

    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int]

    print("图 %dx%d，固定皮肤集 %d (%.1f%%)，输入 luma=%.2f red=%.2f detail=%.2f"
          % (w, h, n, 100.0 * n / (w * h), b_l, b_r, b_d))
    print("")
    print("%-34s %7s %8s %8s %8s %8s" % ("组合", "cover%", "dLuma", "dDetail", "dRed", "dSat"))
    print("-" * 78)
    for label, combo in COMBOS:
        open(EXTRA, "w").write(combo)
        msg = ctypes.create_string_buffer(2048)
        ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                               raw_out.encode("ascii"), w, h, 0.0, 0.0, msg, 2048)
        if ret != 0:
            print("%-34s FAIL %s" % (label, msg.value.decode("utf-8", "replace")[:40]))
            continue
        b = open(raw_out, "rb").read()
        sl = sr = ss = 0.0
        cov = 0
        for i in skin:
            o = i * 4
            r, g, bb = b[o], b[o + 1], b[o + 2]
            sl += 0.299 * r + 0.587 * g + 0.114 * bb
            sr += r - bb
            mx, mn = max(r, g, bb), min(r, g, bb)
            ss += 0.0 if mx == 0 else (mx - mn) / mx
            if (abs(r - rgba[o]) > 4 or abs(g - rgba[o + 1]) > 4
                    or abs(bb - rgba[o + 2]) > 4):
                cov += 1
        d = detail_of(b, w, h, skin)
        print("%-34s %7.2f %+8.2f %+8.2f %+8.2f %+8.3f"
              % (label, 100.0 * cov / n, sl / n - b_l, d - b_d, sr / n - b_r, ss / n - b_s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
