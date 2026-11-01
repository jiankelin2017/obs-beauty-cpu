# -*- coding: utf-8 -*-
"""surface3 ROI 等价性调试：定位 full 与 roi 的差异像素位置。"""
import ctypes, os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
SRC = os.path.join(HERE, 'goldens', 'src', 'face_src.png')

w, h = 640, 394
im = Image.open(SRC).convert('RGB').resize((w, h), Image.LANCZOS)
rgba = np.dstack([np.asarray(im, np.uint8), np.full((h, w, 1), 255, np.uint8)])
raw = os.path.join(RES, '_dbg_in.raw')
rgba.tofile(raw)

dll = ctypes.WinDLL(DLL)
dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_int, ctypes.c_double, ctypes.c_int,
                              ctypes.c_float, ctypes.c_float, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]


def run(use_roi):
    dll.BeautyCoreSetPerf(1, use_roi)
    out = os.path.join(RES, '_dbg_out.raw')
    msg = ctypes.create_string_buffer(512)
    for _ in range(6):
        dll.BeautyCoreRun(raw.encode(), out.encode(), w, h, 50.0, 0,
                          0.0, 0.0, 1, msg, 512)
    return np.fromfile(out, np.uint8).reshape(h, w, 4)


a = run(0)
b = run(1)
d = np.abs(a.astype(np.int16) - b.astype(np.int16))
print('maxdiff', d.max(), 'npix', int((d > 0).sum()))
ys, xs = np.where(d.max(axis=2) > 0)
print('bbox x', xs.min(), xs.max(), 'y', ys.min(), ys.max())
print('first 20:', list(zip(xs[:20].tolist(), ys[:20].tolist())))
print('src at first:', a[ys[0], xs[0]], 'vs', b[ys[0], xs[0]])
os.remove(raw)
os.remove(os.path.join(RES, '_dbg_out.raw'))
