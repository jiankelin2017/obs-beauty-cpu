# -*- coding: utf-8 -*-
"""ROI 假设验证：在美颜滤镜之前插一个缩放滤镜，压小人脸像素，看引擎耗时是否随之下降。

为什么这样做：磨皮 ROI 取的是人脸包围盒（beauty_core.cpp l.1853-1856，s3roi = bounds_），
脸在画面里占比越大，处理的像素越多。让被摄者前后走动可以验证，但人不用动也能验证——
把整个画面缩小，人脸像素同样变小，而人脸在画面中的相对位置不变。

做法：
  1. 起 OBS（--disable-shutdown-check，避开上次非正常退出的安全模式对话框）；
  2. 在「视频采集设备」的滤镜链 index 0 插入 scale_filter（即排在「OBS美颜」之前）；
  3. 设成指定分辨率（默认 960x540，像素数为原来的 1/4）；
  4. 录制 --seconds 秒；
  5. 删掉这个滤镜（无论成败都删），再退出。

用法：
    python roi_scale.py --res 960x540 --seconds 45
    python roi_scale.py --res 480x270 --seconds 45     # 像素数 1/16，信号更强
"""
import argparse
import asyncio
import io
import json
import os
import subprocess
import sys
import time

OBS_BIN = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
OBS_DIR = os.path.dirname(OBS_BIN)
LOGDIR = os.path.join(os.environ["APPDATA"], "obs-studio", "logs")
WS = "ws://127.0.0.1:4455"
SOURCE = u"视频采集设备"
FILTER = u"ROI探测_缩放"


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


def wait_line(log, needle, timeout):
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


async def req(ws, rtype, params=None, counter=None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    myid = "%s-%d" % (rtype, counter[0])
    await ws.send(json.dumps({"op": 6, "d": {"requestType": rtype,
                                             "requestId": myid,
                                             "requestData": params or {}}}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), 25)
        m = json.loads(raw)
        if m.get("op") == 7 and m.get("d", {}).get("requestId") == myid:
            st = m["d"].get("requestStatus", {})
            return m["d"].get("responseData", {}), st


async def connect_retry(timeout=40):
    import websockets
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        try:
            return await websockets.connect(WS, max_size=8 << 20)
        except Exception as exc:      # 端口还没起
            last = exc
            await asyncio.sleep(1)
    raise RuntimeError("连不上 obs-websocket：%r" % (last,))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", default="960x540", help="缩放后的分辨率，如 960x540")
    ap.add_argument("--seconds", type=int, default=45)
    ap.add_argument("--every", type=int, default=2, help="BEAUTY_MASK_EVERY，与基线保持一致")
    ap.add_argument("--lead", type=int, default=12, help="加完滤镜后静置多少秒再开录")
    args = ap.parse_args()

    env = os.environ.copy()
    env["BEAUTY_PROFILE"] = "1"          # 不开这个不会打印「性能」行
    env["BEAUTY_MASK_EVERY"] = str(args.every)

    t_launch = time.time()
    print("[obs] 启动，目标缩放分辨率 %s，every=%d" % (args.res, args.every))
    proc = subprocess.Popen([OBS_BIN, "--disable-shutdown-check"], cwd=OBS_DIR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log = None
    for _ in range(50):
        log = newest_log(t_launch - 2)
        if log:
            break
        time.sleep(0.5)
    init_line = wait_line(log, "init OK", 30)
    print("[obs] 日志：%s" % log)
    print("[obs] " + (init_line or "!! 没等到 init OK"))

    ws = await connect_retry()
    cnt = [0]
    added = False
    # obs-websocket 5.x：连上后必须先发 Identify，否则任何请求都会被 4007 拒掉
    await ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1, "eventSubscriptions": 0}}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 15))
        if m.get("op") == 2:       # Identified
            break
    try:
        d, st = await req(ws, "GetVersion", counter=cnt)
        print("[ws] OBS %s / obs-websocket %s" % (d.get("obsVersion"), d.get("obsWebSocketVersion")))

        d, st = await req(ws, "GetSourceFilterList", {"sourceName": SOURCE}, counter=cnt)
        before = [(f.get("filterIndex"), f.get("filterName"), f.get("filterKind"))
                  for f in d.get("filters", [])]
        print("[filter] 现有滤镜：%s" % (before,))

        # 上次异常留下的同名滤镜先删掉，否则 Create 会返回 False，而它可能排在美颜之后
        if any(f[1] == FILTER for f in before):
            d, st = await req(ws, "RemoveSourceFilter", {
                "sourceName": SOURCE, "filterName": FILTER}, counter=cnt)
            print("[filter] 清理残留 ok=%s" % st.get("result"))
            await asyncio.sleep(2)

        d, st = await req(ws, "CreateSourceFilter", {
            "sourceName": SOURCE, "filterName": FILTER,
            "filterKind": "scale_filter", "filterIndex": 0,
        }, counter=cnt)
        added = st.get("result")
        print("[filter] CreateSourceFilter ok=%s" % added)

        # filterIndex 在 Create 时没被采纳（实测新建的总落在末尾，即美颜之后），
        # 显式改索引。5.7.3 里 MoveSourceFilter 返回 False，改用 SetSourceFilterIndex。
        d, st = await req(ws, "SetSourceFilterIndex", {
            "sourceName": SOURCE, "filterName": FILTER, "filterIndex": 0,
        }, counter=cnt)
        print("[filter] SetSourceFilterIndex 0 ok=%s" % st.get("result"))
        if not st.get("result"):
            d, st = await req(ws, "MoveSourceFilter", {
                "sourceName": SOURCE, "filterName": FILTER, "movementType": "TOP",
            }, counter=cnt)
            print("[filter] 回退 MoveSourceFilter TOP ok=%s" % st.get("result"))

        d, st = await req(ws, "SetSourceFilterSettings", {
            "sourceName": SOURCE, "filterName": FILTER,
            "filterSettings": {"scale_type": "resolution", "resolution": args.res},
            "overlay": True,
        }, counter=cnt)
        print("[filter] SetSourceFilterSettings ok=%s" % st.get("result"))

        d, st = await req(ws, "GetSourceFilterList", {"sourceName": SOURCE}, counter=cnt)
        order = [(f.get("filterIndex"), f.get("filterName")) for f in d.get("filters", [])]
        print("[filter] 处理后顺序：%s" % (order,))
        if not order or order[0][1] != FILTER:
            raise RuntimeError("缩放滤镜没排到最前，顺序为 %s，本次数据不可用" % (order,))

        d, st = await req(ws, "GetSourceFilter", {
            "sourceName": SOURCE, "filterName": FILTER}, counter=cnt)
        print("[filter] 实际设置：enabled=%s settings=%s"
              % (d.get("filterEnabled"), json.dumps(d.get("filterSettings", {}), ensure_ascii=False)))

        await asyncio.sleep(args.lead)

        d, st = await req(ws, "StartRecord", counter=cnt)
        print("[rec] StartRecord ok=%s" % st.get("result"))
        await asyncio.sleep(args.seconds)
        d, st = await req(ws, "StopRecord", counter=cnt)
        print("[rec] StopRecord ok=%s path=%s" % (st.get("result"), d.get("outputPath")))

        t_stop = time.time()
        seen = False
        while time.time() - t_stop < 30:
            if log and os.path.exists(log):
                with io.open(log, "r", encoding="utf-8", errors="replace") as fh:
                    if "Recording Stop" in fh.read():
                        seen = True
                        break
            await asyncio.sleep(1)
        print("[rec] 停止确认：%s（%.1f s）" % ("已写出 Recording Stop" if seen else "!! 未见", time.time() - t_stop))
    finally:
        if added:
            try:
                d, st = await req(ws, "RemoveSourceFilter", {
                    "sourceName": SOURCE, "filterName": FILTER}, counter=cnt)
                print("[filter] RemoveSourceFilter ok=%s" % st.get("result"))
                # 上一次实测发现删除没有落盘到场景文件，这里等 OBS 把场景写完再退出
                await asyncio.sleep(2)
                d, st = await req(ws, "GetSourceFilterList", {"sourceName": SOURCE}, counter=cnt)
                left = [(f.get("filterIndex"), f.get("filterName")) for f in d.get("filters", [])]
                print("[filter] 退出前顺序：%s" % (left,))
            except Exception as exc:
                print("!! 删除滤镜失败：%r" % (exc,))
        try:
            await req(ws, "Quit", counter=cnt)
        except Exception:
            pass
        await asyncio.sleep(2)
        try:
            ws.close()
        except Exception:
            pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=15)
            except Exception:
                proc.terminate()

    if log and os.path.exists(log):
        print("\n[结果] 本段性能行：")
        with io.open(log, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if u"性能 " in line:
                    print("   " + line.strip().split("] ", 1)[-1])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
