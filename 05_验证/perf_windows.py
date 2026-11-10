# -*- coding: utf-8 -*-
"""perf_windows.py 0.1.0 —— 把 OBS 日志里的「性能」行按窗口归集，并给出两种口径

为什么要这个脚本
----------------
`obs-beauty.cpp` 的性能行是**180 帧窗口均值**，分母 `prof_frames` 把
「无脸跳过」帧也算了进去。无脸帧在 `beauty_core.cpp` 里只做一次整帧 memcpy
就返回（不进磨皮链），代价接近 0。于是：

  * 某档 `对齐` 分母比 180 小，说明该窗口有帧在计数点之前就早退了；
  * 某档 `无脸跳过` 不为 0，说明该窗口里有 n 帧以近乎零成本混进了分母，
    **引擎均值被系统性拉低**。

不修正就会把「少算了几帧」误读成「引擎变快了」。0.1.0 因此对每个窗口同时
输出两种口径：

  raw  = 日志原值（= 上一轮报告用的口径，保留以便向前对比）
  proc = 仅按**真正进入磨皮链的帧**折算：
         engine_proc = (engine_raw * frames - noface * memcpy_ms) / (frames - noface)

memcpy_ms 默认 0.7，取自 `beauty_core.cpp` submitAsync 处的注释自述
（「1080p 下的 8MB memcpy 约 0.7ms」）。它是**估计值**，脚本会把这一项
显式打印出来，不要把它当成实测。

用法
----
    python perf_windows.py <日志1> [日志2 ...] [-o 报告.md]
    python perf_windows.py --dir "%APPDATA%/obs-studio/logs" --since 23:30
"""

import argparse
import io
import os
import re
import sys

# 「性能 1920x1080：下载 2.93 + 引擎 41.36 + 上传 1.37 = 45.65 ms/帧（180 帧平均）
#   对齐 398/1215（33%）无脸跳过 45」
RE_PERF = re.compile(
    r"性能\s+(\d+)x(\d+)：下载\s+([\d.]+)\s*\+\s*引擎\s+([\d.]+)\s*\+\s*上传\s+([\d.]+)"
    r"\s*=\s*([\d.]+)\s*ms/帧（(\d+)\s*帧平均）对齐\s+(\d+)/(\d+)（(\d+)%）无脸跳过\s+(\d+)"
)
RE_EVERY = re.compile(r"region=on\(every=(\d+)\)")
RE_REC_START = re.compile(r"==== Recording (Start|Stop) ====")
RE_TS = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3}):")


def parse_log(path):
    """返回 dict：every / windows / rec 起止 / 文件行数。"""
    every = None
    windows = []
    rec = {"start": None, "stop": None}
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = RE_EVERY.search(line)
            if m and every is None:
                every = int(m.group(1))
            m = RE_TS.match(line)
            ts = m.group(1) if m else None
            m = RE_REC_START.search(line)
            if m:
                rec["start" if m.group(1) == "Start" else "stop"] = ts
                continue
            m = RE_PERF.search(line)
            if m:
                g = m.groups()
                windows.append({
                    "ts": ts,
                    "w": int(g[0]), "h": int(g[1]),
                    "dl": float(g[2]), "engine": float(g[3]), "up": float(g[4]),
                    "total": float(g[5]), "frames": int(g[6]),
                    "align_used": int(g[7]), "align_total": int(g[8]),
                    "align_pct": int(g[9]), "noface": int(g[10]),
                })
    return {"path": path, "every": every, "windows": windows, "rec": rec}


def _tsec(ts):
    """'23:42:50.226' -> 秒数（跨零点按 +86400 处理，日志都是一次会话）。"""
    if not ts:
        return None
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def mark_inside_rec(run):
    """给每个窗口标 in_rec：窗口**整段**落在录制区间内才算 True。

    窗口的起点取上一个窗口的结束时刻（窗口是累积计数，相邻两行之间正好一段）；
    第一个窗口没有已知起点，一律视为不在区间内。这条判据会把「跨录制起点」和
    「跨录制终点」的两个混合窗剔掉 —— 它们的均值既含预览也含录制，不能当稳态。
    """
    rs = _tsec(run["rec"]["start"])
    re_ = _tsec(run["rec"]["stop"])
    prev_end = None
    for w in run["windows"]:
        end = _tsec(w["ts"])
        if rs is None or re_ is None or prev_end is None:
            w["in_rec"] = False
        else:
            w["in_rec"] = (prev_end >= rs) and (end is not None) and (end <= re_)
        prev_end = end


def summarize(run, memcpy_ms, keep=None):
    ws = [w for w in run["windows"] if (keep(w) if keep else True)]
    if not ws:
        return None
    frames = sum(w["frames"] for w in ws)
    noface = sum(w["noface"] for w in ws)
    proc_frames = frames - noface
    eng_raw = sum(w["engine"] * w["frames"] for w in ws) / frames
    tot_raw = sum(w["total"] * w["frames"] for w in ws) / frames
    dl = sum(w["dl"] * w["frames"] for w in ws) / frames
    up = sum(w["up"] * w["frames"] for w in ws) / frames
    eng_proc = (sum(w["engine"] * w["frames"] for w in ws) - noface * memcpy_ms) / max(proc_frames, 1)
    tot_proc = eng_proc + dl + up
    al_u = sum(w["align_used"] for w in ws)
    al_t = sum(w["align_total"] for w in ws)
    return {
        "every": run["every"], "file": os.path.basename(run["path"]),
        "windows": len(ws), "frames": frames, "noface": noface,
        "noface_pct": 100.0 * noface / frames if frames else 0.0,
        "dl": dl, "up": up,
        "engine_raw": eng_raw, "total_raw": tot_raw,
        "engine_proc": eng_proc, "total_proc": tot_proc,
        "align": (al_u, al_t, 100.0 * al_u / al_t if al_t else 0.0),
        "rec": run["rec"],
    }


def fmt_row(s, base=None):
    d_raw = "—"
    d_proc = "—"
    if base is not None:
        d_raw = "%+.2f" % (s["total_raw"] - base["total_raw"])
        d_proc = "%+.2f" % (s["total_proc"] - base["total_proc"])
    return ("| every=%d | %d | %d | %.1f%% | %.2f | %.2f | %s | %.2f | %.2f | %s | %d/%d (%.1f%%) |"
            % (s["every"], s["windows"], s["noface"], s["noface_pct"],
               s["engine_raw"], s["total_raw"], d_raw,
               s["engine_proc"], s["total_proc"], d_proc,
               s["align"][0], s["align"][1], s["align"][2]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*")
    ap.add_argument("--dir", default=None)
    ap.add_argument("--since", default=None, help="文件名里的时间前缀下限，如 23:30")
    ap.add_argument("--memcpy-ms", type=float, default=0.7)
    ap.add_argument("--rec-only", action="store_true",
                    help="只保留整段落在录制区间内的窗口（推荐用于稳态对比）")
    ap.add_argument("--windows", default=None,
                    help="按出现序号取窗口，如 2-8（用于复现上一轮报告的取窗方式）")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    paths = list(args.logs)
    if args.dir:
        for name in sorted(os.listdir(args.dir)):
            if not name.endswith(".txt"):
                continue
            if args.since and name[:5] < args.since:
                continue
            paths.append(os.path.join(args.dir, name))

    runs = [parse_log(p) for p in paths]
    runs = [r for r in runs if r["windows"]]
    if not runs:
        print("没有解析到任何「性能」行。确认日志是 obs-beauty 打开 BEAUTY_PROFILE 时产生的。")
        return 2
    for r in runs:
        mark_inside_rec(r)

    if args.windows:
        lo, _, hi = args.windows.partition("-")
        lo = int(lo)
        hi = int(hi) if hi else lo
        for r in runs:
            for i, w in enumerate(r["windows"], 1):
                w["pick"] = lo <= i <= hi
    elif args.rec_only:
        for r in runs:
            for w in r["windows"]:
                w["pick"] = w["in_rec"]
    else:
        for r in runs:
            for w in r["windows"]:
                w["pick"] = True

    out = []
    out.append("# 性能窗口归集（perf_windows.py 0.1.0）\n")
    out.append("memcpy 折算取 **%.2f ms/帧**（估计值，来自源码注释，非实测）。"
               "口径：%s。\n"
               % (args.memcpy_ms,
                  ("窗口 %s（按出现序号）" % args.windows) if args.windows else
                  ("仅整段落在录制区间内的窗口" if args.rec_only else "全部窗口")))

    for tag, keep in (("全部窗口（含预览/混合窗）", lambda w: True),
                      ("仅录制区间内窗口", lambda w: w["in_rec"])):
        sums = [summarize(r, args.memcpy_ms, keep) for r in runs]
        sums = [s for s in sums if s]
        if not sums:
            continue
        base = next((s for s in sums if s["every"] == 0), None)
        out.append("## %s\n" % tag)
        out.append("| 档位 | 窗口 | 无脸帧 | 占比 | 引擎 raw | 合计 raw | Δraw | 引擎 proc | 合计 proc | Δproc | 对齐 |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for s in sums:
            out.append(fmt_row(s, base if (base and s is not base) else None))
        out.append("")
    # (sums 在上一循环内已用完，明细段单独构建)

    out.append("## 逐窗口明细\n")
    out.append("「入」列 = 该窗口是否整段落在录制区间内（★ 为是）。\n")
    for r in runs:
        out.append("### every=%d — %s（录制 %s → %s）\n"
                   % (r["every"], os.path.basename(r["path"]),
                      r["rec"]["start"] or "?", r["rec"]["stop"] or "?"))
        out.append("| # | 时刻 | 入 | 下载 | 引擎 | 上传 | 合计 | 帧 | 对齐 | 无脸 |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for i, w in enumerate(r["windows"], 1):
            out.append("| %d | %s | %s | %.2f | %.2f | %.2f | %.2f | %d | %d/%d (%d%%) | %d |"
                       % (i, w["ts"] or "?", "★" if w["in_rec"] else "—",
                          w["dl"], w["engine"], w["up"], w["total"],
                          w["frames"], w["align_used"], w["align_total"],
                          w["align_pct"], w["noface"]))
        out.append("")

    text = "\n".join(out)
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("已写出 %s" % args.out)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
