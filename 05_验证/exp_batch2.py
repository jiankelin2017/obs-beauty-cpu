# -*- coding: utf-8 -*-
"""expA 安全实验（第二轮）：60 帧/进程，暴露量 ×6。

判定口径（nz_probe 的 LegacySeqTest 每帧写一行 seq_log）：
  infer = 该帧结束时的成功推理计数（失败帧不增）
  gap   = infer 未增长的帧（= 本次调用抛了访问违例）
  恢复  = 末帧 infer >= 总帧数 - 失败帧数（说明 AV 之后 fuai 仍能正常出掩码）
  崩溃  = 进程异常退出 / 帧数不足 / 末帧 cov 掉零
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(HERE, "seq_log.txt")
META = os.path.join(HERE, "flick", "nz_in", "meta.txt")
PROBE = "nz_probe_nodel.py"
DLL = os.path.join(HERE, "expA", "legacy_engine_test_expA.dll")
PANEL = "0:50"
N = 40

COUNT = int(open(META).read().split()[1])
print("每进程帧数 %d，计划 %d 个进程（总推理调用约 %d 次）" % (COUNT, N, COUNT * N))
sys.stdout.flush()


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
    rows = []
    for i in range(N):
        tag = "exb%02d" % i
        n0 = len(seq_lines())
        try:
            r = subprocess.run([sys.executable, PROBE, "run", DLL, tag, PANEL],
                               cwd=HERE, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=300)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            print("%s 超时" % tag)
            rows.append((tag, -1, -1, -1, -1, 0.0, "TIMEOUT"))
            continue
        fr = parse(seq_lines()[n0:n0 + COUNT])
        if len(fr) < COUNT:
            print("%s 帧数不足(%d/%d) rc=%d  <-- 进程可能中途崩溃"
                  % (tag, len(fr), COUNT, rc))
            rows.append((tag, -1, -1, -1, -1, 0.0, "SHORT"))
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
        cov_last = fr[-1][1]
        cov_zero = 1 if cov_last <= 0.001 else 0
        rows.append((tag, gap_n, last, recovered, gaps, cov_last, "OK"))
        if gap_n:
            print("%s 失败帧 %d:%s 末infer=%d/%d 恢复=%s 末cov=%.4f"
                  % (tag, gap_n, gaps if len(gaps) <= 6 else gaps[:6] + ["..."],
                     last, COUNT, "是" if recovered else "否", cov_last))
        else:
            print("%s 健康 (60 帧全成功, cov=%.4f)" % (tag, cov_last))
        sys.stdout.flush()

    print("")
    print("=" * 78)
    broken = [r for r in rows if r[6] != "OK"]
    ok = [r for r in rows if r[6] == "OK" and r[1] == 0]
    bad = [r for r in rows if r[6] == "OK" and r[1] > 0]
    print("总运行 %d：健康 %d，出现访问违例 %d，异常退出/不完整 %d"
          % (len(rows), len(ok), len(bad), len(broken)))
    if bad:
        rec = sum(1 for r in bad if r[3] == 1)
        zero = sum(1 for r in bad if r[5] <= 0.001)
        print("失败后恢复 %d / %d；恢复后覆盖度掉零 %d 例" % (rec, len(bad), zero))
        print("失败帧位置分布：%s" % [r[4] for r in bad])
        print("失败场次的末帧覆盖度：%s" % ["%.4f" % r[5] for r in bad])
    if broken:
        print("异常进程：%s" % [(r[0], r[6]) for r in broken])
    print("=" * 78)


if __name__ == "__main__":
    main()
