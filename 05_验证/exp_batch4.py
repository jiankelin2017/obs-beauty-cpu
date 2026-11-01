# -*- coding: utf-8 -*-
"""A/B 压测：给定 DLL，跑 N 个进程 × COUNT 帧，统计访问违例（gap）次数。

判定口径与 exp_batch3.py 一致：
  infer = 该帧结束时的成功推理计数（失败帧不增）
  gap   = infer 未增长的帧（= 本次调用抛了访问违例）

用法：
  python exp_batch4.py <dll> <N> [tag_prefix]
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(HERE, "seq_log.txt")
META = os.path.join(HERE, "flick", "nz_in", "meta.txt")
PROBE = "nz_probe_dlldir.py"
PANEL = "0:50"

def seq_lines():
    try:
        with open(SEQ, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []

def parse(lines):
    out = []
    for ln in lines:
        m = re.search(r"infer=(\d+)", ln)
        c = re.search(r"cov=([\d.]+)", ln)
        if m:
            out.append((int(m.group(1)), float(c.group(1)) if c else -1.0))
    return out

def main():
    dll = sys.argv[1]
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    pfx = sys.argv[3] if len(sys.argv) > 3 else "ab"
    COUNT = int(open(META).read().split()[1])
    print("DLL=%s  进程数=%d  每进程帧数=%d  总调用约=%d"
          % (dll, N, COUNT, COUNT * N))
    sys.stdout.flush()

    rows = []
    for i in range(N):
        tag = "%s%03d" % (pfx, i)
        n0 = len(seq_lines())
        try:
            r = subprocess.run([sys.executable, PROBE, "run", dll, tag, PANEL],
                               cwd=HERE, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            print("%s 超时" % tag)
            rows.append((tag, -1, -1, -1, [], 0.0, "TIMEOUT"))
            continue
        fr = parse(seq_lines()[n0:n0 + COUNT])
        if len(fr) < COUNT:
            print("%s 帧数不足(%d/%d) rc=%d  <-- 进程可能中途崩溃"
                  % (tag, len(fr), COUNT, rc))
            if r.stderr:
                print("   stderr: %s" % r.stderr.strip()[:300])
            rows.append((tag, -1, -1, -1, [], 0.0, "SHORT"))
            sys.stdout.flush()
            continue
        infers = [x[0] for x in fr]
        gaps = []
        if infers[0] == 0:
            gaps.append(0)
        for k in range(1, COUNT):
            if infers[k] == infers[k - 1]:
                gaps.append(k)
        gap_n = len(gaps)
        last = infers[-1]
        recovered = 1 if last >= COUNT - gap_n else 0
        rows.append((tag, gap_n, last, recovered, gaps, fr[-1][1], "OK"))
        if gap_n:
            print("%s 失败帧 %d:%s 末infer=%d/%d 恢复=%s 末cov=%.4f"
                  % (tag, gap_n, gaps if len(gaps) <= 6 else gaps[:6] + ["..."],
                     last, COUNT, "是" if recovered else "否", fr[-1][1]))
        else:
            print("%s 健康 (%d 帧全成功, cov=%.4f)" % (tag, COUNT, fr[-1][1]))
        sys.stdout.flush()

    print("")
    print("=" * 78)
    broken = [r for r in rows if r[6] != "OK"]
    ok = [r for r in rows if r[6] == "OK" and r[1] == 0]
    bad = [r for r in rows if r[6] == "OK" and r[1] > 0]
    total_calls = sum(COUNT for r in rows if r[6] == "OK")
    total_gaps = sum(r[1] for r in rows if r[6] == "OK")
    print("DLL=%s" % dll)
    print("总运行 %d：健康 %d，出现访问违例 %d，异常退出/不完整 %d"
          % (len(rows), len(ok), len(bad), len(broken)))
    print("总调用 %d 次，失败 %d 次 → 失败率 %.3f%%"
          % (total_calls, total_gaps, 100.0 * total_gaps / max(1, total_calls)))
    if bad:
        rec = sum(1 for r in bad if r[3] == 1)
        print("失败后恢复 %d / %d" % (rec, len(bad)))
        print("失败帧位置分布：%s" % [r[4] for r in bad])
    if broken:
        print("异常进程：%s" % [(r[0], r[6]) for r in broken])
    print("=" * 78)

if __name__ == "__main__":
    main()
