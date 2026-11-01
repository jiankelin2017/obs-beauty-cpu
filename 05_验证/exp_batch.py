# -*- coding: utf-8 -*-
"""expA 安全实验：VEH 抓到访问违例后继续调用 fuai 是否安全 / 能否自动恢复。

判定口径（每次运行 10 帧，nz_probe 的 LegacySeqTest 每帧打印一行 seq_log）：
  infer  = 该帧结束时的成功推理计数（失败帧不增）
  gap    = 出现「infer 不增」的帧数（= 失败帧数）
  恢复   = 最后一帧的 infer 是否继续增长到 10 - gap
  健康   = gap == 0 且末帧 infer == 10

若 AV 后 fuai 状态已损坏，预期看到：gap 之后 infer 永久不再增长（连败）
或进程直接消失；若只是偶发，预期 gap 之后紧跟正常增长。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(HERE, "seq_log.txt")
PROBE = "nz_probe_nodel.py"
DLL = os.path.join(HERE, "expA", "legacy_engine_test_expA.dll")
PANEL = "0:50"      # 磨皮 50：本项目观测到中毒最多的配置
N = 60


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
        a = re.search(r"meanAbs=([\d.]+)", ln)
        if m:
            out.append((int(m.group(1)),
                        float(c.group(1)) if c else -1.0,
                        float(a.group(1)) if a else -1.0))
    return out


def main():
    rows = []
    for i in range(N):
        tag = "expa%02d" % i
        n0 = len(seq_lines())
        r = subprocess.run([sys.executable, PROBE, "run", DLL, tag, PANEL],
                           cwd=HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        fr = parse(seq_lines()[n0:n0 + 10])
        if len(fr) < 10:
            print("%s 帧数不足(%d) rc=%d" % (tag, len(fr), r.returncode))
            rows.append((tag, -1, -1, -1, -1, 0.0))
            continue
        infers = [x[0] for x in fr]
        # 失败帧 = infer 与上一帧相同的第 k 帧（k>=1）；首帧 infer==0 也算失败
        gaps = []
        if infers[0] == 0:
            gaps.append(0)
        for k in range(1, 10):
            if infers[k] == infers[k - 1]:
                gaps.append(k)
        gap_n = len(gaps)
        last = infers[-1]
        # 恢复：最后一帧的 infer 达到「10 - 失败帧数」
        recovered = 1 if last >= 10 - gap_n else 0
        # 恢复后的覆盖度是否正常（0.14 量级），以及是否出现 0 覆盖的空窗
        covs = [x[1] for x in fr]
        cov_last = covs[-1]
        rows.append((tag, gap_n, last, recovered, gaps[0] if gaps else -1, cov_last))
        flag = ""
        if gap_n:
            flag = "  <-- 失败帧 %s 恢复=%s 末cov=%.4f" % (gaps, "是" if recovered else "否", cov_last)
        print("%s gap=%d 末infer=%2d %s" % (tag, gap_n, last, flag))
        sys.stdout.flush()

    print("")
    print("=" * 78)
    ok = [r for r in rows if r[1] == 0]
    bad = [r for r in rows if r[1] > 0]
    lost = [r for r in rows if r[1] < 0]
    print("总运行 %d：健康 %d，出现访问违例 %d，异常退出 %d"
          % (len(rows), len(ok), len(bad), len(lost)))
    if bad:
        rec = sum(1 for r in bad if r[3] == 1)
        print("其中：失败后成功恢复 %d / %d，未恢复 %d" % (rec, len(bad), len(bad) - rec))
        for r in bad:
            print("  %s 失败帧位置 %s 末infer=%d 末cov=%.4f 恢复=%s"
                  % (r[0], r[4], r[2], r[5], "是" if r[3] else "否"))
    print("=" * 78)


if __name__ == "__main__":
    main()
