# -*- coding: utf-8 -*-
"""测某一噪声幅度下 rawChg / err 的地板（必须独立进程，SDK 状态才干净）。

用法: python measure_floor.py <amp> <panel>
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp
from shape_test import read_dump, soften

amp = int(sys.argv[1])
panel = sys.argv[2] if len(sys.argv) > 2 else "0:50,4:50"

# prep_noisy 写死 ±2，这里按参数自造噪声序列
import random
from measure_whiten_fixed import read_png_rgba
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
ret, msg = fp.run_seq(indir, outdir, panel)
if os.path.exists("dump_mask.txt"):
    os.remove("dump_mask.txt")

files = sorted(glob.glob("mask_dump_*.raw"))
dumps = [read_dump(f) for f in files]
raws = [d[2] for d in dumps]
softs = [d[1] for d in dumps]
sraw = [soften(r) for r in raws]
chg = [float(np.abs(raws[i].astype(np.int16) - raws[i - 1].astype(np.int16)).mean())
       for i in range(1, len(raws))]
err = [float(np.abs(sraw[i].astype(np.int16) - softs[i - 1].astype(np.int16)).mean())
       for i in range(1, len(raws))]
print("amp=%d 帧数=%d ret=%d" % (amp, len(files), ret))
print("  rawChg 均值 %.3f  最大 %.3f" % (float(np.mean(chg)), max(chg)))
print("  err    均值 %.3f  最大 %.3f" % (float(np.mean(err)), max(err)))
