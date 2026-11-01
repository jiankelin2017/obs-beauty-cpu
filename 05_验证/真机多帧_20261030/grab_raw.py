# -*- coding: utf-8 -*-
"""抓 N 张「关掉自研滤镜」的原始摄像头帧（场景级截图）。
dshow_input 是 async 源，GetSourceScreenshot 直抓源返回全黑，必须抓场景。
"""
import json, base64, time, os, sys
import websocket

URL = "ws://127.0.0.1:4455"
SCENE = "美颜测试"
SRC = "视频采集设备"
FILTER = "OBS美颜"
OUT = r"C:/btwork/live_check/raw2"
_id = [0]


def connect():
    ws = websocket.create_connection(URL, timeout=15)
    ws.recv()
    ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1}}))
    ws.recv()
    return ws


def req(ws, t, d=None):
    _id[0] += 1
    ws.send(json.dumps({"op": 6, "d": {"requestType": t, "requestId": str(_id[0]),
                                      "requestData": d or {}}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("op") == 7:
            return m["d"]


def set_filter(ws, on):
    return req(ws, "SetSourceFilterEnabled",
               {"sourceName": SRC, "filterName": FILTER, "filterEnabled": bool(on)})["requestStatus"]["result"]


def shot(ws, path, w=1920, h=1080):
    d = req(ws, "GetSourceScreenshot", {"sourceName": SCENE, "imageFormat": "png",
                                        "imageWidth": w, "imageHeight": h})
    if not d["requestStatus"]["result"]:
        return False
    open(path, "wb").write(base64.b64decode(d["responseData"]["imageData"].split(",", 1)[1]))
    return True


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    gap = float(sys.argv[2]) if len(sys.argv) > 2 else 0.55
    os.makedirs(OUT, exist_ok=True)
    ws = connect()
    print("关闭滤镜:", set_filter(ws, False))
    time.sleep(0.8)
    ok = 0
    for i in range(n):
        p = os.path.join(OUT, "raw_%02d.png" % i)
        if shot(ws, p):
            ok += 1
            print("  %s %d bytes" % (os.path.basename(p), os.path.getsize(p)))
        time.sleep(gap)
    print("恢复滤镜:", set_filter(ws, True))
    st = req(ws, "GetSourceFilter", {"sourceName": SRC, "filterName": FILTER})["responseData"]
    print("确认 enabled =", st.get("filterEnabled"), "| 抓到", ok, "张")
