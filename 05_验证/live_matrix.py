"""live_matrix.py - 同一台相机、同一光照下，用不同环境变量各跑一次 OBS，把
「下载 / 引擎 / 上传」与引擎分段耗时并排列出来。

为什么需要它：真机上「引擎 14 ms」到底花在哪，台架复现不出来（台架没有编码器
抢核，也不会有「人走出画面」）。所以把可调项做成环境变量，一次装机做多组对照。

⚠️ 统计口径：**只统计「无脸跳过 = 0」的窗口**。人走出画面时引擎会整段跳过，
那几个窗口的耗时是无意义的低值；把它们混进中位数会造出「某组快 3 ms」的假象
（1.0.9.0 第一轮就踩了这个坑：C 组 10.31 vs A 组 13.87，其实四组都是 13.9）。

用法：
    python live_matrix.py            # 跑全部组
    python live_matrix.py A B        # 只跑指定组

每组：启动 OBS（带该组环境变量）→ 录 28 秒 → 退出，然后把那一份日志拷到
_live112/<组名>.txt，最后解析并打印表格。

1.0.13.0 起固定跑 S / F 两组**同会话配对**：S = 默认（`fuse=1`），F = `BEAUTY_BOX_FUSE=0`
（盒式退回 `1.0.12.0` 的写法）。跨会话的绝对值不可比 —— 2026-11-09 13:13 那轮所有
多线程段齐降 1.8 倍、单线程的人脸检测却不变，是当时有后台进程抢核，不是代码差异。
判据只看同一次坐在电脑前跑出来的 S 对 F。**比之前先看 ROI**：磨皮几乎完全由 ROI
面积支配，ROI 对不上就只能按面积归一。

每组跑完会自动校验：`init OK` 只出现一次、窗口数 ≤ 8、`fuse` 与预期一致；
任一条不满足就打印「数据作废」。观察到的历史事故：`quit` 有时只关窗口不退进程，
下一次 `up` 便复用旧进程、环境变量不生效，两组日志合并成一份。
"""

import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CTL = os.path.join(HERE, "obs_ctl.py")
LOGDIR = os.path.join(os.environ["APPDATA"], "obs-studio", "logs")
OUTDIR = os.path.join(HERE, "_live113")
REC_SECS = 28

# 组名 → (说明, 环境变量列表)
GROUPS = [
    ("S", "1.0.13.0 默认（盒式三通道融合 + SSE 垂直趟）", []),
    ("F", "1.0.13.0 + BEAUTY_BOX_FUSE=0（退回 bandBoxH/V 参考实现）",
     ["BEAUTY_BOX_FUSE=0"]),
]

PERF = re.compile(
    r"性能 (\d+)x(\d+)：下载 ([\d.]+) \+ 引擎 ([\d.]+) \+ 上传 ([\d.]+) = ([\d.]+) ms/帧"
    r"（(\d+) 帧平均）对齐 (\d+)/(\d+)（(\d+)%）无脸跳过 (\d+)")
STAGE = re.compile(
    r"分段：检测\+掩码 ([\d.]+) \| 磨皮 ([\d.]+) \| 色调 ([\d.]+) \| 细节 ([\d.]+)"
    r" \| 美形\+alpha ([\d.]+) \| ROI (\d+)x(\d+) 掩码 (\d+)")


def newest_log():
    files = [f for f in os.listdir(LOGDIR) if f.endswith(".txt")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(LOGDIR, f)), reverse=True)
    return os.path.join(LOGDIR, files[0])


def obs_alive():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
                       capture_output=True, text=True, errors="replace")
    return "obs64.exe" in (r.stdout or "")


def wait_obs_gone(timeout=12.0):
    """等 obs64.exe 真退出。quit 偶尔只是把窗口关掉，进程还活着 —— 那样下一次
    up 会「复用」旧进程、环境变量不生效，两组日志合并成一份（1.0.13.0 的 F_r3
    就这么废的：17 个窗口全是 fuse=on）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not obs_alive():
            return True
        time.sleep(0.5)
    return False


def verify_log(dst, envs):
    """校验这一份日志确实只对应一次会话、且开关与预期一致。"""
    txt = open(dst, encoding="utf-8", errors="replace").read()
    ninit = txt.count("obs-beauty] init OK")
    nwin = len(PERF.findall(txt))
    ok = True
    if ninit != 1:
        print("  !! init OK 出现 %d 次（应为 1）—— 日志可能混了多次会话" % ninit)
        ok = False
    if nwin > 8:
        print("  !! %d 个 6 秒窗口 >> 录制时长 %d 秒，疑似上一次录制没停" % (nwin, REC_SECS))
        ok = False
    for e in envs:
        k, v = e.split("=", 1)
        want = "on" if v != "0" else "off"
        if k == "BEAUTY_BOX_FUSE" and ("fuse=%s" % want) not in txt:
            print("  !! 日志里没有 fuse=%s —— 环境变量没生效" % want)
            ok = False
    if not ok:
        print("  !! %s 数据作废，请重跑该组" % os.path.basename(dst))
    return ok


def run_group(name, desc, envs):
    print("\n=== %s: %s ===" % (name, desc), flush=True)
    if obs_alive():
        print("[%s] OBS 还在跑，先退出再开始（否则环境变量不生效）" % name, flush=True)
        subprocess.run([sys.executable, CTL, "quit"], capture_output=True, text=True)
        if not wait_obs_gone():
            print("[%s] 退不掉，跳过本组，请手动关掉 OBS 再重跑" % name, flush=True)
            return
    up = [sys.executable, CTL, "up"]
    for e in envs:
        up += ["--env", e]
    r = subprocess.run(up, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip(), flush=True)
    if r.returncode != 0:
        print("[%s] up failed" % name, flush=True)
        return
    subprocess.run([sys.executable, CTL, "record", str(REC_SECS)],
                   capture_output=True, text=True)
    subprocess.run([sys.executable, CTL, "quit"], capture_output=True, text=True)
    if not wait_obs_gone():
        print("[%s] quit 之后 obs64.exe 仍在，终止录制" % name, flush=True)
    time.sleep(1.5)
    dst = os.path.join(OUTDIR, "%s.txt" % name)
    shutil.copyfile(newest_log(), dst)
    print("log ->", dst, flush=True)
    verify_log(dst, envs)


def summarize(name):
    p = os.path.join(OUTDIR, "%s.txt" % name)
    if not os.path.exists(p):
        return None
    txt = open(p, encoding="utf-8", errors="replace").read()
    rows = PERF.findall(txt)
    stages = STAGE.findall(txt)
    init = re.search(r"box_block=(\d+), box_minpx=(\d+), par_copy=(\w+), alpha=(\w+)"
                     r", zc=(\w+), tone_lut=(\w+), fuse=(\w+)", txt)
    if not rows:
        return {"name": name, "perf": None, "cfg": "?"}
    # 只留「无脸跳过 = 0」的窗口：那些才是「脸一直在画面里」的稳态数据
    used = [r for r in rows if r[10] == "0"]
    if not used:
        return {"name": name, "perf": None, "cfg": "无干净窗口（人不在画面里）"}
    med = lambda v: sorted(v)[len(v) // 2]
    perf = (med([float(r[2]) for r in used]), med([float(r[3]) for r in used]),
            med([float(r[4]) for r in used]), med([float(r[5]) for r in used]))
    st = {}
    if stages:
        for i, k in enumerate(["mask", "blur", "tone", "detail", "warp"]):
            st[k] = med([float(s[i]) for s in stages])
        st["roi"] = "%sx%s" % (stages[-1][5], stages[-1][6])
        st["mpx"] = stages[-1][7]
    return {"name": name, "perf": perf, "stage": st, "cfg": init.groups() if init else "?",
            "clean": len(used), "total": len(rows)}


def main():
    want = sys.argv[1:]
    os.makedirs(OUTDIR, exist_ok=True)
    for name, desc, envs in GROUPS:
        if want and name not in want:
            continue
        run_group(name, desc, envs)

    print("\n%-4s %-46s %-6s %-6s %-6s %-6s %-34s %s"
          % ("组", "配置", "下载", "引擎", "上传", "合计", "分段 检测/磨皮/色调/细节/美形", "干净窗口"))
    print("-" * 132)
    for name, desc, _ in GROUPS:
        if want and name not in want:
            continue
        s = summarize(name)
        if not s or not s["perf"]:
            print("%-4s %-46s (无数据) %s" % (name, desc, s.get("cfg") if s else ""))
            continue
        dl, pr, up, tot = s["perf"]
        st = s["stage"]
        stxt = ("%.1f/%.1f/%.1f/%.1f/%.1f" % (st["mask"], st["blur"], st["tone"],
                                              st["detail"], st["warp"])) if st else "-"
        print("%-4s %-46s %6.2f %6.2f %6.2f %6.2f  %-34s %d/%d ROI=%s 掩码=%s" %
              (name, desc, dl, pr, up, tot, stxt, s["clean"], s["total"],
               st.get("roi", "?"), st.get("mpx", "?")))
        c = s["cfg"]
        if isinstance(c, tuple):
            print("     init: box=%s minpx=%s par_copy=%s alpha=%s zc=%s tone=%s fuse=%s" % c)


if __name__ == "__main__":
    main()
