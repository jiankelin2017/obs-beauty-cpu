# -*- coding: utf-8 -*-
"""tone_test.py —— 验证美白 / 红润

三条判据：
  1. 美白：肤色区亮度上升，且**色相基本不变**（保色相是这一版的关键改进）
  2. 红润：R 上升、G 下降（提红压绿）
  3. 非皮肤区：一个字节都不动
"""

import ctypes
import colorsys
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')
W, H = 640, 394

# face_src 的肤色区（取脸中间一块，避开眼睛嘴巴）
SKIN = (310, 360, 175, 215)     # x0,x1,y0,y1
# 明确的非皮肤（背景白墙 / 深色衣领上方）
NONSKIN = (450, 550, 40, 120)

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
        _dll.BeautyCoreSetTone.argtypes = [ctypes.c_double, ctypes.c_double]
        _dll.BeautyCoreSetTone.restype = None
        _dll.BeautyCoreSetEdgeK.argtypes = [ctypes.c_int]
        _dll.BeautyCoreSetEdgeK.restype = None
        _dll.BeautyCoreSetProtectK.argtypes = [ctypes.c_int]
        _dll.BeautyCoreSetProtectK.restype = None
    return _dll


def run(whiten, red, blur=50.0):
    dll = setup()
    dll.BeautyCoreSetTone(whiten, red)
    raw = os.path.join(RES, '640x394.raw').encode()
    out = os.path.join(OUT, '_tone.raw').encode()
    msg = ctypes.create_string_buffer(512)
    for _ in range(5):
        dll.BeautyCoreRun(raw, out, W, H, blur, 0, 0.0, 0.0, 1, msg, 512)
    rc = dll.BeautyCoreRun(raw, out, W, H, blur, 0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError(msg.value.decode('utf-8', 'replace'))
    with open(out, 'rb') as f:
        return np.frombuffer(f.read(), np.uint8).reshape((H, W, 4)).copy()


def luma(a):
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def hue_deg(a):
    """按 HSV 算色相（0..360），向量化"""
    r = a[..., 0] / 255.0
    g = a[..., 1] / 255.0
    b = a[..., 2] / 255.0
    mx = np.max(a[..., :3], axis=-1) / 255.0
    mn = np.min(a[..., :3], axis=-1) / 255.0
    d = mx - mn
    safe = np.where(d < 1e-6, 1.0, d)
    h = np.where(mx == r, ((g - b) / safe) % 6,
                 np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4))
    return h * 60.0


def region(arr, box):
    x0, x1, y0, y1 = box
    return arr[y0:y1, x0:x1]


def main():
    src = np.fromfile(os.path.join(RES, '640x394.raw'), np.uint8).reshape((H, W, 4))
    base = run(0.0, 0.0)          # 只有磨皮，无美白红润

    print('%-14s %10s %12s %12s' % ('配置', '肤色区亮度', '色相偏移(°)', '非皮肤变化'))
    print('%-14s %10.2f %12s %12s' % ('无美白红润', region(luma(base), SKIN).mean(), '—', '—'))

    for wv in (30, 60, 100):
        out = run(float(wv), 0.0)
        dl = region(luma(out), SKIN).mean() - region(luma(base), SKIN).mean()
        # 色相偏移：只在亮度有变化的像素上算（避免把没动的背景算进来）
        ch = np.any(out != base, axis=2)
        sub = np.zeros_like(ch)
        x0, x1, y0, y1 = SKIN
        sub[y0:y1, x0:x1] = True
        sel = ch & sub
        if sel.sum():
            dh = np.abs(hue_deg(out)[sel] - hue_deg(base)[sel])
            dh = np.minimum(dh, 360 - dh)
            hue_shift = dh.mean()
        else:
            hue_shift = 0.0
        # 先切片再比较（直接拿二维布尔去索引三维数组会维度错位）
        nx0, nx1, ny0, ny1 = NONSKIN
        diff_ns = np.abs(out[ny0:ny1, nx0:nx1].astype(np.int16)
                         - base[ny0:ny1, nx0:nx1].astype(np.int16)).max()
        print('%-14s %+10.2f %12.2f %12d'
              % ('美白 %d' % wv, dl, hue_shift, diff_ns))

    print()
    for rv in (30, 60, 100):
        out = run(0.0, float(rv))
        a = region(out, SKIN).astype(np.float32).mean(axis=(0, 1))
        b = region(base, SKIN).astype(np.float32).mean(axis=(0, 1))
        print('%-14s ΔR=%+6.2f  ΔG=%+6.2f  ΔB=%+6.2f'
              % ('红润 %d' % rv, a[0] - b[0], a[1] - b[1], a[2] - b[2]))

    tmp = os.path.join(OUT, '_tone.raw')
    if os.path.exists(tmp):
        os.remove(tmp)
    print()
    print('[判据] 美白应提亮但色相偏移 <3°；红润应 ΔR>0 且 ΔG<0；'
          '非皮肤区变化必须为 0。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
