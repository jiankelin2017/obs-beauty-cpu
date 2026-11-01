# -*- coding: utf-8 -*-
"""诊断：中频带 h_mid = box3 - box7 的幅值分布（整数级）。
midGate 的 Lo/Hi 若高于真实幅值，回填会被整体吃掉。"""
import struct
import sys
import numpy as np
from PIL import Image, ImageFilter

W, H = 1074, 604
img = Image.open("out/frame_0.png").convert("RGB")
a = np.asarray(img).astype(np.int32)
b3 = np.asarray(img.filter(ImageFilter.BoxBlur(1))).astype(np.int32)   # 3x3
b7 = np.asarray(img.filter(ImageFilter.BoxBlur(3))).astype(np.int32)   # 7x7
hf = a - b3
hm = b3 - b7

with open("mask_dump_011.raw", "rb") as f:
    d = f.read()
mw, mh = struct.unpack_from("<ii", d, 0)
n = mw * mh
soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)

ys = (np.arange(H) * mh // H)
xs = (np.arange(W) * mw // W)
m = soft[np.ix_(ys, xs)] > 0
print("掩码内像素 %d / %d (%.1f%%)" % (m.sum(), W * H, 100.0 * m.sum() / (W * H)))

for name, h in (("h_fine(1~2px)", hf), ("h_mid(3~7px)", hm)):
    v = np.abs(h[m])
    print("%s  均值 %.3f  中位 %.0f  p75 %.0f  p90 %.0f  p99 %.0f"
          % (name, v.mean(), np.median(v), np.percentile(v, 75),
             np.percentile(v, 90), np.percentile(v, 99)))
    for lo, hi in ((1, 3), (0, 2), (0, 1)):
        g = np.clip((v - lo) / float(hi - lo), 0, 1)
        print("    门限 Lo=%d Hi=%d -> 平均通过率 %.1f%%" % (lo, hi, 100.0 * g.mean()))
