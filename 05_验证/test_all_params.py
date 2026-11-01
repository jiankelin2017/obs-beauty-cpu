# -*- coding: utf-8 -*-
"""Measure all 9 effects under region=on vs region=off.

For each effect: drive the engine at a strong value and report how much of the
frame it actually changed. The gap between the two columns is exactly what the
skin mask is swallowing.

Usage: python test_all_params.py <image>
"""
import ctypes
import os
import sys

from PIL import Image

DLL = r"C:/legacy_e2e/legacy_engine_test.dll"
ASSET_DIR = r"C:/Program Files/obs-studio/obs-plugins/64bit/obs-beauty"
WORK = r"C:/legacy_e2e/work"
MAX_SIDE = 640

# order must match the enum in legacy_engine.h. Values are PANEL scale 0..100.
EFFECTS = [
    (0, "blur      磨皮", 100.0),
    (1, "clarity   清晰", 100.0),
    (2, "whiten    美白", 100.0),
    (3, "red       红润", 100.0),
    (4, "sharpen   锐化", 100.0),
    (5, "threed    五官立体", 100.0),
    (6, "eyebright 亮眼", 100.0),
    (7, "pouch     去黑眼圈", 100.0),
    (8, "nasolabial去法令纹", 100.0),
]


def load_rgba(path):
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
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
    return w, h, bytes(rgba)


PANEL_FILE = r"C:/legacy_e2e/panel.txt"


def run(dll, w, h, rgba, value, panel_idx):
    with open(PANEL_FILE, "w") as f:
        f.write(str(panel_idx))
    raw_in = os.path.join(WORK, "in.raw")
    raw_out = os.path.join(WORK, "out.raw")
    open(raw_in, "wb").write(rgba)
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                           raw_out.encode("ascii"), w, h, value, 0.0, msg, 2048)
    if ret != 0:
        return None, msg.value.decode("utf-8", "replace")
    out = open(raw_out, "rb").read()
    n = w * h
    changed = 0
    for i in range(n):
        o = i * 4
        if (abs(rgba[o] - out[o]) > 4 or abs(rgba[o + 1] - out[o + 1]) > 4 or
                abs(rgba[o + 2] - out[o + 2]) > 4):
            changed += 1
    return 100.0 * changed / n, ""


def main():
    args = sys.argv[1:]
    region_off = "--region-off" in args
    args = [a for a in args if a != "--region-off"]
    path = args[0]
    os.makedirs(WORK, exist_ok=True)
    # must be set before the first LegacySelfTest call: regionActive_ is decided
    # once during init and never re-evaluated inside the same process.
    if region_off:
        os.environ["BEAUTY_REGION_OFF"] = "1"
    else:
        os.environ.pop("BEAUTY_REGION_OFF", None)
    w, h, rgba = load_rgba(path)
    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int,
    ]

    print("MODE=%s" % ("region=off" if region_off else "region=on"))
    print("image: %s  (%dx%d)" % (os.path.basename(path), w, h))
    for idx, label, val in EFFECTS:
        pct, err = run(dll, w, h, rgba, val, idx)
        if pct is None:
            print("%-24s ERROR %s" % (label, err))
        else:
            print("%-24s %8.2f%%" % (label, pct))
    return 0


if __name__ == "__main__":
    sys.exit(main())
