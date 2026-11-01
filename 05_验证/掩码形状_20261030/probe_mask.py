# -*- coding: utf-8 -*-
"""抓「滤镜开 / 关」两帧，做差得到磨皮真实作用区域（掩码足迹），
用来看掩码边界是否与脸/脖子轮廓对齐、是否偏移。"""
import json, base64, time, os, sys
import websocket

URL = "ws://127.0.0.1:4455"
OUT = r"C:\btwork\mask_check\live"
os.makedirs(OUT, exist_ok=True)
_id = [0]

ws = websocket.create_connection(URL, timeout=20)
hello = json.loads(ws.recv())
ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1}}))
ws.recv()


def req(t, d=None):
    _id[0] += 1
    ws.send(json.dumps({"op": 6, "d": {"requestType": t, "requestId": str(_id[0]), "requestData": d or {}}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("op") == 7:
            return m["d"]


scene = req("GetCurrentProgramScene")["responseData"]["currentProgramSceneName"]
print("current scene:", scene)

# 找到挂了 obs-beauty 滤镜的源
items = req("GetSceneItemList", {"sceneName": scene})["responseData"]["sceneItems"]
target = None
for it in items:
    nm = it["sourceName"]
    try:
        fl = req("GetSourceFilterList", {"sourceName": nm})["responseData"]["filters"]
    except Exception:
        continue
    for f in fl:
        if "beauty" in f["filterKind"].lower() or "美颜" in f["filterName"]:
            target = (nm, f["filterName"], f["filterEnabled"])
            break
    if target:
        break
print("target:", target)
if not target:
    print("!! 没有找到美颜滤镜")
    sys.exit(1)
src, fname, enabled = target

st = req("GetSourceFilter", {"sourceName": src, "filterName": fname})["responseData"]["filterSettings"]
print("settings:", json.dumps({k: v for k, v in st.items() if k in
      ("blur_level", "whiten_level", "rosy_level", "clarity_level", "face_level", "enable")},
      ensure_ascii=False))


def shot(path):
    for _ in range(3):
        d = req("GetSourceScreenshot", {"sourceName": scene, "imageFormat": "png",
                                        "imageWidth": 1920, "imageHeight": 1080})
        raw = base64.b64decode(d["responseData"]["imageData"].split(",", 1)[1])
        open(path, "wb").write(raw)
        if len(raw) > 20000:
            return len(raw)
        time.sleep(0.4)
    return len(raw)


def set_en(v):
    req("SetSourceFilterEnabled", {"sourceName": src, "filterName": fname, "filterEnabled": v})
    time.sleep(1.0)


print("shot ON  ->", shot(os.path.join(OUT, "on.png")))
set_en(False)
print("shot OFF ->", shot(os.path.join(OUT, "off.png")))
set_en(True)
time.sleep(0.5)
print("restored enabled =", req("GetSourceFilter", {"sourceName": src, "filterName": fname})
      ["responseData"]["filterEnabled"])
print("blur_level now =", req("GetSourceFilter", {"sourceName": src, "filterName": fname})
      ["responseData"]["filterSettings"].get("blur_level"))
ws.close()
