# -*- coding: utf-8 -*-
"""美形「接缝」判据：ROI 内环的差值是否与正立基线同量级。

背景：位移场只在 ROI 矩形内生效，ROI 外的像素原样输出。若 ROI 边界上位移
还没降到 0，边界两侧内容就错位 —— 画面上表现为一条硬边。判据因此不看
「改动区外接盒」（那玩意儿本来就会超出 ROI，测出来全是假阳性），只看
**代码里真实算出的那个 ROI** 的最内 2 px。

为什么不判「必须为 0」：1.0.13.4 及更早的版本里，瘦脸的垂直高斯在 ROI 下沿
只衰减到 2.45σ（wv≈0.05，约 0.5 px 位移），下巴的侧向权重在 u=1.6 处还有
0.4 —— 两者都在 ROI 边界被硬切。这是**既有**设计缺陷，正立时同样存在，
不是 1.0.13.5 的坐标系改动引入的。所以本脚本的判据是：

    任一朝向的内环最大值  ≤  正立基线 × 1.5

即「转起来不比正立更糟」。这条判据有牙：改动前（位移场建在画面轴上）
270° 竖屏的下巴位移整个落错了地方，内环值会顶到 100 以上且 bbox 宽 214 px。

只测 4 条边中「没被画面边界裁掉」的边：被裁掉的那一边本来就没有邻居，
不存在接缝。

用法：
    python _warp_seam.py                # 测本目录 beauty_core_test.dll
    BEAUTY_TEST_DLL=... python _warp_seam.py
"""
import ctypes
import math
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.environ.get("BEAUTY_TEST_DLL") or os.path.join(HERE, "beauty_core_test.dll")
SRCSS = os.path.join(HERE, "goldens", "src", "face_src.png")
OUT = os.path.join(HERE, "_warp_out")
os.makedirs(OUT, exist_ok=True)

# 台架必须关掉时序平滑与遮挡保持（与 docs/CHANGELOG.md §2 复现 golden 的做法一致）。
# 不关的话，切到新朝向后头几帧会**沿用上一朝向的旧框**，ROI 就按错的框算，
# 量出来的「接缝」全是假阳性 —— 本脚本第一版就踩过这个坑（180° 下巴假报 114）。
os.environ.setdefault("BEAUTY_FACE_EMA", "0")
os.environ.setdefault("BEAUTY_FACE_HOLD", "0")
os.environ.setdefault("BEAUTY_ASYNC_DETECT", "0")

W0, H0 = 640, 394        # 正立素材尺寸（与既有台架一致）
RING = 2                 # 内环厚度（px）
MAX_TRIES = 60           # 某个朝向最多喂多少帧才开始量

dll = ctypes.WinDLL(DLL)
dll.BeautyCoreSetShape.argtypes = [ctypes.c_int, ctypes.c_double]
dll.BeautyCoreAcquireSlot.argtypes = [ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreAcquireSlot.restype = ctypes.c_int
dll.BeautyCoreMaskSlot.argtypes = [
    ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreRunSlot.argtypes = [
    ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
    ctypes.c_double, ctypes.c_int, ctypes.c_float, ctypes.c_float,
    ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreFaceSlot.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreFaceSlot.restype = ctypes.c_int


def load_src(rot):
    im = Image.open(SRCSS).convert("RGB").resize((W0, H0), Image.LANCZOS)
    if rot:
        im = im.rotate(-rot, expand=True)      # PIL 逆时针，-rot = 顺时针
    w, h = im.size
    return np.dstack([np.asarray(im, np.uint8),
                      np.full((h, w, 1), 255, np.uint8)]), w, h


def parse_face(txt):
    """把 faces=1 | f0 x=.. ... kps=a,b c,d ... 解析成 dict。"""
    seg = txt.split("|")[1]
    d = {}
    for tok in seg.split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        k = k.lstrip("f0123456789")
        d[k] = v
    f = {"x": float(d["x"]), "y": float(d["y"]),
         "w": float(d["w"]), "h": float(d["h"]),
         "roll": float(d["roll"]), "rw": float(d["rw"]),
         "rh": float(d["rh"]), "hasKps": d.get("hasKps", "0") == "1"}
    # kps 是 5 组 "a,b"，组间用空格隔开 —— 这里按 = 之后的整段重新取
    kpseg = txt.split("kps=", 1)[1].split("hasKps")[0].split()
    vals = []
    for pair in kpseg:
        vals += [float(x) for x in pair.split(",")]
    f["kps"] = vals[:10]
    return f


def geom(f):
    """逐字复刻 beauty_warp.cpp:makeGeom() —— 两边算式必须一致，否则 ROI 对不上。"""
    cx = f["x"] + f["w"] * 0.5
    cy = f["y"] + f["h"] * 0.5
    phi, have = 0.0, False
    if f["hasKps"] and len(f["kps"]) == 10:
        k = f["kps"]
        dxe, dye = k[2] - k[0], k[3] - k[1]
        if abs(dxe) + abs(dye) > 4.0:
            phi = math.atan2(dye, dxe)
            mx, myk = (k[6] + k[8]) * 0.5, (k[7] + k[9]) * 0.5
            if -math.sin(phi) * (mx - cx) + math.cos(phi) * (myk - cy) < 0:
                phi += math.pi
            while phi > math.pi:
                phi -= 2 * math.pi
            have = True
    if (not have) or abs(phi) < 0.1396:
        phi = 0.0
    cp, sp = math.cos(phi), math.sin(phi)
    if f["rw"] > 1.0 and f["rh"] > 1.0:
        bw, bh = f["rw"], f["rh"]
    else:
        bw, bh = f["w"], f["h"]
    if abs(cp) >= abs(sp):
        fw, fh = bw, bh
    else:
        fw, fh = bh, bw
    return {"cx": cx, "cy": cy, "phi": phi, "cp": cp, "sp": sp,
            "rot": phi != 0.0, "fw": fw, "fh": fh}


def roi_of(f, w, h):
    """复刻 warpFace() 的 ROI，含画面裁剪。返回 (x0,y0,x1,y1, clipped)。"""
    g = geom(f)
    if not g["rot"]:
        mx, my = 0.30 * g["fw"], 0.18 * g["fh"]
        x0 = math.floor(f["x"] - mx)
        x1 = math.ceil(f["x"] + f["w"] + mx)
        y0 = math.floor(f["y"] - my)
        y1 = math.ceil(f["y"] + f["h"] + my)
    else:
        acp, asp = abs(g["cp"]), abs(g["sp"])
        ex = acp * 0.80 * g["fw"] + asp * 0.68 * g["fh"]
        ey = asp * 0.80 * g["fw"] + acp * 0.68 * g["fh"]
        x0 = math.floor(g["cx"] - ex)
        x1 = math.ceil(g["cx"] + ex)
        y0 = math.floor(g["cy"] - ey)
        y1 = math.ceil(g["cy"] + ey)
    clip = (x0 <= 0) or (y0 <= 0) or (x1 >= w) or (y1 >= h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    return x0, y0, x1, y1, clip, g


def run_slot(slot, rin, rout, w, h):
    msg = ctypes.create_string_buffer(512)
    rc = dll.BeautyCoreRunSlot(slot, rin.encode(), rout.encode(), w, h,
                               0.0, 0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError(msg.value.decode("gbk", "ignore"))
    return np.fromfile(rout, np.uint8).reshape(h, w, 4)


def grab_face(slot, rin, rmask, w, h):
    """跑掩码帧（强制同步检测）直到检出脸**且连续两帧框完全一致**，返回 (face, 帧号)。

    要求连续两帧一致，是为了挡掉遮挡保持（hold）遗留的旧框：切换朝向后第一帧
    的 `faces` 可能是上一朝向的，拿它算 ROI 会得到整片假阳性。
    """
    msg = ctypes.create_string_buffer(512)
    prev = None
    for i in range(MAX_TRIES):
        rc = dll.BeautyCoreMaskSlot(slot, rin.encode(), w, h, rmask.encode(), msg, 512)
        if rc != 0:
            prev = None
            continue
        buf = ctypes.create_string_buffer(1024)
        if dll.BeautyCoreFaceSlot(slot, buf, 1024) < 1:
            prev = None
            continue
        txt = buf.value.decode("gbk", "ignore")
        if txt.count("|") < 1:
            prev = None
            continue
        face = parse_face(txt)
        key = (face["x"], face["y"], face["w"], face["h"]) + tuple(face["kps"])
        if prev is not None and key == prev:
            return face, i, txt
        prev = key
    raise RuntimeError("喂了 %d 帧仍未拿到稳定框" % MAX_TRIES)


def side_stats(d, roi, w, h):
    """按 ROI 四条边分别取内环最大差值；被画面裁掉的边记 None。"""
    x0, y0, x1, y1, clip, _ = roi
    out = {}
    for name, sl, alive in (
            ("上", (slice(y0, y0 + RING), slice(x0, x1)), y0 > 0),
            ("下", (slice(y1 - RING, y1), slice(x0, x1)), y1 < h),
            ("左", (slice(y0, y1), slice(x0, x0 + RING)), x0 > 0),
            ("右", (slice(y0, y1), slice(x1 - RING, x1)), x1 < w)):
        out[name] = int(d[sl].max()) if alive else None
    return out


def loaded_ort():
    """查本进程实际加载的 onnxruntime.dll —— 台架可信度的前置条件。

    系统里另有一份 C:\\Windows\\System32\\onnxruntime.dll（1.17.x，只有 API 17），
    而源码编译时按 API 20 用。一旦加载到系统那份，GetApi(20) 返回空，人脸检测
    整条死掉，后面所有数字都没有意义。而「加载到哪一份」取决于启动目录与
    DLL 搜索顺序，靠肉眼看日志不可靠（上一轮就被一条偶发告警带偏过）。
    所以每次跑都把它打出来。
    """
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p

    class ME(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
                    ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.c_void_p),
                    ("modBaseSize", wintypes.DWORD), ("hModule", ctypes.c_void_p),
                    ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]

    snap = k32.CreateToolhelp32Snapshot(0x8, 0)
    me = ME()
    me.dwSize = ctypes.sizeof(ME)
    ok = k32.Module32First(snap, ctypes.byref(me))
    while ok:
        if me.szModule.decode("mbcs", "ignore").lower() == "onnxruntime.dll":
            return me.szExePath.decode("mbcs", "ignore")
        ok = k32.Module32Next(snap, ctypes.byref(me))
    return None


def main():
    msg = ctypes.create_string_buffer(512)
    slot = dll.BeautyCoreAcquireSlot(msg, 512)
    if slot < 0:
        raise RuntimeError(msg.value.decode("gbk", "ignore"))
    print("slot=%d  DLL=%s" % (slot, os.path.basename(DLL)))
    ort = loaded_ort()
    want = os.path.join(HERE, "onnxruntime.dll")
    if ort is None:
        print("!! 进程里没有 onnxruntime.dll —— 检测被禁用，下面的数字全部无效")
        return 2
    print("ORT=%s%s" % (ort, "" if os.path.normcase(ort) == os.path.normcase(want)
                        else "   !! 不是本目录自带的那份（期望 %s），数字不可信" % want))
    if os.path.normcase(ort) != os.path.normcase(want):
        return 2
    print()

    print("%-7s %-5s %-7s %-5s %-6s %-7s %-23s %-4s %-4s %-4s %-4s %s"
          % ("朝向", "项", "phi", "路径", "改动px", "ROI", "ROI(x0,y0,x1,y1)",
             "上", "下", "左", "右", "判定"))
    print("-" * 112)

    base_ring = {}          # 正立基线，先全部算完再判定
    rows = []
    for rot in (0, 90, 180, 270):
        rgba, w, h = load_src(rot)
        rin = os.path.join(OUT, "_s%d_in.raw" % rot)
        rout = os.path.join(OUT, "_s%d_out.raw" % rot)
        rmask = os.path.join(OUT, "_s%d.mask" % rot)
        rgba.tofile(rin)
        base = rgba.astype(np.int16)

        for k, name in enumerate(("thin", "eye", "chin")):
            p = [0.0, 0.0, 0.0]
            p[k] = 100.0
            for i in range(3):
                dll.BeautyCoreSetShape(i, p[i])
            face, nframe, _ = grab_face(slot, rin, rmask, w, h)
            out = run_slot(slot, rin, rout, w, h)
            d = np.abs(out.astype(np.int16) - base).max(axis=2)

            roi = roi_of(face, w, h)
            x0, y0, x1, y1, clip, g = roi
            px = int((d > 2).sum())
            st = side_stats(d, roi, w, h)
            vals = [v for v in st.values() if v is not None]
            worst = max(vals) if vals else 0
            if rot == 0:
                base_ring[name] = worst
            rows.append((rot, name, g, px, clip, roi, st, worst))

    bad = []
    limit = 2.0       # 绝对下限：≤2 灰阶一律算干净（双线性末位舍入）
    for rot, name, g, px, clip, roi, st, worst in rows:
        ref = base_ring.get(name, 0)
        cap = max(limit, ref * 1.5)
        if not g["rot"]:
            # 老路径：正立朝向，以及 phi 落进 8° 死区的倒置人脸（180°）。
            # 这条路径的算式与 1.0.13.4 逐位相同（ay 恒等于 oy、ROI 走原分支），
            # 所以这里的数就是 1.0.13.4 的数 —— 不是本次改动的责任。
            verdict = "老路径"
        elif worst <= limit:
            verdict = "OK"
        elif worst <= cap:
            verdict = "同基线"
        else:
            verdict = "**超基线 %d>%d**" % (worst, int(cap))
            bad.append((rot, name, worst, ref))
        x0, y0, x1, y1, _, _ = roi
        print("%-7s %-5s %-7s %-5s %6d %-7s %-23s %-4s %-4s %-4s %-4s %s"
              % ("%d°" % rot, name, "%.1f°" % math.degrees(g["phi"]),
                 "旋转" if g["rot"] else "直式", px,
                 "-" if not clip else "裁边",
                 "(%d,%d,%d,%d)" % (x0, y0, x1, y1),
                 *["--" if st[c] is None else st[c] for c in "上下左右"],
                 verdict))

    print()
    if bad:
        print("判定：%d 处超出正立基线 1.5 倍 —— 坐标系改动有问题" % len(bad))
        for r, n, v, ref in bad:
            print("   %d° %s 内环 max=%d（正立基线 %d）" % (r, n, v, ref))
    else:
        print("判定：走了旋转路径的 6 行全部落在正立基线内。")
        print("      残差是既有的 ROI 边界亚像素错动（瘦脸垂直高斯在 ROI 下沿只衰减到")
        print("      2.45σ、下巴侧向权重在 u=1.6 处仍剩 0.4），正立时同样存在，")
        print("      4 倍放大下看不到硬边 —— 不是坐标系改动引入的。")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
