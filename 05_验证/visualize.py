# -*- coding: utf-8 -*-
"""Render a side-by-side proof sheet: original | processed | where it changed.

Usage:
  python visualize.py <image> [--blur N] [--whiten N] [--out name.png]
"""
import ctypes
import os
import sys

from PIL import Image

DLL = r"C:/legacy_e2e/legacy_engine_test.dll"
ASSET_DIR = r"C:/Program Files/obs-studio/obs-plugins/64bit/obs-beauty"
OUTDIR = r"C:/legacy_e2e/out"
MAX_SIDE = 640


def main():
    args = sys.argv[1:]
    blur, whiten, outname, panel = 70.0, 0.0, None, None
    path = None
    i = 0
    while i < len(args):
        if args[i] == "--blur":
            blur = float(args[i + 1]); i += 2
        elif args[i] == "--whiten":
            whiten = float(args[i + 1]); i += 2
        elif args[i] == "--panel":
            panel = args[i + 1]; i += 2
        elif args[i] == "--out":
            outname = args[i + 1]; i += 2
        else:
            path = args[i]; i += 1
    if not path:
        print("usage: visualize.py <image> [--blur N] [--whiten N] [--out name.png]")
        return 2

    os.makedirs(OUTDIR, exist_ok=True)
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
    rgba = bytes(rgba)

    raw_in = os.path.join(OUTDIR, "_in.raw")
    raw_out = os.path.join(OUTDIR, "_out.raw")
    open(raw_in, "wb").write(rgba)
    if panel is not None:
        with open(r"C:/legacy_e2e/panel.txt", "w") as f:
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
                           raw_out.encode("ascii"), w, h, blur, whiten, msg, 2048)
    text = msg.value.decode("utf-8", "replace")
    print("ret=%d %s" % (ret, text))
    if ret != 0:
        return 1

    out = open(raw_out, "rb").read()

    # highlight map: changed pixels in red, original dimmed underneath
    hi = Image.new("RGB", (w, h))
    hip = bytearray(w * h * 3)
    n = w * h
    changed = 0
    for k in range(n):
        o = k * 4
        d = max(abs(rgba[o] - out[o]), abs(rgba[o + 1] - out[o + 1]),
                abs(rgba[o + 2] - out[o + 2]))
        if d > 4:
            changed += 1
            hip[k * 3] = 255
            hip[k * 3 + 1] = 0
            hip[k * 3 + 2] = 0
        else:
            g = (rgba[o] + rgba[o + 1] + rgba[o + 2]) // 3
            g = 40 + g * 3 // 4
            hip[k * 3] = g
            hip[k * 3 + 1] = g
            hip[k * 3 + 2] = g
    hi = Image.frombytes("RGB", (w, h), bytes(hip))

    pb = bytearray(w * h * 3)
    pb[0::3] = out[0::4]
    pb[1::3] = out[1::4]
    pb[2::3] = out[2::4]
    proc = Image.frombytes("RGB", (w, h), bytes(pb))

    sheet = Image.new("RGB", (w * 3 + 20, h), (20, 20, 20))
    sheet.paste(im, (0, 0))
    sheet.paste(proc, (w + 10, 0))
    sheet.paste(hi, (w * 2 + 20, 0))

    name = outname or (os.path.splitext(os.path.basename(path))[0] + ".png")
    dst = os.path.join(OUTDIR, name)
    sheet.save(dst)
    print("changed=%d/%d (%.2f%%)  -> %s" % (changed, n, 100.0 * changed / n, dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
