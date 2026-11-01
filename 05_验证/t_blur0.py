# -*- coding: utf-8 -*-
"""面板磨皮=0（无任何 SDK 参数）时的细节保留率，判断是否绕过 SDK。"""
import os, sys
sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

indir = os.path.join("flick", "static")
for tag, panel in (("z0", "0:0"), ("z1", "0:1")):
    outdir = os.path.join("flick", "p302_%s_out" % tag)
    os.makedirs(outdir, exist_ok=True)
    fp.clear_logs()
    ret, msg = fp.run_seq(indir, outdir, panel)
    print("%-4s panel=%-6s ret=%d %s" % (tag, panel, ret, msg))
