# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.abspath("."))
from analyze_302 import load_mask, load_raw, detail, SCALES
m = load_mask()
inp = load_raw(os.path.join("flick", "static", "seq_011.raw"))
din = {r: detail(inp, r)[m].mean() for r in SCALES}
print("输入细节: " + "  ".join("r%d=%.3f" % (r, din[r]) for r in SCALES))
for tag in ("z0", "z1"):
    p = os.path.join("flick", "p302_%s_out" % tag, "seq_011.raw")
    out = load_raw(p)
    row = "%-4s lum=%6.2f" % (tag, out[m].mean())
    for r in SCALES:
        dv = detail(out, r)[m].mean()
        row += "  r%d %6.3f/%5.1f%%" % (r, dv, 100.0*dv/din[r])
    print(row)
