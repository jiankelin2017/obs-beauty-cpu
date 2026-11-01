# -*- coding: utf-8 -*-
"""跑一档形变序列并导出掩码（供 eval_candidate.py 调用）。

用法: python lag_one.py <fast|mid|slow>
"""
import glob
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

W, H = fp.W, fp.H
COUNT = 12
SCALES = {"fast": 1.20, "mid": 1.12, "slow": 1.05}


def main():
    tag = sys.argv[1]
    end = SCALES[tag]
    src = np.frombuffer(open(os.path.join("flick", "static", "seq_000.raw"), "rb").read(),
                        dtype=np.uint8).reshape(H, W, 4)
    f0 = sorted(glob.glob("mask_dump_*.raw"))
    if f0:
        dd = open(f0[0], "rb").read()
        mw, mh = struct.unpack_from("<ii", dd, 0)
        n = mw * mh
        soft = np.frombuffer(dd[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)
        ys, xs = np.nonzero(soft >= 128)
        ax = xs.mean() * (W - 1) / (mw - 1)
        ay = ys.mean() * (H - 1) / (mh - 1)
    else:
        ax, ay = 531.3, 368.1   # 静态帧的已知掩码质心
    rgb = Image.fromarray(src[:, :, :3])
    d = os.path.join("flick", "sweep_" + tag)
    os.makedirs(d, exist_ok=True)
    for i in range(COUNT):
        s = 1.0 if i < 2 else 1.0 + (end - 1.0) * (i - 1) / 9.0
        a = 1.0 / s
        z = rgb.transform((W, H), Image.AFFINE, (a, 0, ax * (1 - a), 0, a, ay * (1 - a)),
                          resample=Image.BICUBIC)
        np.dstack([np.array(z), src[:, :, 3]]).tofile(os.path.join(d, "seq_%03d.raw" % i))
    out = os.path.join("flick", "sweep_%s_out" % tag)
    os.makedirs(out, exist_ok=True)
    fp.clear_logs()
    open("dump_mask.txt", "w").write("on")
    ret, msg = fp.run_seq(d, out, "0:50,2:50,3:30,4:50")
    if os.path.exists("dump_mask.txt"):
        os.remove("dump_mask.txt")
    print("%s ret=%d %s dumps=%d" % (tag, ret, msg[:60], len(glob.glob("mask_dump_*.raw"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
