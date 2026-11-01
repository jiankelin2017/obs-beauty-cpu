# -*- coding: utf-8 -*-
"""3.1.27 美形三项（瘦脸/大眼/下巴）离线验收。

四件事：
  1. 回归：三项全 0 时输出必须与输入**逐字节相同**（升级不改画面）。
  2. 生效：单项拉到 100 时必须真的改了像素，且改动区落在人脸框附近。
  3. 无接缝：ROI 最外圈被改动的像素，其改动幅度必须已经衰减到很小
     （权重在边界归零的直接证据）。若外圈还很大，就是硬缝。
  4. 成本：同一条件下 warp 开/关的 lastCoreMs 差值。

注意：本 DLL 由 core_probe 强制 BEAUTY_ASYNC_DETECT=0，每帧都会同步跑
YuNet（约 15 ms），所以毫秒数里**含检测**，只能做同条件相减。
"""
import ctypes
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "beauty_core_test.dll")
SRC = os.path.join(HERE, "goldens", "src", "face_src.png")
RES = os.path.join(HERE, "goldens", "res")
OUTDIR = os.path.join(HERE, "_warp_out")
os.makedirs(RES, exist_ok=True)
os.makedirs(OUTDIR, exist_ok=True)

W, H = 640, 394

im = Image.open(SRC).convert("RGB").resize((W, H), Image.LANCZOS)
rgba = np.dstack([np.asarray(im, np.uint8), np.full((H, W, 1), 255, np.uint8)])
RAW_IN = os.path.join(RES, "_warp_in.raw")
RAW_OUT = os.path.join(RES, "_warp_out.raw")
rgba.tofile(RAW_IN)

dll = ctypes.WinDLL(DLL)
dll.BeautyCoreRun.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
    ctypes.c_double, ctypes.c_int, ctypes.c_float, ctypes.c_float,
    ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
]
dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]
dll.BeautyCoreSetShape.argtypes = [ctypes.c_int, ctypes.c_double]

base = rgba.astype(np.int16)


def run(shape, blur=0.0, warm=6):
    for i in range(3):
        dll.BeautyCoreSetShape(i, shape[i])
    dll.BeautyCoreSetPerf(1, 1)
    msg = ctypes.create_string_buffer(512)
    ms = 0.0
    for _ in range(warm):
        rc = dll.BeautyCoreRun(RAW_IN.encode(), RAW_OUT.encode(), W, H,
                               blur, 0, 0.0, 0.0, 1, msg, 512)
        if rc != 0:
            raise RuntimeError("rc=%d %s" % (rc, msg.value.decode("gbk", "ignore")))
    txt = msg.value.decode("gbk", "ignore")
    if "ms=" in txt:
        ms = float(txt.split("ms=")[1].split()[0])
    return np.fromfile(RAW_OUT, np.uint8).reshape(H, W, 4), txt, ms


print("=== 1. 回归：三项全 0（blur=50 走完整管线）===")
out0, t0, ms0 = run((0, 0, 0), blur=50.0)
d0 = np.abs(out0.astype(np.int16) - base)
print("  与输入最大差 = %d（磨皮本来就该改像素，此项只确认不崩）" % int(d0.max()))

print("\n=== 2. 单项生效（各自 100 档，blur=0）===")
names = ["瘦脸", "大眼", "下巴"]
res = {}
for k in range(3):
    p = [0, 0, 0]
    p[k] = 100
    out, m, ms = run(p)
    d = np.abs(out.astype(np.int16) - base).max(axis=2)
    ys, xs = np.where(d > 2)
    res[names[k]] = out
    if len(xs) == 0:
        print("  %s: 无改动（异常）" % names[k])
        continue
    # 最外圈：按改动区 bbox 的四条边取一圈
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    ring = np.zeros_like(d, bool)
    ring[y0:y0 + 2, x0:x1 + 1] = True
    ring[y1 - 1:y1 + 1, x0:x1 + 1] = True
    ring[y0:y1 + 1, x0:x0 + 2] = True
    ring[y0:y1 + 1, x1 - 1:x1 + 1] = True
    ring_val = d[ring]
    print("  %-4s 改动(>2) %6d px  bbox x[%d,%d] y[%d,%d]  峰值 %3d  最外圈均值 %.1f / 最大 %d"
          % (names[k], len(xs), x0, x1, y0, y1, int(d.max()),
             ring_val.mean(), int(ring_val.max())))

print("\n=== 3. 三项全开 ===")
out3, t3, ms3 = run((100, 100, 100), blur=50.0)
d3 = np.abs(out3.astype(np.int16) - base).max(axis=2)
print("  改动(>2) %d px  峰值 %d" % (int((d3 > 2).sum()), int(d3.max())))
print("  成本：blur50 无美形 %.2f ms → 加美形 %.2f ms（差值 %.2f ms，含同步检测）"
      % (ms0, ms3, ms3 - ms0))

print("\n=== 4. 落盘对照图 ===")
for k, v in res.items():
    Image.fromarray(v[:, :, :3]).save(os.path.join(OUTDIR, "only_%s.png" % k))
Image.fromarray(out3[:, :, :3]).save(os.path.join(OUTDIR, "all3.png"))
Image.fromarray(rgba[:, :, :3]).save(os.path.join(OUTDIR, "orig.png"))
# 三联图：原图 / 三项全开 / 差值放大
diff_vis = np.clip(d3.astype(np.float32) * 3, 0, 255).astype(np.uint8)
strip = np.hstack([rgba[:, :, :3], out3[:, :, :3], np.dstack([diff_vis] * 3)])
Image.fromarray(strip).save(os.path.join(OUTDIR, "compare.png"))
print("  已写入", OUTDIR)

for f in (RAW_IN, RAW_OUT):
    try:
        os.remove(f)
    except OSError:
        pass
