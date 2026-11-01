# -*- coding: utf-8 -*-
"""freq_vs_bilateral.py —— 高低频磨皮 vs 旧的「双边+线性混合」

要回答的问题：为什么旧方式"脸糊"，高低频不糊？

量化方式：
  1. 把图分成**低频**（大半径高斯）和**高频**（原图 - 低频）
  2. 低频 = 脸型、光影、明暗层次 → **它的对比度被削弱就是"糊"**
  3. 高频 = 毛孔、痘印、细纹 → 它该被削弱，那才是"磨皮"

理想结果：低频保留 ≈ 100%，高频下降 30~60%。
旧方式如果低频掉得多，就是"糊"而不是"磨"。
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
        _dll.BeautyCoreSetFreq.argtypes = [ctypes.c_int, ctypes.c_float,
                                           ctypes.c_float, ctypes.c_float]
        _dll.BeautyCoreSetFreq.restype = None
        _dll.BeautyCoreSetEdgeK.argtypes = [ctypes.c_int]
        _dll.BeautyCoreSetEdgeK.restype = None
        _dll.BeautyCoreSetProtectK.argtypes = [ctypes.c_int]
        _dll.BeautyCoreSetProtectK.restype = None
    return _dll


def run(mode, sigma, mag_lo, mag_hi, blur, edge_k=10, protect_k=80):
    dll = setup()
    dll.BeautyCoreSetFreq(mode, sigma, mag_lo, mag_hi)
    dll.BeautyCoreSetEdgeK(edge_k)
    dll.BeautyCoreSetProtectK(protect_k)
    raw = os.path.join(RES, '640x394.raw').encode()
    out = os.path.join(OUT, '_fv.raw').encode()
    msg = ctypes.create_string_buffer(512)
    for _ in range(5):
        dll.BeautyCoreRun(raw, out, W, H, float(blur), 0, 0.0, 0.0, 1, msg, 512)
    rc = dll.BeautyCoreRun(raw, out, W, H, float(blur), 0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError(msg.value.decode('utf-8', 'replace'))
    with open(out, 'rb') as f:
        return np.frombuffer(f.read(), np.uint8).reshape((H, W, 4)).copy()


def gauss(img, sigma):
    """频域切分用的大半径高斯（numpy 实现，只用于测量）"""
    r = int(sigma * 3 + 0.5)
    k = np.exp(-(np.arange(-r, r + 1, dtype=np.float32) ** 2) / (2 * sigma * sigma))
    k /= k.sum()
    a = img.astype(np.float32)
    pad = np.pad(a, ((0, 0), (r, r), (0, 0)), mode='edge')
    tmp = np.zeros_like(a)
    for i, kv in enumerate(k):
        tmp += pad[:, i:i + W, :] * kv
    pad2 = np.pad(tmp, ((r, r), (0, 0), (0, 0)), mode='edge')
    out = np.zeros_like(tmp)
    for i, kv in enumerate(k):
        out += pad2[i:i + H, :, :] * kv
    return out


def split_lh(img, sigma=12.0):
    l = gauss(img[:, :, :3], sigma)
    h = img[:, :, :3].astype(np.float32) - l
    return l, h


def local_contrast(low):
    """低频层的局部对比度：用 Laplacian 的绝对值均值"""
    g = low.mean(axis=2)
    lap = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
                 - g[1:-1, :-2] - g[1:-1, 2:])
    return lap


def main():
    src = np.fromfile(os.path.join(RES, '640x394.raw'), np.uint8).reshape((H, W, 4))
    l_src, h_src = split_lh(src)
    c_src = local_contrast(l_src)
    e_src = float(np.abs(h_src).mean())

    # 脸区域（face_src 的 YuNet 框）。注意两个尺寸：
    # 局部对比度是 (H-2,W-2)，高频图是 (H,W)，掩码要分别做。
    x0, x1, y0, y1 = 277, 384, 89, 223
    reg_low = np.zeros((H - 2, W - 2), bool)
    reg_low[y0:y1 - 2, x0:x1 - 2] = True
    reg_full = np.zeros((H, W), bool)
    reg_full[y0:y1, x0:x1] = True
    reg = reg_full

    # 高频按**幅度**分三层：小幅度=瑕疵（该磨），大幅度=边缘（该留）
    hmag = np.abs(h_src).max(axis=2)
    bands = {'小幅度(<6)': (hmag >= 0) & (hmag < 6),
             '中幅度(6~30)': (hmag >= 6) & (hmag < 30),
             '大幅度(>30)': hmag >= 30}
    print('脸区域内的频段统计（sigma=12 定义低频）')
    print()
    print('%-22s %9s %11s %10s %10s %10s'
          % ('配置', '总磨皮量', '低频保留%', '小幅度%', '中幅度%', '大幅度%'))

    rows = []
    for tag, mode, sigma, lo, hi in [
        ('旧：双边混合 t=50', 0, 3.0, 6.0, 30.0),
        ('旧：双边混合 t=100', 0, 3.0, 6.0, 30.0),
        ('新：高低频 σ=3 t=50', 1, 3.0, 6.0, 30.0),
        ('新：高低频 σ=3 t=100', 1, 3.0, 6.0, 30.0),
        ('新：高低频 σ=6 t=100', 1, 6.0, 6.0, 30.0),
    ]:
        blur = 100.0 if 't=100' in tag else 50.0
        out = run(mode, sigma, lo, hi, blur)
        l_out, h_out = split_lh(out)
        c_out = local_contrast(l_out)
        low_keep = 100.0 * c_out[reg_low].mean() / c_src[reg_low].mean()
        # out[reg_full] 已经是 (N,4)，不能再按三维切
        amt = float(np.abs(out[reg_full][:, :3].astype(np.float32)
                           - src[reg_full][:, :3].astype(np.float32)).mean())
        band_keep = []
        for name, bm in bands.items():
            sel = bm & reg_full
            if sel.sum() == 0:
                band_keep.append(float('nan'))
                continue
            band_keep.append(100.0 * np.abs(h_out[sel]).mean()
                             / np.abs(h_src[sel]).mean())
        rows.append((tag, amt, low_keep, band_keep))
        print('%-22s %9.3f %10.1f%% %9.1f%% %9.1f%% %9.1f%%'
              % (tag, amt, low_keep, band_keep[0], band_keep[1], band_keep[2]))

    tmp = os.path.join(OUT, '_fv.raw')
    if os.path.exists(tmp):
        os.remove(tmp)
    print()
    print('[判据] 理想 = 低频≈100%（脸不塌）+ 小幅度↓（瑕疵磨掉）'
          '+ 大幅度≈100%（五官轮廓保住）')
    print('       旧方式的毛病是「想磨小幅度就一起削大幅度」——线性混合没有分层能力。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
