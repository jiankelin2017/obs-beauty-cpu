# -*- coding: utf-8 -*-
"""把指定 BEAUTY_MASK_SHAPE 下引擎算出的掩码导出并与 fuai 真值叠图。

用法（每个形状必须独立进程 —— 引擎每个进程只读一次环境变量）：
    BEAUTY_MASK_SHAPE=4 python mask_shape_probe.py 4 face_src
产物：C:\\btwork\\mask_check\\shape_<sid>_<shape>.png（三联：真值 / 我方 / 差异）
"""
import ctypes
import os
import sys

import cv2
import numpy as np

HERE = r'D:\插件\OBS美颜\06_离线验证'
os.add_dll_directory(HERE)

DLL = ctypes.WinDLL(os.path.join(HERE, 'beauty_core_test.dll'))
DLL.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
DLL.BeautyCoreMask.restype = ctypes.c_int

W, H = 640, 394
OUTDIR = r'C:\btwork\mask_check'


def read_mask(p):
    b = open(p, 'rb').read()
    mw, mh = np.frombuffer(b[:8], np.int32)
    return np.frombuffer(b[8:], np.uint8).reshape((mh, mw))


def main():
    shape = sys.argv[1] if len(sys.argv) > 1 else '0'
    sid = sys.argv[2] if len(sys.argv) > 2 else 'face_src'
    raw = os.path.join(HERE, 'goldens', 'src', sid + '.raw')
    fu = read_mask(os.path.join(HERE, 'goldens', 'masks', sid + '_fuai.mask'))
    fu = cv2.resize(fu, (W, H), interpolation=cv2.INTER_LINEAR)
    f = fu > 127
    img = np.fromfile(raw, np.uint8).reshape((H, W, 4))[:, :, :3]
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    tmp = os.path.join(HERE, '_probe_%s_%s.mask' % (shape, sid))
    if os.path.exists(tmp):
        os.remove(tmp)
    msg = ctypes.create_string_buffer(512)
    rc = DLL.BeautyCoreMask(raw.encode(), W, H, tmp.encode(), msg, 512)
    print('rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
    if rc != 0:
        return 1
    m = read_mask(tmp)
    c = m > 127
    os.remove(tmp)

    def show(mask):
        b = bgr.copy()
        b[mask] = (0.35 * b[mask] + 0.65 * np.array([0, 0, 255])).astype(np.uint8)
        return b

    vis = bgr.copy()
    vis[f & ~c] = (0, 255, 0)      # 绿 = fuai 有、我们缺
    vis[~f & c] = (255, 0, 255)    # 品红 = 我们多
    cov = 100.0 * c.sum() / (W * H)
    print('shape=%s %s  cov %.2f%%  欠 %.1f%%  溢 %d px'
          % (shape, sid, cov, 100.0 * (f & ~c).sum() / f.sum(), (~f & c).sum()))
    grid = np.hstack([show(f), show(c), vis])
    p = os.path.join(OUTDIR, 'shape_%s_%s.png' % (sid, shape))
    cv2.imwrite(p, grid)
    print('->', p)

    # 逐行宽度：定位截断位置
    print('   y   掩码宽  羽化带宽')
    for y in range(150, H, 16):
        xs = np.where(c[y])[0]
        band = np.where((m[y] > 8) & (m[y] <= 200))[0]
        if xs.size:
            print('%5d  %5d  %5d' % (y, xs.size, band.size))
        else:
            print('%5d      0  %5d' % (y, band.size))
    return 0


if __name__ == '__main__':
    sys.exit(main())
