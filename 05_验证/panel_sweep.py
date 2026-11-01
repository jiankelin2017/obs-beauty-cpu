# -*- coding: utf-8 -*-
"""3.0.8 磨皮滑块全行程：面板值 → 掩码内细节保留率。"""
import os, shutil, struct, sys
sys.path.insert(0, os.path.abspath("."))
import numpy as np
from PIL import Image, ImageFilter
import flicker_probe as fp

W, H = 1074, 604
SC = (1, 2, 3)

def mask_from(p):
    d = open(p, "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)
    ys = np.arange(H) * mh // H
    xs = np.arange(W) * mw // W
    return soft[np.ix_(ys, xs)] > 0

def load_raw(p):
    b = open(p, "rb").read()
    return np.frombuffer(b, dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.float32)

def detail(a, r):
    im = Image.fromarray(a.astype(np.uint8))
    sm = np.asarray(im.filter(ImageFilter.BoxBlur(r))).astype(np.float32)
    return np.abs(a - sm).mean(axis=2)

shutil.copy("mask_dump_048.raw", "mask_keep.raw")
m = mask_from("mask_keep.raw")
indir = os.path.join("flick", "static")
inp = load_raw(os.path.join(indir, "seq_011.raw"))
din = {r: detail(inp, r)[m].mean() for r in SC}

print("面板磨皮  亮度      r1 保留   r2 保留   r3 保留")
for v in (0, 5, 10, 25, 50, 75, 100):
    od = os.path.join("flick", "pw_%03d" % v)
    os.makedirs(od, exist_ok=True)
    fp.clear_logs()
    ret, msg = fp.run_seq(indir, od, "0:%d" % v)
    if ret != 0:
        print("  %3d  FAIL %s" % (v, msg)); continue
    out = load_raw(os.path.join(od, "seq_011.raw"))
    row = "  %3d    %6.2f" % (v, out[m].mean())
    for r in SC:
        row += "   %5.1f%%" % (100.0 * detail(out, r)[m].mean() / din[r].mean())
    print(row)
