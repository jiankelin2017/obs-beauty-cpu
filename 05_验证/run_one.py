# -*- coding: utf-8 -*-
"""按给定面板跑一组序列（env 由父进程传入）。"""
import os, sys
sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp
tag, panel = sys.argv[1], sys.argv[2]
od = os.path.join("flick", tag)
os.makedirs(od, exist_ok=True)
fp.clear_logs()
ret, msg = fp.run_seq(os.path.join("flick", "static"), od, panel)
print("%s ret=%d" % (tag, ret))
