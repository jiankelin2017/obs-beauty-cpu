# -*- coding: utf-8 -*-
"""ellipse_vs_skin.py —— 椭圆 mask 能否替代现在的「肤色∩人脸框」

背景：三个成熟开源实现都不做逐像素皮肤分割，而是用椭圆近似
（wtnl-zhi 明确写「不是像素级皮肤分割」）。原因是椭圆只要几个 float 参数，
可以当 uniform 传给 shader，**不需要下载整帧**。

系数直接抄 wtnl-zhi/obs-beauty-filter 的 face_landmarks.c：
    radius_x = face_width * 0.57
    radius_y = face_height * 0.55
（该仓库 GPL-2.0-or-later）

本脚本先验证 IoU，够了再写 C++ —— 避免白写。
"""

import ctypes
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
SRC = os.path.join(HERE, 'goldens', 'src')
OUT = os.path.join(HERE, 'goldens', 'masks')
W, H = 640, 394

# 抄来的系数
RX_K = 0.57
RY_K = 0.55


def binmask(m):
    return (m >= 128)


def iou(a, b):
    A, B = binmask(a), binmask(b)
    u = np.logical_or(A, B).sum()
    return float(np.logical_and(A, B).sum()) / float(u) if u else 0.0


def prf(pred, truth):
    P, T = binmask(pred), binmask(truth)
    tp = np.logical_and(P, T).sum()
    prec = float(tp) / float(P.sum()) if P.sum() else 0.0
    rec = float(tp) / float(T.sum()) if T.sum() else 0.0
    return prec, rec


def read_mask(path):
    with open(path, 'rb') as f:
        head = f.read(8)
    mw, mh = np.frombuffer(head, np.int32)
    data = np.fromfile(path, np.uint8, offset=8)
    return data.reshape((mh, mw))


def ellipse_mask(cx, cy, rx, ry, soft=1.0, w=W, h=H):
    """与将来 C++ 实现同构：归一化椭圆距离 → 像素距离 → 软边"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx + 0.5 - cx) / rx
    ny = (yy + 0.5 - cy) / ry
    d = np.sqrt(nx * nx + ny * ny)
    px = (d - 1.0) * min(rx, ry)          # 到边界的近似像素距离
    a = np.clip(1.0 - px / soft, 0.0, 1.0)
    return (a * 255).astype(np.uint8)


def main():
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreMask.restype = ctypes.c_int

    scenes = ['face_src', 'crop_a', 'crop_c', 'look1']
    tmp = os.path.join(OUT, '_ell_tmp.mask')
    rows = []

    for sid in scenes:
        raw = os.path.join(SRC, sid + '.raw')
        if not os.path.exists(raw):
            continue
        msg = ctypes.create_string_buffer(512)
        rc = dll.BeautyCoreMask(raw.encode('utf-8'), W, H,
                                tmp.encode('utf-8'), msg, 512)
        info = msg.value.decode('utf-8', 'replace')
        if rc != 0:
            print('%-10s 跳过：%s' % (sid, info))
            continue
        cur = read_mask(tmp)
        cov_cur = 100.0 * binmask(cur).mean()

        # 用当前掩码的实际包围盒反推「人脸框」（等价于 YuNet 框再外扩）
        ys, xs = np.nonzero(binmask(cur))
        bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
        cx = (bx0 + bx1) / 2.0
        cy = (by0 + by1) / 2.0
        # 注意：bbox 是「肤色∩框」的结果，比真实人脸框略窄。这里按真实框
        # 宽度反推：椭圆要盖住现有掩码，所以用 bbox 直接当脸框测一次。
        for k_tag, (kx, ky) in [('0.57/0.55', (RX_K, RY_K)),
                                ('0.62/0.62', (0.62, 0.62))]:
            rx = (bx1 - bx0 + 1) * kx
            ry = (by1 - by0 + 1) * ky
            ell = ellipse_mask(cx, cy, rx, ry, soft=2.0)
            p, r = prf(ell, cur)
            rows.append((sid, k_tag, 100.0 * binmask(ell).mean(),
                         iou(ell, cur), p, r, cov_cur))
            print('%-10s 系数%-10s 椭圆覆盖 %5.2f%% (现有 %5.2f%%)  IoU %.3f  P %.3f  R %.3f'
                  % (sid, k_tag, 100.0 * binmask(ell).mean(), cov_cur,
                     iou(ell, cur), p, r))

    if os.path.exists(tmp):
        os.remove(tmp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
