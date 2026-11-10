# -*- coding: utf-8 -*-
"""ab_run.py 0.1.0 —— 一次 A/B 测试的全流程：改面板 → 起 OBS → 录制 → 收队 → 指路日志

为什么要有它
------------
上一轮三组是手工起的 OBS。手工流程有三个可复现性问题：
  ① 录制起点前有一段预览，日志的首窗和跨起点的窗口混进均值；
  ② 谁去点「开始录制」决定了每次的预热程度不一样；
  ③ 起完没人记 DLL 哈希，事后无法确认测的是哪个二进制。

0.1.0 把这些固定成一条命令：
  * 面板值改动只落在 `视频.json` 的 settings 里，其余字段一个不动（先备份）；
  * `--lead` 秒的静置后再开录，让自动方向探测和首帧预热走完；
  * 录制时长由 `--seconds` 固定，不再看表；
  * 结束走 obs-websocket 的 StopRecord → 正常退出（不是 taskkill），
    这样 `Recording Stop` 与最终统计才会写进日志；
  * 结束时打印**装机 DLL 的 SHA256**与日志路径。

用法
----
    python ab_run.py --tag base --every 2 --seconds 60 --set color_level=0

    # 只探测画面里有没有脸，不录制
    python ab_run.py --tag probe --every 2 --probe

    # 追加环境变量
    python ab_run.py --tag align0 --every 2 --env BEAUTY_MASK_ALIGN=0
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time

OBS_BIN = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
OBS_EXE_DIR = os.path.dirname(OBS_BIN)
SCENE = os.path.join(os.environ["APPDATA"], "obs-studio", "basic", "scenes", u"\u89c6\u9891.json")
LOGDIR = os.path.join(os.environ["APPDATA"], "obs-studio", "logs")
DLL = r"C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\obs-beauty.dll"
WS = "ws://127.0.0.1:4455"

PANEL_KEYS = [
    "blur_level", "clarity", "color_level", "red_level", "sharpen",
    "global_sharpen", "face_threed", "eye_bright",
    "remove_pouch_strength", "remove_nasolabial_folds_strength", "delspot_level",
    "thin_face", "big_eye", "chin",
]


def sha256(path):
    if not os.path.exists(path):
        return "(missing)"
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:32]


def dll_env_locked(path):
    """目标 DLL 是不是「发布版」—— 1.0.13.10 起发布构建加锁，BEAUTY_* 一律不读。

    两个构建版本串相同、画面路径相同，只有这一位不同，所以只能按加载日志的
    字面串分辨。返回 True/False，老版本（没有这一位）返回 None。
    """
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return None
    if b"env override: locked (release build)" in blob:
        return True
    if b"env override: open (dev build)" in blob:
        return False
    return None


def patch_scene(sets, keep_backup_tag):
    with io.open(SCENE, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    changed = {}
    for src in doc.get("sources", []):
        for filt in src.get("filters", []) or []:
            if filt.get("id") != "obs_beauty_filter":
                continue
            st = filt.setdefault("settings", {})
            for k, v in sets.items():
                old = st.get(k)
                st[k] = v
                changed[k] = (old, v)
    if not changed:
        print("!! 场景里没找到 obs_beauty_filter")
        return
    bak = SCENE + ".bak_ab_" + keep_backup_tag
    if not os.path.exists(bak):
        shutil.copy2(SCENE, bak)
    with io.open(SCENE, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=4)
    print("[scene] 面板改动：" + ", ".join("%s %s→%s" % (k, o, n) for k, (o, n) in changed.items()))


def newest_log(since):
    best = None
    for name in os.listdir(LOGDIR):
        if not name.endswith(".txt"):
            continue
        p = os.path.join(LOGDIR, name)
        if os.path.getmtime(p) >= since:
            if best is None or os.path.getmtime(p) > os.path.getmtime(best):
                best = p
    return best


def wait_line(log, needle, timeout, since=0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if log and os.path.exists(log):
            try:
                with io.open(log, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if needle in line:
                            return line.strip()
            except OSError:
                pass
        time.sleep(0.5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--every", type=int, default=2)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--lead", type=int, default=15, help="起 OBS 后静置多少秒再开录")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--env", action="append", default=[], metavar="K=V")
    ap.add_argument("--probe", action="store_true", help="只探测不录制")
    ap.add_argument("--no-patch", action="store_true")
    ap.add_argument("--phases", default=None,
                    help='同一会话内交替切换，如 "blur_level=100;blur_level=0;color_level=0"，'
                         '用分号分隔，每段是逗号分隔的 key=value')
    ap.add_argument("--period", type=int, default=36, help="每个相位停留秒数")
    ap.add_argument("--rounds", type=int, default=3, help="相位序列重复几轮")
    args = ap.parse_args()

    # 1.0.13.10（C-2/C-3）：发布构建对所有 BEAUTY_* 一律返回「没设置」。
    # 拿它做环境变量 A/B，两组数据会一模一样而看不出原因 —— 直接拦住。
    if dll_env_locked(DLL) and (args.env or any(k.startswith("BEAUTY_") for k in os.environ)):
        print("!! %s 是发布版（BEAUTY_ENV_LOCK）：BEAUTY_* 覆盖一律无效。" % DLL)
        print("   这台机器上装的是加锁的那份，做 A/B 请改装")
        print("   02_构建\\build_1.0.13.10_dev\\obs-beauty.dll（诊断版，版本串相同，")
        print("   日志首行会是 'env override: open (dev build)'）。")
        return 2


    sets = {}
    for item in args.set:
        k, _, v = item.partition("=")
        if k not in PANEL_KEYS:
            print("!! 未知面板项 %s（可选：%s）" % (k, ", ".join(PANEL_KEYS)))
            return 2
        sets[k] = float(v)
    if sets and not args.no_patch:
        patch_scene(sets, args.tag)

    env = dict(os.environ)
    env["BEAUTY_PROFILE"] = "1"
    env["BEAUTY_MASK_EVERY"] = str(args.every)
    for item in args.env:
        k, _, v = item.partition("=")
        env[k] = v

    t_launch = time.time()
    print("[obs] 启动，every=%d，额外 env=%s" % (args.every, args.env or "无"))
    # --disable-shutdown-check：上一次非正常退出会让 OBS 弹「安全模式」对话框卡住启动
    proc = subprocess.Popen([OBS_BIN, "--disable-shutdown-check"], cwd=OBS_EXE_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log = None
    t0 = time.time()
    while time.time() - t0 < 25:
        log = newest_log(t_launch - 2)
        if log:
            break
        time.sleep(0.5)
    init_line = wait_line(log, "init OK", 25)
    print("[obs] 日志：%s" % log)
    print("[obs] " + (init_line or "!! 没等到 init OK"))
    if not init_line:
        proc.terminate()
        return 3

    import asyncio
    import websockets

    async def drive():
        async with websockets.connect(WS, max_size=8 << 20) as ws:
            hello = json.loads(await ws.recv())
            await ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1, "eventSubscriptions": 0}}))
            ident = json.loads(await ws.recv())
            print("[ws] 已连接（op=%s）" % ident.get("op"))

            async def req(rtype, params=None):
                rid = rtype
                msg = {"op": 6, "d": {"requestType": rtype, "requestId": rid,
                                      "requestData": params or {}}}
                await ws.send(json.dumps(msg))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("op") == 7 and m["d"].get("requestId") == rid:
                        return m["d"].get("responseData", {}), m["d"].get("requestStatus", {})

            print("[obs] 静置 %ds（预热 + 方向探测）" % args.lead)
            await asyncio.sleep(args.lead)

            if args.probe:
                d, st = await req("GetRecordStatus")
                print("[probe] 录制状态 ok=%s outputActive=%s" % (st.get("result"), d.get("outputActive")))
                await asyncio.sleep(6)
                await req("Quit")
                return

            phases = []
            if args.phases:
                for seg in args.phases.split(";"):
                    kv = {}
                    for item in seg.split(","):
                        item = item.strip()
                        if not item:
                            continue
                        k, _, v = item.partition("=")
                        kv[k.strip()] = float(v)
                    phases.append(kv)
                print("[phases] %d 段 × %d 轮 × %ds" % (len(phases), args.rounds, args.period))

            src, filt = "视频采集设备", "OBS美颜"
            base_settings = {}
            if phases:
                d, st = await req("GetSourceFilter", {"sourceName": src, "filterName": filt})
                base_settings = dict(d.get("filterSettings") or {})
                print("[phases] 读到当前面板：%s"
                      % {k: base_settings.get(k) for k in PANEL_KEYS if k in base_settings})

            d, st = await req("StartRecord")
            print("[rec] StartRecord ok=%s" % st.get("result"))

            marks = []
            if phases:
                for r in range(args.rounds):
                    for pid, kv in enumerate(phases):
                        merged = dict(base_settings)
                        merged.update(kv)
                        _d, s2 = await req("SetSourceFilterSettings",
                                           {"sourceName": src, "filterName": filt,
                                            "filterSettings": merged})
                        label = "P%d:%s" % (pid, ",".join("%s=%g" % (k, v) for k, v in kv.items()) or "base")
                        t_start = time.strftime("%H:%M:%S") + (".%03d" % (int(time.time() * 1000) % 1000))
                        await asyncio.sleep(args.period)
                        t_end = time.strftime("%H:%M:%S") + (".%03d" % (int(time.time() * 1000) % 1000))
                        marks.append((label, t_start, t_end))
                        print("[phase] r%d %-28s %s → %s (set ok=%s)"
                              % (r, label, t_start, t_end, s2.get("result")))
            else:
                await asyncio.sleep(args.seconds)

            d, st = await req("StopRecord")
            print("[rec] StopRecord ok=%s path=%s" % (st.get("result"), d.get("outputPath")))

            # 等 OBS 自己写完 finalize 与统计行再退出。
            # 判据用 "Recording Stop"：无丢帧时 OBS 不打印 "Video stopped..." 统计行，
            # 早先按那句话判断会把「正常收尾」误判成「卡住」。
            t_stop = time.time()
            seen = False
            while time.time() - t_stop < 30:
                if log and os.path.exists(log):
                    with io.open(log, "r", encoding="utf-8", errors="replace") as fh:
                        if "Recording Stop" in fh.read():
                            seen = True
                            break
                await asyncio.sleep(1)
            print("[rec] 停止确认：%s（耗时 %.1f s）"
                  % ("日志已写出 Recording Stop" if seen else "!! 30 s 内未见 Recording Stop",
                     time.time() - t_stop))
            await asyncio.sleep(2)
            await req("Quit")

            if marks:
                mdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ab_marks")
                if not os.path.isdir(mdir):
                    os.makedirs(mdir)
                mp = os.path.join(mdir, args.tag + ".tsv")
                with io.open(mp, "w", encoding="utf-8") as fh:
                    for label, a, b in marks:
                        fh.write("%s\t%s\t%s\n" % (label, a, b))
                print("[marks] %s" % mp)

    try:
        asyncio.run(drive())
    except Exception as exc:                      # noqa: BLE001
        print("!! websocket 流程失败：%r" % (exc,))
        try:
            proc.terminate()
        except Exception:
            pass
        return 4

    try:
        proc.wait(timeout=25)
    except subprocess.TimeoutExpired:
        proc.terminate()
    print("[dll] obs-beauty.dll sha256[:32] = %s" % sha256(DLL))
    print("[log] %s" % log)
    with io.open(log, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "性能 " in line or "Recording " in line or "skipped frames" in line:
                print("   " + line.strip())

    mpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ab_marks", args.tag + ".tsv")
    if os.path.exists(mpath):
        analyze_phases(log, mpath)
    return 0


def _sec(ts):
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def analyze_phases(log, mpath, memcpy_ms=0.7):
    """把每个「性能」窗口归到相位，只保留整段落在相位内的窗口。

    相位边界由 ab_run 写下的 marks 决定（墙钟时刻，与日志同源）。
    跨边界的窗口一律丢弃 —— 它混了两个相位，归到哪边都是错的。
    """
    import re
    RE = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3}).*性能\s+\d+x\d+：下载\s+([\d.]+)\s*\+\s*引擎\s+([\d.]+)"
                    r"\s*\+\s*上传\s+([\d.]+)\s*=\s*([\d.]+).*无脸跳过\s+(\d+)")
    windows = []
    with io.open(log, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = RE.match(line)
            if m:
                windows.append({"end": _sec(m.group(1)), "ts": m.group(1),
                                "dl": float(m.group(2)), "engine": float(m.group(3)),
                                "up": float(m.group(4)), "total": float(m.group(5)),
                                "noface": int(m.group(6)), "frames": 180})
    phases = []
    with io.open(mpath, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                phases.append((parts[0], _sec(parts[1]), _sec(parts[2])))

    buckets = {}
    prev_end = None
    for w in windows:
        for i, (label, a, b) in enumerate(phases):
            if prev_end is not None and prev_end >= a and w["end"] <= b:
                buckets.setdefault(i, []).append(w)
                break
        prev_end = w["end"]

    if not buckets:
        print("[phase] 没有整段落在相位内的窗口，无法归因")
        return

    def stat(ws):
        frames = sum(w["frames"] for w in ws)
        noface = sum(w["noface"] for w in ws)
        proc = frames - noface
        # 处理帧太少时，「扣掉无脸帧」的折算会把分母压到很小，结果失真到离谱
        # （实测一段 720/720 无脸会算出 154 ms）。低于 30% 直接判样本不足，
        # 不参与任何比较。
        if proc < 0.3 * frames:
            return None
        eng_sum = sum(w["engine"] * w["frames"] for w in ws)
        dl = sum(w["dl"] * w["frames"] for w in ws) / frames
        up = sum(w["up"] * w["frames"] for w in ws) / frames
        eng_proc = (eng_sum - noface * memcpy_ms) / proc
        return len(ws), frames, noface, eng_sum / frames, eng_proc, eng_proc + dl + up

    print("\n[phase] 分段结果（只含整段落在相位内的窗口；proc 按处理帧折算，memcpy=%.2f ms）" % memcpy_ms)
    print("   %-3s %-30s %5s %6s %7s %9s %9s %9s" % ("段", "相位", "窗口", "帧", "无脸", "引擎raw", "引擎proc", "合计proc"))
    agg = {}
    for i, (label, _a, _b) in enumerate(phases):
        ws = buckets.get(i)
        if not ws:
            print("   %-3d %-30s %5s" % (i + 1, label, "0(全被跨边界剔掉)"))
            continue
        res = stat(ws)
        if res is None:
            print("   %-3d %-30s 样本不足（处理帧 < 30%%），不计入" % (i + 1, label))
            continue
        n, frames, noface, er, ep, tp = res
        print("   %-3d %-30s %5d %6d %7d %9.2f %9.2f %9.2f" % (i + 1, label, n, frames, noface, er, ep, tp))
        agg.setdefault(label, []).append((n, frames, noface, er, ep, tp))

    print("\n[phase] 按相位合并")
    print("   %-30s %5s %6s %7s %9s %9s %9s" % ("相位", "窗口", "帧", "无脸", "引擎raw", "引擎proc", "合计proc"))
    for label, lst in agg.items():
        n = sum(x[0] for x in lst)
        frames = sum(x[1] for x in lst)
        noface = sum(x[2] for x in lst)
        er = sum(x[3] for x in lst) / len(lst)
        ep = sum(x[4] for x in lst) / len(lst)
        tp = sum(x[5] for x in lst) / len(lst)
        print("   %-30s %5d %6d %7d %9.2f %9.2f %9.2f" % (label, n, frames, noface, er, ep, tp))


if __name__ == "__main__":
    sys.exit(main())
