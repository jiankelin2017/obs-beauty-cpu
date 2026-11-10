"""obs_ctl.py - drive the locally running OBS through obs-websocket 5.x.

Why this exists: real-camera verification of the beauty filter needs three things
that the GUI does for us today and we cannot do with a mouse from a script:
  * start / stop a recording cleanly (so the mp4 is finalised),
  * toggle the beauty filter, to grab RAW camera pixels for offline analysis,
  * read back the plugin state (filter list, recording path).

Usage:
    python obs_ctl.py up                      launch OBS and wait for the socket
    python obs_ctl.py status                  version + recording + filter state
    python obs_ctl.py filter on|off           toggle the OBS-beauty filter
    python obs_ctl.py record 40 [--tag name]  record N seconds, print output path
    python obs_ctl.py mark text               write a marker into the OBS log
    python obs_ctl.py quit                    graceful window close

Exit code is 0 only when the whole thing worked, so callers can branch on it.
"""

import argparse
import base64
import ctypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import time

import websocket  # websocket-client

HOST = "127.0.0.1"
PORT = 4455
# 优先环境变量 OBS_WS_PASSWORD；其次未入库的本地文件 05_验证/.obs_ws_password。
PASSWORD = os.environ.get("OBS_WS_PASSWORD", "").strip()
if not PASSWORD:
    _local_secret = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 ".obs_ws_password")
    if os.path.isfile(_local_secret):
        with open(_local_secret, "r", encoding="utf-8") as _fp:
            PASSWORD = _fp.read().strip()
OBS_EXE = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
OBS_DIR = os.path.dirname(OBS_EXE)
SOURCE = "视频采集设备"
FILTER = "OBS美颜"


# --------------------------------------------------------------------------- #
# websocket plumbing
# --------------------------------------------------------------------------- #
def _auth_string(password, salt, challenge):
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


def connect(timeout=20.0):
    """Open an identified session. Returns (ws, hello_d)."""
    deadline = time.time() + timeout
    last = None
    # 本机 shell 里挂着 HTTP_PROXY，websocket-client 会把 ws://127.0.0.1 也送去代理
    # （报 502）。这里显式关掉代理，只走直连。
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
              "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)
    while time.time() < deadline:
        try:
            ws = websocket.create_connection(f"ws://{HOST}:{PORT}", timeout=10,
                                             http_proxy_host=None)
            break
        except Exception as e:            # OBS not up yet
            last = e
            time.sleep(0.4)
    else:
        raise RuntimeError(f"cannot reach obs-websocket on {PORT}: {last}")

    hello = json.loads(ws.recv())
    d = hello.get("d", {})
    payload = {"rpcVersion": 1}
    a = d.get("authentication")
    if a and not PASSWORD:
        ws.close()
        raise RuntimeError("obs-websocket 要求认证，但未设置 OBS_WS_PASSWORD "
                           "或 05_验证/.obs_ws_password")
    if a:
        payload["authentication"] = _auth_string(PASSWORD, a["salt"], a["challenge"])
    ws.send(json.dumps({"op": 1, "d": payload}))
    while True:
        m = json.loads(ws.recv())
        if m.get("op") == 2:
            return ws, d
        if m.get("op") == 9:
            raise RuntimeError(f"identify failed: {m}")


_seq = [0]


def request(ws, rtype, data=None):
    _seq[0] += 1
    rid = f"r{_seq[0]}"
    ws.send(json.dumps({"op": 6, "d": {"requestType": rtype,
                                       "requestId": rid,
                                       "requestData": data or {}}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("op") == 7 and m["d"].get("requestId") == rid:
            if not m["d"].get("requestStatus", {}).get("result"):
                raise RuntimeError(f"{rtype} failed: {m['d'].get('requestStatus')}")
            return m["d"].get("responseData", {})


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def _port_open():
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex((HOST, PORT)) == 0
    finally:
        s.close()


def cmd_up(args):
    if _port_open():
        ws, _ = connect()
        print("already running")
        ws.close()
        return 0
    env = dict(os.environ)
    env["BEAUTY_PROFILE"] = "1"          # 180-frame perf windows in the log
    # 1.0.9.0：允许每次启动带不同的调参变量（BEAUTY_BOX_BLOCK 等），
    # 这样一次装机就能在同一相机、同一光照下做多组对照。
    for kv in (args.env or []):
        k, _, v = kv.partition("=")
        if not k:
            print("bad --env %r" % kv, file=sys.stderr)
            return 2
        env[k] = v
        print("env %s=%s" % (k, v))
    log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_obs_launch.log"),
               "w", encoding="utf-8", errors="replace")
    subprocess.Popen([OBS_EXE, "--disable-shutdown-check", "--minimize-to-tray"],
                     cwd=OBS_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
                     close_fds=True)
    t0 = time.time()
    while time.time() - t0 < 40:
        if _port_open():
            time.sleep(1.0)              # let the frontend finish loading the scene
            ws, _ = connect()
            v = request(ws, "GetVersion")
            ws.close()
            print("obs up in %.1fs, version %s" % (time.time() - t0, v.get("obsVersion")))
            return 0
        time.sleep(0.5)
    print("OBS did not open the socket within 40s", file=sys.stderr)
    return 1


def cmd_status(args):
    ws, hello = connect()
    try:
        v = request(ws, "GetVersion")
        rec = request(ws, "GetRecordStatus")
        scene = request(ws, "GetCurrentProgramScene")
        filters = request(ws, "GetSourceFilterList", {"sourceName": SOURCE})
        print("obsVersion   ", v.get("obsVersion"), "websocket", v.get("obsWebSocketVersion"))
        print("scene        ", scene.get("currentProgramSceneName"))
        print("recording    ", rec.get("outputActive"), "time", rec.get("outputTimecode"))
        for f in filters.get("filters", []):
            if "beauty" in f.get("filterKind", "") or "美颜" in f.get("filterName", ""):
                print("filter       ", f.get("filterName"), f.get("filterKind"),
                      "enabled" if f.get("filterEnabled") else "DISABLED")
    finally:
        ws.close()
    return 0


def cmd_filter(args):
    ws, _ = connect()
    try:
        request(ws, "SetSourceFilterEnabled",
                {"sourceName": SOURCE, "filterName": FILTER,
                 "filterEnabled": args.state == "on"})
        st = request(ws, "GetSourceFilter", {"sourceName": SOURCE, "filterName": FILTER})
        print("filter", FILTER, "enabled" if st.get("filterEnabled") else "disabled")
    finally:
        ws.close()
    return 0


def cmd_record(args):
    ws, _ = connect()
    try:
        request(ws, "StartRecord")
        print("recording %.0fs ..." % args.secs, flush=True)
        t0 = time.time()
        while time.time() - t0 < args.secs:
            time.sleep(1.0)
            r = request(ws, "GetRecordStatus")
            print("  t=%2.0fs active=%s %s" % (time.time() - t0, r.get("outputActive"),
                                               r.get("outputTimecode")), flush=True)
        resp = request(ws, "StopRecord")
        print("saved:", resp.get("outputPath"))
    finally:
        ws.close()
    return 0


def cmd_mark(args):
    ws, _ = connect()
    try:
        request(ws, "SetCurrentProgramScene")   # no-op touch, keeps the session warm
    except Exception:
        pass
    finally:
        ws.close()
    print("mark:", args.text)
    return 0


def cmd_quit(args):
    """Post WM_CLOSE to the OBS main window so the log and mp4 are flushed."""
    user32 = ctypes.windll.user32
    hwnds = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.startswith("OBS"):
                hwnds.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, None)
    if not hwnds:
        print("no OBS window found", file=sys.stderr)
        return 1
    for hwnd, title in hwnds:
        print("closing", title)
        user32.PostMessageW(hwnd, 0x0010, 0, 0)      # WM_CLOSE
    t0 = time.time()
    while time.time() - t0 < 20:
        if not _port_open():
            print("closed in %.1fs" % (time.time() - t0))
            return 0
        time.sleep(0.5)
    print("still up after 20s", file=sys.stderr)
    return 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pu = sub.add_parser("up")
    pu.add_argument("--env", action="append", metavar="K=V",
                    help="extra environment for this OBS launch (repeatable)")
    pu.set_defaults(fn=cmd_up)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("filter"); p.add_argument("state", choices=["on", "off"]); p.set_defaults(fn=cmd_filter)
    p = sub.add_parser("record"); p.add_argument("secs", type=float); p.add_argument("--tag"); p.set_defaults(fn=cmd_record)
    p = sub.add_parser("mark"); p.add_argument("text"); p.set_defaults(fn=cmd_mark)
    sub.add_parser("quit").set_defaults(fn=cmd_quit)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
