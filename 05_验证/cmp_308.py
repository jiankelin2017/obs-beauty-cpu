# -*- coding: utf-8 -*-
"""3.0.8 前后纹理对比图：输入 / 3.0.7(磨皮50) / 3.0.8(磨皮50)。"""
import os, shutil, struct, sys
sys.path.insert(0, os.path.abspath("."))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import flicker_probe as fp

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

shutil.copy("mask_dump_048.raw", "mask_keep.raw")
m = mask_from("mask_keep.raw")
indir = os.path.join("flick", "static")

# 3.0.7 等价：t=1（面板100）+ blur_level 强制回 3.0
open("extra_blur.txt", "w").write("blur_level=3.0\n")
env_old = dict(os.environ, BEAUTY_EXTRA_PARAMS_FILE=os.path.abspath("extra_blur.txt"))
for tag, panel, env in (("old", "0:100", env_old), ("new", "0:50", None)):
    od = os.path.join("flick", "cmp_%s" % tag)
    os.makedirs(od, exist_ok=True)
    fp.clear_logs()
    ret, msg = fp.run_seq(indir, od, panel, env=env) if env else fp.run_seq(indir, od, panel)
    print("%-4s panel=%-7s ret=%d" % (tag, panel, ret))

inp = load_raw(os.path.join(indir, "seq_011.raw"))
old = load_raw(os.path.join("flick", "cmp_old", "seq_011.raw"))
new = load_raw(os.path.join("flick", "cmp_new", "seq_011.raw"))

# 在掩码内找一块 120x120、纹理最丰富（且完全在掩码内）的方块
S = 120
best, bxy = -1, (0, 0)
im = Image.fromarray(inp)
sm = np.asarray(im.filter(ImageFilter.BoxBlur(1))).astype(np.float32)
hp = np.abs(inp.astype(np.float32) - sm).mean(axis=2)
for y in range(0, H - S, 20):
    for x in range(0, W - S, 20):
        if m[y:y+S, x:x+S].all():
            sc = hp[y:y+S, x:x+S].mean()
            if sc > best:
                best, bxy = sc, (x, y)
print("选中方块 x=%d y=%d 纹理=%.3f" % (bxy[0], bxy[1], best))

x0, y0 = bxy
crops = [Image.fromarray(a[y0:y0+S, x0:x0+S]) for a in (inp, old, new)]
labels = ["INPUT", "3.0.7 blur50", "3.0.8 blur50"]
Z = 3
crops = [c.resize((S*Z, S*Z), Image.NEAREST) for c in crops]
PAD, TOP = 8, 26
out = Image.new("RGB", (len(crops)*S*Z + (len(crops)+1)*PAD, S*Z + TOP + 2*PAD), (24, 24, 28))
d = ImageDraw.Draw(out)
for i, (c, lb) in enumerate(zip(crops, labels)):
    ox = PAD + i*(S*Z + PAD)
    out.paste(c, (ox, TOP))
    d.text((ox + 2, 7), lb, fill=(235, 235, 235))
os.makedirs("out", exist_ok=True)
p = os.path.abspath("out/cmp_308.png")
out.save(p)
print("已保存", p, out.size)
