# -*- coding: utf-8 -*-
"""Run the engine on a real screenshot crop and report luma before/after.

Lets us check whether our whiten N actually reaches the brightness lift that
the competing plugin gets at the same panel value.

Usage: python measure_whiten.py <image> --crop L,T,R,B --panel N --value V
"""
import ctypes
import os
import sys

from PIL import Image

DLL = r"C:/legacy_e2e/legacy_engine_test.dll"
ASSET_DIR = r"C:/Program Files/obs-studio/obs-plugins/64bit/obs-beauty"
OUT = r"C:/legacy_e2e/out"
PANEL_FILE = r"C:/legacy_e2e/panel.txt"


def is_skin(r, g, b):
    """Same YCbCr rule as compare_beauty.py, so numbers stay comparable."""
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b
    if y < 30 or not (77 <= cb <= 127) or not (133 <= cr <= 173):
        return False
    mx, mn = max(r, g, b), min(r, g, b)
    if mx > 0 and (mx - mn) / mx > 0.55:
        return False
    return True


def luma_stats(buf, w, h):
    n = 0
    s = 0.0
    for i in range(w * h):
        o = i * 4
        r, g, b = buf[o], buf[o + 1], buf[o + 2]
        if not is_skin(r, g, b):
            continue
        n += 1
        s += 0.299 * r + 0.587 * g + 0.114 * b
    return (s / n if n else 0.0), n


def detail_of(buf, w, h):
    """Mean |Laplacian| on luma over skin pixels."""
    def L(i):
        o = i * 4
        return 0.299 * buf[o] + 0.587 * buf[o + 1] + 0.114 * buf[o + 2]

    acc = 0.0
    n = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            o = i * 4
            if not is_skin(buf[o], buf[o + 1], buf[o + 2]):
                continue
            acc += abs(4 * L(i) - L(i - 1) - L(i + 1) - L(i - w) - L(i + w))
            n += 1
    return acc / n if n else 0.0


def main():
    args = sys.argv[1:]
    path = args[0]
    crop, panel, value = None, None, 75.0
    resize = None
    i = 1
    while i < len(args):
        if args[i] == "--crop":
            crop = tuple(int(v) for v in args[i + 1].split(",")); i += 2
        elif args[i] == "--size":
            resize = tuple(int(v) for v in args[i + 1].split("x")); i += 2
        elif args[i] == "--panel":
            panel = args[i + 1]; i += 2
        elif args[i] == "--value":
            value = float(args[i + 1]); i += 2
        else:
            i += 1

    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if resize:
        im = im.resize(resize, Image.LANCZOS)
    w, h = im.size

    rgba = bytearray(w * h * 4)
    rgb = im.tobytes()
    rgba[0::4] = rgb[0::3]
    rgba[1::4] = rgb[1::3]
    rgba[2::4] = rgb[2::3]
    rgba[3::4] = b"\xff" * (w * h)
    rgba = bytes(rgba)

    os.makedirs(OUT, exist_ok=True)
    raw_in = os.path.join(OUT, "_w_in.raw")
    raw_out = os.path.join(OUT, "_w_out.raw")
    open(raw_in, "wb").write(rgba)
    if panel is not None:
        with open(PANEL_FILE, "w") as f:
            f.write(panel)

    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int,
    ]
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                           raw_out.encode("ascii"), w, h, value, 0.0, msg, 2048)
    if ret != 0:
        print("FAIL", msg.value.decode("utf-8", "replace"))
        return 1

    out = open(raw_out, "rb").read()
    a, na = luma_stats(rgba, w, h)
    b, nb = luma_stats(out, w, h)
    da = detail_of(rgba, w, h)
    db = detail_of(out, w, h)
    print("  engine says: %s" % msg.value.decode("utf-8", "replace"))
    print("panel=%s value=%.0f" % (panel, value))
    print("  skin px: %d -> %d" % (na, nb))
    print("  skin luma: %.2f -> %.2f  (%+.2f)" % (a, b, b - a))
    print("  detail:    %.2f -> %.2f  (%+.2f)" % (da, db, db - da))
    return 0


if __name__ == "__main__":
    sys.exit(main())
