# -*- coding: utf-8 -*-
"""背景保护的**对照组**：同一参数在同一进程里跑两遍，看「纯状态漂移」有多大。

如果 s50 与 s50 之间掩码外也有 ~150 px @1 级差异，那 base vs s50 的差异就不
能算成「越界」，只能算测量噪声（fuai 掩码本身跨调用有 1 像素级漂移）。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

W, H = 1074, 604


def run(tag, panel):
    outdir = os.path.join("flick", "ctl_%s_out" % tag)
    os.makedirs(outdir, exist_ok=True)
    fp.clear_logs()
    ret, msg = fp.run_seq(os.path.join("flick", "static"), outdir, panel)
    print("%-8s panel=%-16s ret=%d %s" % (tag, panel, ret, msg))
    return outdir


def load(p):
    return np.frombuffer(open(p, "rb").read(), dtype=np.uint8).reshape(
        H, W, 4)[:, :, :3].astype(np.int32)


def main():
    a = run("a", "0:50,4:50")
    b = run("b", "0:50,4:50")
    src = load("flick/static/seq_000.raw")
    da = load(os.path.join(a, "seq_000.raw"))
    db = load(os.path.join(b, "seq_000.raw"))
    d = np.abs(da - db).max(axis=2)
    n = int((d > 0).sum())
    print("\n同参数两次运行（s50 vs s50，frame 0）：")
    print("  有差异像素 %d  最大 %d 级  均值 %.4f"
          % (n, int(d.max()), float(d[d > 0].mean()) if n else 0.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
