# -*- coding: utf-8 -*-
"""候选阈值两端验证：拖尾（形变序列）+ 抗闪（噪声序列）必须同时达标。

死区必须高于噪声地板（±5: rawChg 0.19 / err 0.19），斜率要陡才能压住中等
速度的拖尾。这里把形变三档和噪声三档都跑一遍。
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp
from shape_test import soften, read_dump, chain_305

COUNT = 12
CANDS = [
    ("3.0.5 现值 chg.40/3.0 err.30/1.5", 0.40, 3.00, 0.30, 1.50),
    ("D            chg.35/1.0 err.32/0.8", 0.35, 1.00, 0.32, 0.80),
    ("E            chg.35/0.9 err.30/0.7", 0.35, 0.90, 0.30, 0.70),
]


def load_seq(tag, n=COUNT):
    files = sorted(glob.glob("mask_dump_*.raw"))[-n:]
    dumps = [read_dump(f) for f in files]
    return [d[2] for d in dumps], [d[1] for d in dumps]


def trailing(series, sraw):
    return [float(np.abs(series[i].astype(np.int16) - sraw[i].astype(np.int16)).mean())
            for i in range(len(series))]


def residual(series):
    """输出掩码的帧间|Δ|（过渡带），抗闪指标。"""
    out = []
    for i in range(1, len(series)):
        a, b = series[i - 1], series[i]
        m = ((a > 0) & (a < 250)) | ((b > 0) & (b < 250))
        d = np.abs(b.astype(np.int16) - a.astype(np.int16))[m]
        out.append(float(d.mean()) if d.size else 0.0)
    return float(np.mean(out)), float(np.max(out)) if out else 0.0


def main():
    print("== 形变三档：稳态拖尾（级，越小越跟得上）==")
    deform = {}
    for tag in ("fast", "mid", "slow"):
        files = sorted(glob.glob("mask_dump_*.raw"))
        # 形变序列的转储在 sweep_*_out 运行之后已经不在了，现场重跑
        os.system(r'"C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe"'
                  r' lag_one.py %s > NUL 2>&1' % tag)
        raws, actual = load_seq(tag)
        sraw = [soften(r) for r in raws]
        deform[tag] = (raws, sraw, actual)
        line = ["  %-5s" % tag]
        for name, lo, hi, elo, ehi in CANDS:
            if name.startswith("3.0.5"):
                t = trailing(actual, sraw)
            else:
                t = trailing(chain_305(raws, k_lo=lo, k_hi=hi, e_lo=elo, e_hi=ehi), sraw)
            line.append("%s %.2f" % (name.split()[0], float(np.mean(t[2:]))))
        print("  ".join(line))
    print("        （三列依次 = 3.0.5现值 / D / E 的稳态拖尾）")

    print("\n== 噪声三档：输出掩码帧间残差（级，越小越不闪）==")
    for amp in (2, 5, 12):
        files = sorted(glob.glob("mask_dump_*.raw"))
        os.system(r'"C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe"'
                  r' floor_one.py %d > NUL 2>&1' % amp)
        raws, actual = load_seq("n%d" % amp)
        line = ["  ±%-2d" % amp]
        for name, lo, hi, elo, ehi in CANDS:
            if name.startswith("3.0.5"):
                r = residual(actual)
            else:
                r = residual(chain_305(raws, k_lo=lo, k_hi=hi, e_lo=elo, e_hi=ehi))
            line.append("%s %.3f/%.2f" % (name.split()[0], r[0], r[1]))
        print("  ".join(line))
    print("        （三列依次 = 3.0.5现值 / D / E 的 残差均值/最大值）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
