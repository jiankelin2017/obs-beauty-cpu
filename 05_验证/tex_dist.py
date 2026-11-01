# -*- coding: utf-8 -*-
"""统计脸内像素的局部结构强度 |box3 - box7| 分布，用于定 kTexHi 阈值。"""
import os
import sys

import numpy as np

HERE = r'C:\legacy_e2e'
sys.path.insert(0, HERE)
import nz_probe_dlldir as nz  # noqa: E402

W, H = 1074, 604


def y_of(path):
    a = np.frombuffer(open(path, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return (a[:, :, 0].astype(np.float32) * 299 +
            a[:, :, 1].astype(np.float32) * 587 +
            a[:, :, 2].astype(np.float32) * 114) / 1000.0


def box(y, r):
    p = np.pad(y, r, mode='edge')
    ii = p.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1, 0), (1, 0)))
    k = 2 * r + 1
    s = (ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k])
    return s / (k * k)


def main():
    tag = 'kd_base'
    mw, mh, soft = nz.load_mask(tag)
    soft = np.frombuffer(soft, dtype=np.uint8).reshape(mh, mw)
    yi = (np.arange(H) * mh // H).clip(0, mh - 1)
    xi = (np.arange(W) * mw // W).clip(0, mw - 1)
    mask = soft[np.ix_(yi, xi)]           # 上采样到全帧
    print('mask %dx%d -> 全帧, 脸内像素 %d' % (mw, mh, int((mask >= 200).sum())))

    src = y_of(os.path.join(HERE, 'flick', 'nz_in', 'seq_000.raw'))
    hm = np.abs(box(src, 1) - box(src, 3))
    face = mask >= 200
    for p in (50, 60, 70, 75, 80, 85, 90, 95, 99):
        print('  P%-3d = %.3f 级' % (p, np.percentile(hm[face], p)))
    print('  均值 %.3f  最大 %.1f' % (hm[face].mean(), hm[face].max()))

    # 脸颊区（结构最平坦的皮肤）与全脸对比
    ys, xs = np.where(face)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    print('  脸 bbox x[%d,%d] y[%d,%d]' % (x0, x1, y0, y1))
    ch = face.copy()
    ch[: int(H * 0.35)] = False          # 去掉头发/额头边缘
    ch[int(H * 0.80):] = False
    ch[:, : int(W * 0.30)] = False
    ch[:, int(W * 0.70):] = False
    if ch.sum() > 1000:
        print('  中央脸颊区 P50=%.3f P90=%.3f P99=%.3f'
              % (np.percentile(hm[ch], 50), np.percentile(hm[ch], 90),
                 np.percentile(hm[ch], 99)))


if __name__ == '__main__':
    main()
