# -*- coding: utf-8 -*-
"""交替 0/100 两次，验证实机滑杆是否真的改变画面（相邻帧肤色区平均 |Δ|）。
能抵消自动曝光漂移：0→100 与 100→0 两组互为对照。
"""
import json, base64, time, os
import cv2
import numpy as np
import websocket

URL = "ws://127.0.0.1:4455"
SCENE = "美颜测试"
SRC = "视频采集设备"
FILTER = "OBS美颜"
OUT = r"C:\btwork\live_check\ab01"
_id = [0]
os.makedirs(OUT, exist_ok=True)

ws = websocket.create_connection(URL, timeout=15)
ws.recv()
ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1}}))
ws.recv()


def req(t, d=None):
    _id[0] += 1
    ws.send(json.dumps({"op": 6, "d": {"requestType": t, "requestId": str(_id[0]),
                                      "requestData": d or {}}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("op") == 7:
            return m["d"]


cur = req("GetSourceFilter", {"sourceName": SRC, "filterName": FILTER})["responseData"]
st = cur["filterSettings"]
orig = st.get("blur_level")
print("orig blur_level =", orig)


def setlv(v):
    s = dict(st)
    s["blur_level"] = float(v)
    req("SetSourceFilterSettings", {"sourceName": SRC, "filterName": FILTER,
                                    "filterSettings": s, "overlay": True})
    time.sleep(0.8)


def shot(p):
    d = req("GetSourceScreenshot", {"sourceName": SCENE, "imageFormat": "png",
                                    "imageWidth": 1920, "imageHeight": 1080})
    open(p, "wb").write(base64.b64decode(d["responseData"]["imageData"].split(",", 1)[1]))


seq = []
try:
    for i, v in enumerate([0, 100, 0, 100]):
        setlv(v)
        p = os.path.join(OUT, "f%d_%03d.png" % (i, v))
        shot(p)
        seq.append((v, p))
        print("shot", v, os.path.basename(p))
finally:
    s = dict(st)
    s["blur_level"] = float(orig)
    req("SetSourceFilterSettings", {"sourceName": SRC, "filterName": FILTER,
                                    "filterSettings": s, "overlay": True})
    back = req("GetSourceFilter", {"sourceName": SRC, "filterName": FILTER})["responseData"]
    print("restored =", back["filterSettings"].get("blur_level"))


def mask(b):
    ycrcb = cv2.cvtColor(b, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    m = ((cr > 133) & (cr < 178) & (cb > 74) & (cb < 130) & (y > 45)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return cv2.erode((lab == k).astype(np.uint8), np.ones((11, 11), np.uint8))


imgs = [cv2.imread(p) for v, p in seq]
m = mask(imgs[0]) > 0
print("\n相邻两帧肤色区平均 |Δ|（同一次会话，交替 0/100）：")
for i in range(1, len(imgs)):
    d = np.abs(imgs[i].astype(np.float32) - imgs[i - 1].astype(np.float32)).mean(axis=2)
    l0 = cv2.cvtColor(imgs[i - 1], cv2.COLOR_BGR2GRAY)[m].mean()
    l1 = cv2.cvtColor(imgs[i], cv2.COLOR_BGR2GRAY)[m].mean()
    print("  %03d -> %03d : %.3f  (luma %.1f -> %.1f)" % (seq[i - 1][0], seq[i][0],
                                                          d[m].mean(), l0, l1))
