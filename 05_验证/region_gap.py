# -*- coding: utf-8 -*-
"""
区域画质差距定量（对应「痘印 / 鼻翼阴影 / 唇纹全留着」这条反馈）
================================================================

背景
----
用户对比第三方 SDK 与自研引擎的实机画面，指出三处肉眼差距：
额头痘印、鼻翼阴影、嘴唇纹理。源码里有三道闸门可能挡住：

    freqMagHi = 30   高频幅度 > 30 灰阶完全不动（保眉毛/鼻梁边/唇线）
    regSpotThrHi = 30  祛斑痘偏离 > 30 不算斑点
    protectK = 80      眼/嘴区域权重压掉 80%

本脚本不猜，直接量：在四个区域上测三个频带的保留率，
把 SDK 与 core（不同 freqMagHi）放在同一张表上对比。

频带口径
--------
    细纹理 |Y - box3|        —— 痘印、毛孔、唇纹
    中频   |box3 - box7|     —— 皮肤起伏
    阴影   |box7 - box21|    —— 鼻翼阴影这类大尺度明暗

区域
----
归一化到人脸框（cv2 YuNet 实测 640x394：x=276.4 y=84.8 w=111.3 h=140.8）：
    额头 / 鼻翼 / 唇 / 脸颊（参照）

用法
----
    BEAUTY_FREQ_MAG=6,30  python region_gap.py sdk
    BEAUTY_FREQ_MAG=6,60  python region_gap.py core

freqMagHi 在 core 里是进程启动时读一次的环境变量，所以每个档位要单独起进程。
"""

import ctypes
import os
import re
import sys

import numpy as np

import low_path_test as L

W, H = 640, 394
P_BLUR, P_CLARITY, P_WHITEN, P_RED, P_SHARPEN, P_GLOBAL_SHARP, \
    P_THREED, P_EYEBRIGHT, P_POUCH, P_NASOLABIAL, P_DELSPOT = range(11)
P_COUNT = 11

SDK_DLL = os.path.join(L.HERE, 'ref_golden.dll')
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')
RAW = os.path.join(L.RES, '640x394.raw')

# 人脸框与关键点（cv2 YuNet 在 640x394.raw 上的实测值）
BX, BY, BW_, BH_ = 276.4, 84.8, 111.3, 140.8

# 区域：归一化到人脸框 (nx0, ny0, nx1, ny1)
REGIONS = [
    ('额头', 0.40, 0.13, 0.78, 0.30),
    ('鼻翼', 0.50, 0.55, 0.72, 0.68),
    ('唇',   0.36, 0.72, 0.72, 0.82),
    ('脸颊', 0.15, 0.45, 0.35, 0.60),
    # 眼睛是「绝不能被磨」的对照区：降 protectK 能追上 SDK 的唇，但代价可能
    # 是睫毛/瞳孔边缘被糊。所以每次动 protectK 必须同时看这一列。
    # 取两块：横跨双眼（含眼白与虹膜边界）与眉眼之间。
    ('眼区', 0.30, 0.34, 0.88, 0.47),
]


def y_luma(a):
    a = a[:, :, :3].astype(np.float32)
    return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]


def box(a, r):
    h, w = a.shape
    k = 2 * r + 1
    p = np.pad(a, ((0, 0), (r, r)), mode='edge')
    c = np.cumsum(p, axis=1, dtype=np.float64)
    c = np.concatenate([np.zeros((h, 1)), c], axis=1)
    h1 = (c[:, k:] - c[:, :-k]) / k
    p2 = np.pad(h1, ((r, r), (0, 0)), mode='edge')
    c2 = np.cumsum(p2, axis=0, dtype=np.float64)
    c2 = np.concatenate([np.zeros((1, w)), c2], axis=0)
    return (c2[k:, :] - c2[:-k, :]) / k


def bands(a):
    """返回 (细纹理, 中频, 阴影) 三张图"""
    y = y_luma(a).astype(np.float64)
    b3 = box(y, 1)
    b7 = box(y, 3)
    b21 = box(y, 10)
    return np.abs(y - b3), np.abs(b3 - b7), np.abs(b7 - b21)


def region_masks():
    out = []
    for name, nx0, ny0, nx1, ny1 in REGIONS:
        m = np.zeros((H, W), bool)
        x0 = int(BX + nx0 * BW_); x1 = int(BX + nx1 * BW_)
        y0 = int(BY + ny0 * BH_); y1 = int(BY + ny1 * BH_)
        m[max(0, y0):min(H, y1), max(0, x0):min(W, x1)] = True
        out.append((name, m))
    return out


# ---------------------------- SDK ----------------------------

def run_sdk(blur):
    d = ctypes.WinDLL(SDK_DLL)
    d.RefGoldenRun.argtypes = [ctypes.c_char_p] * 3 + [
        ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double),
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    out = os.path.join(L.OUT, '_gap_sdk.raw')
    arr = (ctypes.c_double * P_COUNT)(*[0.0] * P_COUNT)
    arr[P_BLUR] = blur
    msg = ctypes.create_string_buffer(512)
    rc = d.RefGoldenRun(ENGINE_DIR.encode(), RAW.encode(), out.encode(),
                         W, H, arr, P_COUNT, 1, 1, 0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('sdk rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
    return L.load(out, W, H)


# ---------------------------- core ----------------------------

def run_core(blur):
    dll = ctypes.WinDLL(L.DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    for n in ('BeautyCoreSetTone', 'BeautyCoreSetDetail'):
        getattr(dll, n).argtypes = [ctypes.c_double, ctypes.c_double]
    dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    dll.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]
    # 只开磨皮，其余全 0 —— 与 SDK 同一档位才有可比性
    dll.BeautyCoreSetTone(0.0, 0.0)
    dll.BeautyCoreSetDetail(0.0, 0.0)
    dll.BeautyCoreSetClarityPanel(0.0)
    for i in range(5):
        dll.BeautyCoreSetRegion(i, 0.0)
    out = os.path.join(L.OUT, '_gap_core.raw')
    msg = ctypes.create_string_buffer(512)
    for _ in range(3):
        dll.BeautyCoreRun(RAW.encode(), out.encode(), W, H, blur, 0,
                          0.0, 0.0, 1, msg, 512)
    m = re.search(r'ms=([0-9.]+)', msg.value.decode('ascii', 'replace'))
    return L.load(out, W, H), (float(m.group(1)) if m else -1.0)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'core'
    blur = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
    maghi = os.environ.get('BEAUTY_FREQ_MAG', '6,30').split(',')[1]

    src = L.load(RAW, W, H)
    if mode == 'sdk':
        cur = run_sdk(blur)
        label = 'SDK'
        extra = ''
    else:
        cur, ms = run_core(blur)
        label = 'core'
        extra = ' magHi=%s (%.2f ms)' % (maghi, ms)

    sb = bands(src)
    cb = bands(cur)
    rms = region_masks()
    print('%s 磨皮%.0f%s' % (label, blur, extra))
    print('%-6s %10s %10s %10s' % ('区域', '细纹理%', '中频%', '阴影%'))
    for name, m in rms:
        vals = []
        for i in range(3):
            a = float(sb[i][m].mean())
            b = float(cb[i][m].mean())
            vals.append(100.0 * b / a if a > 1e-9 else float('nan'))
        print('%-6s %9.1f %9.1f %9.1f' % (name, vals[0], vals[1], vals[2]))


if __name__ == '__main__':
    main()
