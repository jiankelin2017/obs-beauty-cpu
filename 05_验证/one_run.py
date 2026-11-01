# -*- coding: utf-8 -*-
"""单配置单进程跑一遍（避免同进程多次运行的 SDK 时序状态污染）。"""
import os
import sys

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

indir, outdir, panel = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(outdir, exist_ok=True)
print(fp.run_seq(indir, outdir, panel))
