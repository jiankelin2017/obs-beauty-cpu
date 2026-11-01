import json, base64, sys, time, websocket

URL = "ws://127.0.0.1:4455"
PW = "REDACTED"


def connect():
    ws = websocket.create_connection(URL, timeout=10)
    hello = json.loads(ws.recv())
    ident = {"op": 1, "d": {"rpcVersion": 1}}
    ws.send(json.dumps(ident))
    r = json.loads(ws.recv())
    return ws, r


def req(ws, rtype, data=None):
    global _id
    _id += 1
    ws.send(json.dumps({"op": 6, "d": {"requestType": rtype, "requestId": str(_id),
                                      "requestData": data or {}}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("op") == 7:
            return m["d"]


_id = 0

if __name__ == "__main__":
    ws, hello = connect()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(req(ws, "GetVersion"), ensure_ascii=False))
        print(json.dumps(req(ws, "GetVideoSettings"), ensure_ascii=False))
        print(json.dumps(req(ws, "GetStats"), ensure_ascii=False))
        print(json.dumps(req(ws, "GetCurrentProgramScene"), ensure_ascii=False))
        print(json.dumps(req(ws, "GetInputList"), ensure_ascii=False)[:600])
    elif cmd == "shot":
        name = sys.argv[2]
        out = sys.argv[3]
        d = req(ws, "GetSourceScreenshot", {"sourceName": name,
                                            "imageFormat": "png",
                                            "imageWidth": 1280, "imageHeight": 720})
        if not d["requestStatus"]["result"]:
            print("ERR", d["requestStatus"])
        else:
            img = d["responseData"]["imageData"].split(",", 1)[1]
            open(out, "wb").write(base64.b64decode(img))
            print("saved", out)
    elif cmd == "filters":
        name = sys.argv[2]
        print(json.dumps(req(ws, "GetSourceFilterList", {"sourceName": name}), ensure_ascii=False))
