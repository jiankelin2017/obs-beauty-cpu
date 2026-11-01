# -*- coding: utf-8 -*-
"""3.0.2 中频带回填：参数对照运行器。

同一静态帧（out/frame_0.png × 12）跑四组面板，输出到独立目录，
便于 analyze_302.py 做掩码内多尺度细节对比。
  base  磨皮50              中频增益 0（纯磨皮对照）
  s50   磨皮50 + 锐化50      中频 0.65 / 细频 0.5
  s100  磨皮50 + 锐化100     中频 1.30 / 细频 1.0
  c100  磨皮50 + 锐化50 + 清晰100   中频 1.15 / 细频 0.5
"""
import os
import sys

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

CASES = (
    ("base", "0:50"),
    ("s50",  "0:50,4:50"),
    ("s100", "0:50,4:100"),
    ("c100", "0:50,1:100,4:50"),
)


def main():
    indir = os.path.join("flick", "static")
    os.makedirs(indir, exist_ok=True)
    if not os.path.exists(os.path.join(indir, "seq_000.raw")):
        fp.prep_static(indir)
    for tag, panel in CASES:
        outdir = os.path.join("flick", "p302_%s_out" % tag)
        os.makedirs(outdir, exist_ok=True)
        fp.clear_logs()
        ret, msg = fp.run_seq(indir, outdir, panel)
        print("%-5s panel=%-18s ret=%d %s" % (tag, panel, ret, msg))
    # 掩码与面板无关，单独转一份给分析用
    open("dump_mask.txt", "w").write("on")
    fp.clear_logs()
    fp.run_seq(indir, os.path.join("flick", "p302_mask_out"), "0:50")
    if os.path.exists("dump_mask.txt"):
        os.remove("dump_mask.txt")
    print("mask dump done")


if __name__ == "__main__":
    main()
