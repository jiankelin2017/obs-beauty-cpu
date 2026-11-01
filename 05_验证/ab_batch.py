# -*- coding: utf-8 -*-
"""A/B 批处理：3.0.12（预热） vs 3.0.11（无预热基线）的 fuai 中毒率对照。

每个 nz_probe run = 一个独立进程。判据：
  * msg 里 inferCnt == 10        -> 健康
  * inferCnt < 10                -> 中毒（某帧 inferOnce 走异常分支置 failed_）
  * 进程崩 / 无 msg              -> CRASH
冻结帧从 seq_log.txt 的增量 10 行里解析（infer 停止递增的首帧）。

两个 DLL 交替跑，摊薄机器负载漂移的影响。
"""
import io
import os
import re
import subprocess
import sys

HERE = r"C:\legacy_e2e"
SEQ_LOG = os.path.join(HERE, "seq_log.txt")

DLLS = [
    ("warmup(3.0.12)", "legacy_engine_test.dll"),
    ("base(3.0.11)", "b311/legacy_engine_test_b311.dll"),
]
PANELS = [("blur50", "0:50"), ("blur50+whiten50", "0:50,2:50")]
N = 8
MAX_CONSEC_FAIL = 3


def seq_lines():
    if not os.path.exists(SEQ_LOG):
        return []
    with io.open(SEQ_LOG, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def freeze_frame(lines):
    """10 行 (seq,infer,...)。返回首个 infer 停止递增的 seq；健康返回 -1。"""
    infers = []
    for ln in lines:
        m = re.search(r"seq=(\d+) .*?infer=(\d+)", ln)
        if m:
            infers.append((int(m.group(1)), int(m.group(2))))
    infers.sort()
    for k in range(1, len(infers)):
        if infers[k][1] == infers[k - 1][1]:
            return infers[k][0]
    return -1


def main():
    rows = []
    consec_fail = 0
    for i in range(N):
        for pname, panel in PANELS:
            for dname, dll in DLLS:
                n0 = len(seq_lines())
                tag = "abx"
                cmd = [sys.executable, "nz_probe_nodel.py", "run", dll, tag, panel]
                try:
                    r = subprocess.run(cmd, cwd=HERE, capture_output=True,
                                       text=True, timeout=120)
                    out = (r.stdout or "") + (r.stderr or "")
                except subprocess.TimeoutExpired:
                    rows.append((dname, pname, i, "TIMEOUT", -1, ""))
                    print("%-14s %-16s #%02d TIMEOUT" % (dname, pname, i))
                    continue
                msg = ""
                for ln in out.splitlines():
                    if ln.startswith(tag + " "):
                        msg = ln
                if not msg:
                    rows.append((dname, pname, i, "NOMSG", -1, ""))
                    print("%-14s %-16s #%02d NOMSG rc=%s" % (dname, pname, i, r.returncode))
                    err = (r.stderr or "").strip()
                    if err:
                        print("    stderr: %s" % err[-300:].replace("\n", " | "))
                    consec_fail += 1
                    if consec_fail >= MAX_CONSEC_FAIL:
                        print("连续 %d 次无输出，环境异常，中止批次" % consec_fail)
                        print_summary(rows)
                        return
                    continue
                consec_fail = 0
                m = re.search(r"inferCnt=(\d+)", msg)
                mc = re.search(r"cov=([\d.]+)", msg)
                ic = int(m.group(1)) if m else -1
                cov = mc.group(1) if mc else "?"
                reg = ("就绪" if "语义区域就绪" in out else
                       ("不可用" if "语义区域不可用" in out else "?"))
                werr = "预热重试耗尽" if "预热推理重试" in out else ""
                lines = seq_lines()[n0:n0 + 10]
                ff = freeze_frame(lines) if len(lines) >= 10 else -2
                rows.append((dname, pname, i, ic, ff, cov, reg, werr))
                flag = "  <-- 中毒" if (ic >= 0 and ic < 10) else ""
                print("%-14s %-16s #%02d inferCnt=%-3d freeze=%-3d cov=%s 区域=%s %s%s"
                      % (dname, pname, i, ic, ff, cov, reg, werr, flag))
                sys.stdout.flush()

    print("")
    print("=" * 76)
    for dname, _ in DLLS:
        for pname, _ in PANELS:
            sub = [r for r in rows if r[0] == dname and r[1] == pname]
            n = len(sub)
            poison = sum(1 for r in sub if isinstance(r[3], int) and 0 <= r[3] < 10)
            crash = sum(1 for r in sub if r[3] in ("NOMSG", "TIMEOUT"))
            frz = sorted(r[4] for r in sub if isinstance(r[3], int) and 0 <= r[3] < 10)
            print("%-14s %-16s n=%d 中毒=%d 崩溃=%d 冻结帧=%s"
                  % (dname, pname, n, poison, crash, frz))
    print("=" * 76)


def print_summary(rows):
    print("")
    print("=" * 76)
    for dname, _ in DLLS:
        for pname, _ in PANELS:
            sub = [r for r in rows if r[0] == dname and r[1] == pname]
            n = len(sub)
            poison = sum(1 for r in sub if isinstance(r[3], int) and 0 <= r[3] < 10)
            crash = sum(1 for r in sub if r[3] in ("NOMSG", "TIMEOUT"))
            frz = sorted(r[4] for r in sub if isinstance(r[3], int) and 0 <= r[3] < 10)
            print("%-14s %-16s n=%d 中毒=%d 崩溃=%d 冻结帧=%s"
                  % (dname, pname, n, poison, crash, frz))
    print("=" * 76)


if __name__ == "__main__":
    main()
