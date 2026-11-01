# -*- coding: utf-8 -*-
"""跑一档噪声序列并导出掩码（供 eval_candidate.py 调用）。

用法: python floor_one.py <amp>
"""
import glob
import os
import random
import sys

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp
from measure_whiten_fixed import read_png_rgba

amp = int(sys.argv[1])
indir = os.path.join("flick", "noisy%d" % amp)
os.makedirs(indir, exist_ok=True)
rgba, w, h = read_png_rgba("out/frame_0.png")
assert (w, h) == (fp.W, fp.H)
rnd = random.Random(20261025)
for k in range(fp.COUNT):
    b = bytearray(rgba)
    for i in range(0, len(b), 4):
        for c in range(3):
            v = b[i + c] + rnd.randint(-amp, amp)
            b[i + c] = 0 if v < 0 else (255 if v > 255 else v)
    open(os.path.join(indir, "seq_%03d.raw" % k), "wb").write(bytes(b))
outdir = os.path.join("flick", "floor_%d_out" % amp)
os.makedirs(outdir, exist_ok=True)
fp.clear_logs()
open("dump_mask.txt", "w").write("on")
ret, msg = fp.run_seq(indir, outdir, "0:50,2:50,3:30,4:50")
if os.path.exists("dump_mask.txt"):
    os.remove("dump_mask.txt")
print("amp=%d ret=%d dumps=%d" % (amp, ret, len(glob.glob("mask_dump_*.raw"))))
