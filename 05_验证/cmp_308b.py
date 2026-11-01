# -*- coding: utf-8 -*-
"""3.0.8 前后纹理对比图（只做裁剪拼接，序列已由 run_one.py 生成）。"""
import os, struct, sys
sys.path.insert(0, os.path.abspath("."))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1074, 604

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
    return np.frombuffer(b, dtype=np.uint8).reshape(H, W, 4)[:, :, :3]

m = mask_from("mask_keep.raw")
inp = load_raw(os.path.join("flick", "static", "seq_011.raw"))
old = load_raw(os.path.join("flick", "cmp_old", "seq_011.raw"))
new = load_raw(os.path.join("flick", "cmp_new", "seq_011.raw"))

S = 120
best, bxy = -1, (0, 0)
sm = np.asarray(Image.fromarray(inp).filter(ImageFilter.BoxBlur(1))).astype(np.float32)
hp = np.abs(inp.astype(np.float32) - sm).mean(axis=2)
for y in range(0, H - S, 20):
    for x in range(0, W - S, 20):
        if m[y:y+S, x:x+S].all():
            sc = hp[y:y+S, x:x+S].mean()
            if sc > best:
                best, bxy = sc, (x, y)
print("选中方块 x=%d y=%d 纹理=%.3f" % (bxy[0], bxy[1], best))

# 逐块的高频 std，作为图注数字
def hf(a):
    s = np.asarray(Image.fromarray(a[y0:y0+S, x0:x0+S]).filter(ImageFilter.BoxBlur(1))).astype(np.float32)
    return (a[y0:y0+S, x0:x0+S].astype(np.float32) - s).std()

x0, y0 = bxy
vals = [hf(a) for a in (inp, old, new)]
crops = [Image.fromarray(a[y0:y0+S, x0:x0+S]) for a in (inp, old, new)]
labels = ["INPUT", "3.0.7 blur50", "3.0.8 blur50"]
Z = 3
crops = [c.resize((S*Z, S*Z), Image.NEAREST) for c in crops]
PAD, TOP = 8, 28
out = Image.new("RGB", (len(crops)*S*Z + (len(crops)+1)*PAD, S*Z + TOP + 2*PAD), (24, 24, 28))
d = ImageDraw.Draw(out)
for i, (c, lb) in enumerate(zip(crops, labels)):
    ox = PAD + i*(S*Z + PAD)
    out.paste(c, (ox, TOP))
    d.text((ox + 2, 6), "%s  hf=%.2f" % (lb, vals[i]), fill=(235, 235, 235))
os.makedirs("out", exist_ok=True)
p = os.path.abspath("out/cmp_308.png")
out.save(p)
print("已保存", p, out.size)
print("高频 std: " + "  ".join("%s=%.3f" % (l, v) for l, v in zip(labels, vals)))
