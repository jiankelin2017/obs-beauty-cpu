# -*- coding: utf-8 -*-
"""mask_soft_edge.py —— 量化「软边掩码」是否消除了边界台阶

背景：对照实现的 skinMask 返回连续的 0..1 而不是布尔值，注释里写明理由是
「原图色度是 2x2 采样的，直接判断时肤色区边界呈锯齿，磨皮强度跟着锯齿突变，
鼻梁侧面这类明暗交界处会出现台阶状的硬边」。

我们原来是硬 0/255。这个脚本量化改前改后的差别：

指标 = 「磨皮量图」的空间梯度。磨皮量 = |output - input|（RGB 平均）。
硬边时，磨皮量在掩码边界处从满值突变到 0 → 梯度尖峰；
软边时是渐变 → 梯度平缓。

同时统计掩码值分布（软边应当有中间值）。
"""

import ctypes
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')


def main():
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreMask.restype = ctypes.c_int

    w, h = 640, 394
    raw = os.path.join(RES, '640x394.raw')
    tmp_out = os.path.join(OUT, '_se_out.raw')
    tmp_mask = os.path.join(OUT, '_se_mask.mask')

    src = np.fromfile(raw, np.uint8).reshape((h, w, 4))

    msg = ctypes.create_string_buffer(512)
    for _ in range(5):
        dll.BeautyCoreRun(raw.encode(), tmp_out.encode(), w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    dll.BeautyCoreRun(raw.encode(), tmp_out.encode(), w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    out = np.fromfile(tmp_out, np.uint8).reshape((h, w, 4))

    rc = dll.BeautyCoreMask(raw.encode(), w, h, tmp_mask.encode(), msg, 512)
    with open(tmp_mask, 'rb') as f:
        mw, mh = np.frombuffer(f.read(8), np.int32)
    mask = np.fromfile(tmp_mask, np.uint8, offset=8).reshape((mh, mw))

    # 掩码值分布
    vals, counts = np.unique(mask, return_counts=True)
    mid = vals[(vals > 0) & (vals < 255)]
    mid_px = counts[(vals > 0) & (vals < 255)].sum()
    print('== 掩码值分布 ==')
    print('  全零 %d px  |  满值(255) %d px  |  **中间值 %d px（%.1f%% 的非零像素）**'
          % ((mask == 0).sum(), (mask == 255).sum(), mid_px,
             100.0 * mid_px / max(1, (mask > 0).sum())))
    if len(mid):
        print('  中间值范围 %d ~ %d，共 %d 级' % (mid.min(), mid.max(), len(mid)))
    print('  → 硬边掩码这里应该是 0 px；有中间值才说明边界是渐变的')

    # 磨皮量图的空间梯度（衡量台阶）
    amt = np.abs(out[:, :, :3].astype(np.float32) - src[:, :, :3].astype(np.float32)).mean(axis=2)
    gx = np.abs(np.diff(amt, axis=1))
    gy = np.abs(np.diff(amt, axis=0))
    # 只看有磨皮的地方附近（磨皮量 > 0.2）
    near = amt[1:, 1:] > 0.2
    gsel = np.concatenate([gx[1:, :][near[:, :gx.shape[1]]].ravel(),
                           gy[:, 1:][near[:gy.shape[0], :]].ravel()])
    if len(gsel):
        print()
        print('== 磨皮量图的相邻像素跳变（越小越平滑）==')
        for p in (50, 90, 99, 99.9):
            print('  %5.1f%%   %.4f' % (p, np.percentile(gsel, p)))
        print('  均值 %.4f  最大 %.3f' % (gsel.mean(), gsel.max()))

    for f in (tmp_out, tmp_mask):
        if os.path.exists(f):
            os.remove(f)
    return 0


if __name__ == '__main__':
    sys.exit(main())
