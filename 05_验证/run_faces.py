# -*- coding: utf-8 -*-
"""Drive the engine test DLL over real photos and report what the filter does.

Per image:
  * faces reported by the SDK
  * share of pixels the filter changed (whole frame)

Usage:
  python run_faces.py [--blur N] [--whiten N] <image> [...]
"""
import ctypes
import os
import sys

from PIL import Image

DLL = r"C:/legacy_e2e/legacy_engine_test.dll"
ASSET_DIR = r"C:/Program Files/obs-studio/obs-plugins/64bit/obs-beauty"
WORK = r"C:/legacy_e2e/work"
MAX_SIDE = 640


def load_rgba(path):
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    w, h = im.size
    w -= w % 2
    h -= h % 2
    if (w, h) != im.size:
        im = im.crop((0, 0, w, h))
    rgba = bytearray(w * h * 4)
    px = im.tobytes()  # RGB
    rgba[0::4] = px[0::3]
    rgba[1::4] = px[1::3]
    rgba[2::4] = px[2::3]
    rgba[3::4] = b"\xff" * (w * h)
    return w, h, bytes(rgba)


def changed_stats(a, b, w, h):
    n = w * h
    changed = 0
    total = 0
    for i in range(n):
        o = i * 4
        d = max(abs(a[o] - b[o]), abs(a[o + 1] - b[o + 1]), abs(a[o + 2] - b[o + 2]))
        total += d
        if d > 4:
            changed += 1
    return changed, n, total / (n * 3.0)


def main():
    args = sys.argv[1:]
    blur, whiten = 70.0, 0.0
    paths = []
    i = 0
    while i < len(args):
        if args[i] == "--blur":
            blur = float(args[i + 1]); i += 2
        elif args[i] == "--whiten":
            whiten = float(args[i + 1]); i += 2
        else:
            paths.append(args[i]); i += 1
    if not paths:
        print("usage: run_faces.py [--blur N] [--whiten N] <image> [...]")
        return 2

    os.makedirs(WORK, exist_ok=True)
    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int,
    ]
    msg = ctypes.create_string_buffer(2048)

    print("blur=%.0f whiten=%.0f" % (blur, whiten))
    for p in paths:
        name = os.path.basename(p)
        w, h, rgba = load_rgba(p)
        raw_in = os.path.join(WORK, "in.raw")
        raw_out = os.path.join(WORK, "out.raw")
        open(raw_in, "wb").write(rgba)

        ret = dll.LegacySelfTest(
            ASSET_DIR.encode("ascii"), raw_in.encode("ascii"), raw_out.encode("ascii"),
            w, h, blur, whiten, msg, 2048)
        text = msg.value.decode("utf-8", "replace")
        if ret != 0:
            print("%-18s %dx%d FAIL ret=%d %s" % (name, w, h, ret, text))
            continue

        out = open(raw_out, "rb").read()
        changed, n, mean = changed_stats(rgba, out, w, h)
        print("%-18s %dx%d  %s" % (name, w, h, text))
        print("%-18s   changed=%d/%d (%.2f%%) mean|d|=%.3f"
              % ("", changed, n, 100.0 * changed / n, mean))
    return 0


if __name__ == "__main__":
    sys.exit(main())
