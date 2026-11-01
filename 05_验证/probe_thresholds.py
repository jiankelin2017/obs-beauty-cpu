# -*- coding: utf-8 -*-
"""用 DLL 内部细节层探针比较自适应阈值候选。

只对测试副本有效（生产源码没有 BEAUTY_DETAIL_PROBE）。
每个候选起独立进程，因为探针的阈值在进程内只读一次。
"""
import os
import statistics
import subprocess
import sys

HERE = os.path.abspath(".")
CHILD = r'''
import os, sys
sys.path.insert(0, os.getcwd())
import flicker_probe as f
scen = sys.argv[1]
tag = sys.argv[2]
d = os.path.join("flick", scen)
out = os.path.join("flick", "thr_%s_%s" % (tag, scen))
os.makedirs(out, exist_ok=True)
open("detail_probe.txt", "w").close()
r, m = f.run_seq(d, out, "0:50,2:50,3:30,4:50")
print("ret=%d %s" % (r, m))
'''

CASES = [
    ("base", 10, 16, 6 * 64, 16 * 64),
    ("b", 10, 14, 6 * 64, 12 * 64),
    ("c", 10, 12, 6 * 64, 10 * 64),
    ("d", 10, 12, 6 * 64, 8 * 64),
    ("e", 10, 14, 6 * 64, 10 * 64),
]


def read_probe():
    rows = []
    p = os.path.join(HERE, "detail_probe.txt")
    if not os.path.exists(p):
        return rows
    for line in open(p, encoding="utf-8"):
        d = {}
        for kv in line.split():
            k, _, v = kv.partition("=")
            d[k] = v
        if d.get("mode") == "adapt":
            rows.append(d)
    return rows


def run(tag, scen, vals):
    env = os.environ.copy()
    env.update({
        "BEAUTY_DETAIL_PROBE": "1",
        "BEAUTY_FINE_LO": str(vals[0]),
        "BEAUTY_FINE_HI": str(vals[1]),
        "BEAUTY_MID_LO": str(vals[2]),
        "BEAUTY_MID_HI": str(vals[3]),
    })
    env.pop("BEAUTY_ADAPT_OFF", None)
    p = subprocess.run([sys.executable, "-c", CHILD, scen, tag],
                       cwd=HERE, env=env, capture_output=True, text=True,
                       timeout=120)
    if p.returncode != 0:
        print("  %s %s FAIL %s" % (tag, scen, p.stdout[-200:]))
        return []
    rows = read_probe()
    # 前两帧没有历史，跳过；运动门控全开后探针为 0，也保留（代表无拖影）
    return rows[2:]


def summarize(rows, mid_div):
    if not rows:
        return None
    sf = [float(r["strongF"]) for r in rows if int(r["nStrongF"]) > 0]
    sm = [float(r["strongM"]) / mid_div for r in rows if int(r["nStrongM"]) > 0]
    af = [float(r["allF"]) for r in rows]
    am = [float(r["allM"]) / mid_div for r in rows]
    return (statistics.mean(sf) if sf else 0.0,
            statistics.mean(sm) if sm else 0.0,
            statistics.mean(af), statistics.mean(am))


def main():
    print("候选阈值：细频 Lo/Hi，中频 Lo/Hi（中频已除以 64 换算成级）")
    print("%-6s %-14s %-26s %-26s" %
          ("tag", "thresholds", "slow 强边缘残影 F/M", "±5 噪声 all F/M"))
    for tag, fl, fh, ml, mh in CASES:
        vals = (fl, fh, ml, mh)
        slow = summarize(run(tag, "sweep_slow", vals), 64.0)
        noisy = summarize(run(tag, "noisy5", vals), 64.0)
        print("%-6s %-14s %-26s %-26s" %
              (tag, "%d/%d %d/%d" % (fl, fh, ml // 64, mh // 64),
               "%.2f / %.2f" % (slow[0], slow[1]) if slow else "n/a",
               "%.3f / %.3f" % (noisy[2], noisy[3]) if noisy else "n/a"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
