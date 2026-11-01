# -*- coding: utf-8 -*-
"""limit_knee_test.py —— 验证「阈值软膝」保护立体感

原理（lumina 的 uSmoothThreshold）：
    |src - smoothed| 小 = 细纹理（毛孔、斑点）→ 该磨
    |src - smoothed| 大 = 明暗交界（鼻梁侧、下颌线）→ 不该磨

三条判据：
  1. 高差值区（明暗交界）磨皮量应明显下降
  2. 低差值区（平坦皮肤）应基本不变
  3. 整体磨皮量不能掉太多（掉了「磨皮强度」就得不偿失）
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

_dll = None


def setup():
    global _dll
    if _dll is None:
        _dll = ctypes.WinDLL(DLL)
        _dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                       ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                       ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _dll.BeautyCoreRun.restype = ctypes.c_int
        _dll.BeautyCoreSetLimitThr.argtypes = [ctypes.c_int]
        _dll.BeautyCoreSetLimitThr.restype = None
    return _dll


def run(thr):
    dll = setup()
    dll.BeautyCoreSetLimitThr(thr)
    raw = os.path.join(RES, '640x394.raw').encode()
    out = os.path.join(OUT, '_lk.raw').encode()
    msg = ctypes.create_string_buffer(512)
    for _ in range(5):
        dll.BeautyCoreRun(raw, out, W, H, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    dll.BeautyCoreRun(raw, out, W, H, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    with open(out, 'rb') as f:
        return np.frombuffer(f.read(), np.uint8).reshape((H, W, 4)).copy()


def smooth_amount(out, src):
    d = np.abs(out[:, :, :3].astype(np.float32) - src[:, :, :3].astype(np.float32))
    return d.mean(axis=2)


def main():
    src = np.fromfile(os.path.join(RES, '640x394.raw'), np.uint8).reshape((H, W, 4))
    base = run(0)                      # 关闭软膝
    a_base = smooth_amount(base, src)

    print('%-6s %12s %14s %14s %10s' % ('thr', '总磨皮量', '高差值区', '低差值区', '整体变化'))
    print('%-6s %12.4f %14.4f %14.4f %10s'
          % ('0(关)', a_base.mean(), 0, 0, '—'))

    # 用 thr=0 时的「磨皮量」作为分区的代理指标：
    # 磨皮量大的地方通常就是平滑核跨过明暗交界的地方
    flat = a_base > 1e-6
    if flat.sum() == 0:
        print('没有像素被磨过')
        return 1
    vals = a_base[flat]
    thr_hi = np.percentile(vals, 85)
    high = np.zeros_like(flat)
    low = np.zeros_like(flat)
    high[flat] = vals >= thr_hi
    low[flat] = vals < thr_hi

    for thr in (15, 30, 50):
        out = run(thr)
        a = smooth_amount(out, src)
        rel = 100.0 * a.mean() / a_base.mean()
        print('%-6d %12.4f %14s %14s %9.1f%%'
              % (thr, a.mean(),
                 '%.1f%%' % (100.0 * a[high].mean() / a_base[high].mean()),
                 '%.1f%%' % (100.0 * a[low].mean() / a_base[low].mean()),
                 rel))

    tmp = os.path.join(OUT, '_lk.raw')
    if os.path.exists(tmp):
        os.remove(tmp)
    print()
    print('[判据] 高差值区应明显下降、低差值区接近 100%、整体下降不宜超过 15%')
    return 0


if __name__ == '__main__':
    sys.exit(main())
