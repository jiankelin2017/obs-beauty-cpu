# -*- coding: utf-8 -*-
"""美形「位置」探针：单项 100 档时，改动落在哪里 vs 脸在哪里。

输出三联图（原图 / 变形后 / 改动热力图），并把改动的逐行/逐列分布打出来。
"""
import ctypes
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "beauty_core_test.dll")
SRCSS = os.path.join(HERE, "goldens", "src", "face_src.png")
OUT = os.path.join(HERE, "_warp_out")
os.makedirs(OUT, exist_ok=True)

W, H = 640, 394
im = Image.open(SRCSS).convert("RGB").resize((W, H), Image.LANCZOS)
rgba = np.dstack([np.asarray(im, np.uint8), np.full((H, W, 1), 255, np.uint8)])
RAW_IN = os.path.join(OUT, "_pin.raw")
RAW_OUT = os.path.join(OUT, "_pout.raw")
rgba.tofile(RAW_IN)

dll = ctypes.WinDLL(DLL)
dll.BeautyCoreRun.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
    ctypes.c_double, ctypes.c_int, ctypes.c_float, ctypes.c_float,
    ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreSetShape.argtypes = [ctypes.c_int, ctypes.c_double]


def run(shape, warm=6):
    for i in range(3):
        dll.BeautyCoreSetShape(i, shape[i])
    msg = ctypes.create_string_buffer(512)
    for _ in range(warm):
        rc = dll.BeautyCoreRun(RAW_IN.encode(), RAW_OUT.encode(), W, H,
                              0.0, 0, 0.0, 0.0, 1, msg, 512)
        if rc != 0:
            raise RuntimeError(msg.value.decode("gbk", "ignore"))
    out = np.fromfile(RAW_OUT, np.uint8).reshape(H, W, 4)
    return out, msg.value.decode("gbk", "ignore")


def report(name, d):
    ys, xs = np.where(d > 2)
    if len(xs) == 0:
        print("  %s: 无改动" % name)
        return
    print("  %-4s 改动 %6d px  bbox x[%d,%d] y[%d,%d]  峰值 %3d  质心 (%.1f, %.1f)"
          % (name, len(xs), xs.min(), xs.max(), ys.min(), ys.max(), int(d.max()),
             xs.mean(), ys.mean()))
    rows = (d > 2).sum(axis=1)
    nz = np.nonzero(rows)[0]
    top = nz[np.argsort(rows[nz])[-3:]]
    print("       改动最多的行(自顶向下): %s" % [(int(y), int(rows[y])) for y in sorted(top)])
    cols = (d > 2).sum(axis=0)
    nzc = np.nonzero(cols)[0]
    print("       水平范围 x[%d,%d]（画面中心 %d）" % (nzc.min(), nzc.max(), W // 2))


base = rgba.astype(np.int16)
for k, name in enumerate(["thin", "eye", "chin"]):
    p = [0, 0, 0]
    p[k] = 100
    out, txt = run(p)
    d = np.abs(out.astype(np.int16) - base).max(axis=2)
    print("\n[%s]" % name)
    report(name, d)
    vis = np.clip(d.astype(np.float32) * 5, 0, 255).astype(np.uint8)
    strip = np.hstack([rgba[:, :, :3], out[:, :, :3], np.dstack([vis] * 3)])
    Image.fromarray(strip).save(os.path.join(OUT, "pos_%s.png" % name))
print("\n图 -> %s/pos_*.png" % OUT)
