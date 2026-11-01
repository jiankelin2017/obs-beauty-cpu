# -*- coding: utf-8 -*-
"""protect_test.py —— 验证五官保护只作用在眼睛/嘴巴上

判据（两条必须同时成立）：
  1. 眼睛区域磨皮量明显下降
  2. 脸颊区域磨皮量基本不变

只做到 1 就是「整体减弱」，不是保护。
"""

import ctypes
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')

W, H = 640, 394

# face_src 上的人脸大致位置（YuNet 检出 x=277 y=89 w=107 h=134）
# 眼睛横带、脸颊、嘴巴三段用于分区
# 注意：脸只有 134 px 高（y 89~223），眼睛在 y≈140、嘴在 y≈190，
# 中间几乎没有「干净」的间隔。所以对照区选**额头**（眼睛上方），
# 不能选「脸颊」—— 那个位置会和嘴巴椭圆重叠，测出来是错的。
REGIONS = {
    '眼睛区': (295, 355, 128, 155),
    '额头区（对照）': (300, 360, 100, 122),
    '嘴周区': (310, 360, 180, 205),
}

PROTECT = 80   # 主程序默认值，必须是常量 —— 子进程读环境变量


def load(p):
    return np.fromfile(p, np.uint8).reshape((H, W, 4))


def smooth_amount(out, src):
    d = np.abs(out[:, :, :3].astype(np.float32) - src[:, :, :3].astype(np.float32))
    return d.mean(axis=2)


_dll = None


def run_once(protect_k):
    global _dll
    if _dll is None:
        _dll = ctypes.WinDLL(DLL)
        _dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                       ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                       ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _dll.BeautyCoreRun.restype = ctypes.c_int
        _dll.BeautyCoreSetProtectK.argtypes = [ctypes.c_int]
        _dll.BeautyCoreSetProtectK.restype = None
    _dll.BeautyCoreSetProtectK(protect_k)
    raw = os.path.join(RES, '640x394.raw')
    out = os.path.join(OUT, '_pt.raw')
    msg = ctypes.create_string_buffer(512)
    for _ in range(5):
        _dll.BeautyCoreRun(raw.encode(), out.encode(), W, H, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    _dll.BeautyCoreRun(raw.encode(), out.encode(), W, H, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    return load(out).copy()


def main():
    src = load(os.path.join(RES, '640x394.raw'))
    off = run_once(0)
    on = run_once(PROTECT)
    a_off = smooth_amount(off, src)
    a_on = smooth_amount(on, src)

    print('protectK: 0（关闭） vs %d（默认）' % PROTECT)
    print()
    print('%-14s %12s %12s %10s' % ('区域', '关闭时磨皮量', '开启时', '相对'))
    for name, (x0, x1, y0, y1) in REGIONS.items():
        v0 = a_off[y0:y1, x0:x1].mean()
        v1 = a_on[y0:y1, x0:x1].mean()
        rel = 100.0 * v1 / v0 if v0 > 1e-6 else 0.0
        print('%-14s %12.3f %12.3f %9.1f%%' % (name, v0, v1, rel))

    print()
    d = np.any(off != on, axis=2)
    print('两个版本输出有差异的像素：%d' % d.sum())
    if d.sum():
        ys, xs = np.nonzero(d)
        print('  差异范围 x %d~%d, y %d~%d（应集中在眼睛/嘴巴附近）'
              % (xs.min(), xs.max(), ys.min(), ys.max()))

    tmp = os.path.join(OUT, '_pt.raw')
    if os.path.exists(tmp):
        os.remove(tmp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
