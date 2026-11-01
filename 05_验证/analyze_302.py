# -*- coding: utf-8 -*-
"""3.0.2 掩码内多尺度细节对比。

整帧指标对掩码内改动不敏感（掩码只占 16.5%），必须只在掩码内统计：
  detail_r = mean|img - BoxBlur(r)|   over {mask > 0}
保留率 = out / in（in = 同一静态输入帧）。
"""
import os
import struct

import numpy as np
from PIL import Image, ImageFilter

W, H = 1074, 604
CASES = ("base", "s50", "s100", "c100")
SCALES = (1, 2, 3, 5)


def load_mask():
    d = open("mask_dump_048.raw", "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)
    ys = np.arange(H) * mh // H
    xs = np.arange(W) * mw // W
    return soft[np.ix_(ys, xs)] > 0


def load_raw(p):
    with open(p, "rb") as f:
        b = f.read()
    a = np.frombuffer(b, dtype=np.uint8).reshape(H, W, 4)[:, :, :3]
    return a.astype(np.float32)


def detail(a, r):
    im = Image.fromarray(a.astype(np.uint8))
    sm = np.asarray(im.filter(ImageFilter.BoxBlur(r))).astype(np.float32)
    return np.abs(a - sm).mean(axis=2)


def main():
    m = load_mask()
    inp = load_raw(os.path.join("flick", "static", "seq_011.raw"))
    din = {r: detail(inp, r)[m] for r in SCALES}
    print("掩码内像素 %d，输入细节：" % m.sum())
    print("  " + "  ".join("r%d=%.3f" % (r, din[r].mean()) for r in SCALES))
    print()
    hdr = "%-6s %7s" % ("组", "亮度")
    for r in SCALES:
        hdr += " %14s" % ("r%d 细节/保留" % r)
    print(hdr)
    for tag in CASES:
        out = load_raw(os.path.join("flick", "p302_%s_out" % tag, "seq_011.raw"))
        lum = out[m].mean()
        row = "%-6s %7.2f" % (tag, lum)
        for r in SCALES:
            dv = detail(out, r)[m].mean()
            row += " %6.3f/%6.1f%%" % (dv, 100.0 * dv / din[r].mean())
        print(row)


if __name__ == "__main__":
    main()
