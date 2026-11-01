# -*- coding: utf-8 -*-
"""单独一个进程转储掩码（钩子只在进程内首帧之后稳定，必须独立进程跑）。"""
import os
import sys

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

open("dump_mask.txt", "w").write("on")
fp.clear_logs()
ret, msg = fp.run_seq(os.path.join("flick", "static"),
                      os.path.join("flick", "p302_mask_out"), "0:50")
print("ret=%d %s" % (ret, msg))
