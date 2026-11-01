# -*- coding: utf-8 -*-
"""静态 12 帧逐帧差异探针：可指定 DLL，用来判断「帧 7 的阶跃」是不是新引入。

用法：python static_probe.py <dll路径> [panel]
"""
import os
import sys

HERE = os.path.abspath(".")
sys.path.insert(0, HERE)
import flicker_probe as fp

dll = sys.argv[1]
panel = sys.argv[2] if len(sys.argv) > 2 else "0:50,2:50,3:30,4:50"
fp.DLL = os.path.abspath(dll)

indir = os.path.join(HERE, "flick", "static")
fp.prep_static(indir)
outdir = os.path.join(HERE, "flick", "static_probe_out")
os.makedirs(outdir, exist_ok=True)
fp.clear_logs()
open(os.path.join(HERE, "dump_mask.txt"), "w").write("on")
ret, msg = fp.run_seq(indir, outdir, panel)
if os.path.exists(os.path.join(HERE, "dump_mask.txt")):
    os.remove(os.path.join(HERE, "dump_mask.txt"))
print("%s  ret=%d  %s" % (os.path.basename(dll), ret, msg))
for r in fp.parse_seq_log():
    print("  帧 %-3s faces=%s cov=%-7s infer=%-3s 平均差=%-8s 变化px=%-7s 最大差=%s"
          % (r["seq"], r["faces"], r["cov"], r["infer"],
             r["meanAbs"], r["chgPx"], r["maxDiff"]))
inf = fp.parse_infer_log()
print("  推理 %d 次" % len(inf))
for r in inf:
    print("    infer frame=%s mask=%s %dx%d cov=%s"
          % (r["frame"], r["mask"], r["mw"], r["mh"], r["cov"]))
