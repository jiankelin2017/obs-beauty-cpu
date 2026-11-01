# -*- coding: utf-8 -*-
"""Measure all 9 effects one by one on the same clean input.

For each effect: run at full panel value, then report how much it changed
(coverage) plus the delta in luma / detail / redness / saturation over skin.

Usage: python measure_all_effects.py <image> [--crop L,T,R,B] [--value V]
"""
import ctypes
import os
import sys

from PIL import Image

DLL = r"C:/legacy_e2e/legacy_engine_test.dll"
ASSET_DIR = r"C:/Program Files/obs-studio/obs-plugins/64bit/obs-beauty"
OUT = r"C:/legacy_e2e/out"
PANEL_FILE = r"C:/legacy_e2e/panel.txt"

EFFECTS = [
    (0, "磨皮 blur"),
    (1, "清晰 clarity"),
    (2, "美白 whiten"),
    (3, "红润 red"),
    (4, "锐化 sharpen"),
    (5, "五官立体 threed"),
    (6, "亮眼 eyebright"),
    (7, "去黑眼圈 pouch"),
    (8, "去法令纹 nasolabial"),
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


def skin_set(buf, w, h):
    """肤色像素集。必须在**输入**上判一次，输入输出共用 —— 在输出上重判会让
    效果把像素推过判据边界，输出集整体偏移，测出来的 dRed/dLuma 有一大半是
    集合选择偏差而不是效果（2026-10-25 实测：红润 75 的真值 dRed 是 -0.11，
    输出集口径却给出 +2.92）。"""
    return [i for i in range(w * h)
            if is_skin(buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2])]


def metrics(buf, w, h, skin=None):
    n = 0
    sy = ss = srb = 0.0
    if skin is None:
        skin = skin_set(buf, w, h)
    for i in skin:
        o = i * 4
        r, g, b = buf[o], buf[o + 1], buf[o + 2]
        n += 1
        sy += 0.299 * r + 0.587 * g + 0.114 * b
        mx, mn = max(r, g, b), min(r, g, b)
        ss += 0.0 if mx == 0 else (mx - mn) / mx
        srb += r - b
    if n == 0:
        return None
    return {"luma": sy / n, "sat": ss / n, "red": srb / n, "n": n}


def detail_of(buf, w, h, skin=None):
    def L(i):
        o = i * 4
        return 0.299 * buf[o] + 0.587 * buf[o + 1] + 0.114 * buf[o + 2]

    acc = 0.0
    n = 0
    if skin is None:
        skin = skin_set(buf, w, h)
    for i in skin:
        y, x = divmod(i, w)
        if y == 0 or x == 0 or y == h - 1 or x == w - 1:
            continue
        acc += abs(4 * L(i) - L(i - 1) - L(i + 1) - L(i - w) - L(i + w))
        n += 1
    return acc / n if n else 0.0


def coverage(a, b, w, h):
    n = w * h
    c = 0
    for i in range(n):
        o = i * 4
        if (abs(a[o] - b[o]) > 4 or abs(a[o + 1] - b[o + 1]) > 4 or
                abs(a[o + 2] - b[o + 2]) > 4):
            c += 1
    return 100.0 * c / n


def main():
    args = sys.argv[1:]
    path = args[0]
    crop, value, maxside = None, 75.0, 640
    i = 1
    while i < len(args):
        if args[i] == "--crop":
            crop = tuple(int(v) for v in args[i + 1].split(",")); i += 2
        elif args[i] == "--value":
            value = float(args[i + 1]); i += 2
        elif args[i] == "--max":
            maxside = int(args[i + 1]); i += 2
        else:
            i += 1

    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    im.thumbnail((maxside, maxside), Image.LANCZOS)
    w, h = im.size
    w -= w % 2
    h -= h % 2
    im = im.crop((0, 0, w, h))

    rgba = bytearray(w * h * 4)
    rgb = im.tobytes()
    rgba[0::4] = rgb[0::3]
    rgba[1::4] = rgb[1::3]
    rgba[2::4] = rgb[2::3]
    rgba[3::4] = b"\xff" * (w * h)
    rgba = bytes(rgba)

    os.makedirs(OUT, exist_ok=True)
    raw_in = os.path.join(OUT, "_a_in.raw")
    raw_out = os.path.join(OUT, "_a_out.raw")
    open(raw_in, "wb").write(rgba)

    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int,
    ]
    msg = ctypes.create_string_buffer(2048)

    skin = skin_set(rgba, w, h)
    base = metrics(rgba, w, h, skin)
    base_d = detail_of(rgba, w, h, skin)
    print("input %dx%d  faces=?  skin luma=%.2f detail=%.2f red=%.2f"
          % (w, h, base["luma"], base_d, base["red"]))
    print()
    print("%-22s %7s %8s %8s %8s %8s %8s" %
          ("effect", "cover%", "dLuma", "dDetail", "dRed", "dSat", "faces"))
    print("-" * 76)

    for idx, label in EFFECTS:
        with open(PANEL_FILE, "w") as f:
            f.write(str(idx))
        ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                               raw_out.encode("ascii"), w, h, value, 0.0, msg, 2048)
        if ret != 0:
            print("%-22s FAIL %s" % (label, msg.value.decode("utf-8", "replace")))
            continue
        out = open(raw_out, "rb").read()
        m = metrics(out, w, h, skin)
        d = detail_of(out, w, h, skin)
        txt = msg.value.decode("utf-8", "replace")
        faces = txt.split("faces=")[1].split()[0] if "faces=" in txt else "?"
        print("%-22s %7.2f %+8.2f %+8.2f %+8.2f %+8.3f %8s"
              % (label, coverage(rgba, out, w, h),
                 m["luma"] - base["luma"], d - base_d,
                 m["red"] - base["red"], m["sat"] - base["sat"], faces))
    return 0


if __name__ == "__main__":
    sys.exit(main())
