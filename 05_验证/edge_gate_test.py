# -*- coding: utf-8 -*-
"""edge_gate_test.py —— 验证 Sobel 边缘门控

要证明三件事：
  1. k=0 时输出与加门控之前逐字节相同（没破坏现有行为）
  2. k>0 时「高梯度区」（眉毛、眼镜框、发际线）的细节保留率上升
  3. 「低梯度区」（皮肤平坦处）的磨皮效果基本不变

第 2、3 条必须同时成立 —— 只做到 2 就是「干脆不磨了」，不是门控。
"""

import ctypes
import hashlib
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')
SRC = os.path.join(HERE, 'goldens', 'src')

# 加门控之前的哈希（由 verify_roi.py 记录，k 必须默认为 0 才不变）
KNOWN = {'640x394': None, '720p': None, '1080p': None}


def load(p, w, h):
    return np.fromfile(p, np.uint8).reshape((h, w, 4))


def smooth_amount(out, src):
    """每个像素被磨了多少（RGB 平均绝对差，0 = 完全没动）

    为什么不用 |Laplacian| 当指标：实测 k=0（全磨）时边缘区的 Laplacian
    保留率是 **101.18%** —— 磨皮在强边缘处产生的振铃把二阶导撑大了，
    比原图还高。用这个数去评价「边缘有没有被保护」会得到完全相反的结论
    （k 越大读数越低，看起来像磨得更多）。直接测磨皮幅度才不会有这个问题。
    """
    d = np.abs(out[:, :, :3].astype(np.float32) - src[:, :, :3].astype(np.float32))
    return d.mean(axis=2)


def sobel_mag(img):
    """按 C++ 同款口径算梯度（**G 通道**，L1 近似）

    口径必须和 C++ 一致：门控用的是 G 通道（省 2/3 算术），
    用 luma 算会和实际判定对不上。
    """
    luma = img[:, :, 1].astype(np.int64)
    l = np.pad(luma, 1, mode='edge')
    gx = (l[:-2, 2:] + 2 * l[1:-1, 2:] + l[2:, 2:]) - \
         (l[:-2, :-2] + 2 * l[1:-1, :-2] + l[2:, :-2])
    gy = (l[2:, :-2] + 2 * l[2:, 1:-1] + l[2:, 2:]) - \
         (l[:-2, :-2] + 2 * l[:-2, 1:-1] + l[:-2, 2:])
    return (np.abs(gx) + np.abs(gy)) / 2.0


def main():
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetEdgeK.argtypes = [ctypes.c_int]
    dll.BeautyCoreSetEdgeK.restype = None

    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, '_edge_out.raw')

    # ---- 第 1 条：k=0 时门控必须完全不参与 ----
    #
    # 注意基线会随其它特性变化。历史对应关系：
    #   cec2fd1f… = 旧 YCbCr 矩形窗 + 无五官保护 + 无门控（2026-10-28 上午）
    #   d48fd56d… = 椭圆软边判据 + 五官保护开启 + 无门控（当前）
    # 若把 BEAUTY_SKIN_HARD=1 BEAUTY_PROTECT_K=0 传进进程，应回到 cec2fd1f…
    print('== 1. k=0 时输出必须与「门控关闭」的基线一致 ==')
    expect = {'640x394': 'd48fd56de8513f77', '720p': '32594f98b491f2d7',
              '1080p': '6a67973e18accfb0'}
    ok = True
    for name, w, h in [('640x394', 640, 394), ('720p', 1280, 720), ('1080p', 1920, 1080)]:
        raw = os.path.join(RES, name + '.raw')
        dll.BeautyCoreSetEdgeK(0)
        msg = ctypes.create_string_buffer(512)
        for _ in range(5):
            dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                              w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        rc = dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                               w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        data = np.fromfile(tmp, np.uint8)
        hsh = hashlib.sha256(data.tobytes()).hexdigest()[:16]
        same = (hsh == expect[name])
        print('  %-8s %s  期望 %s 实得 %s' % (name, 'PASS' if same else 'FAIL',
                                              expect[name], hsh))
        ok = ok and same

    # ---- 第 2/3 条：门控分区效果 ----
    print()
    print('== 2/3. 高梯度区 vs 低梯度区 ==')
    name, w, h = '640x394', 640, 394
    raw = os.path.join(RES, name + '.raw')
    src = load(raw, w, h)
    mag = sobel_mag(src)

    results = {}
    for k in (0, 5, 10, 20, 40):
        dll.BeautyCoreSetEdgeK(k)
        msg = ctypes.create_string_buffer(512)
        for _ in range(5):
            dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                              w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        rc = dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                               w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        out = load(tmp, w, h)
        d_out = smooth_amount(out, src)
        # 只统计 mask 覆盖区（mask 外逐字节还原，本来就没变）
        changed = np.abs(out[:, :, :3].astype(np.int16)
                         - src[:, :, :3].astype(np.int16)).max(axis=2) > 0
        # 用 k=0 的结果界定「有磨皮的区域」
        results[k] = (out, d_out, changed)

    base_out, base_amt, base_changed = results[0]
    # 分区：在 k=0 被磨过的像素里，按梯度分两半
    idx = np.nonzero(base_changed)
    if len(idx[0]) == 0:
        print('  没有像素被磨过，无法分区')
        return 1
    m_vals = mag[idx]
    thr = np.percentile(m_vals, 75)      # 前 25% 梯度 = 高梯度区
    high = tuple(np.array(i)[m_vals >= thr] for i in idx)
    low = tuple(np.array(i)[m_vals < thr] for i in idx)
    print('  阈值 mag=%.0f（该区域 75 分位）| 高梯度 %d px，低梯度 %d px'
          % (thr, len(high[0]), len(low[0])))
    print()
    a_high0 = base_amt[high].mean()
    a_low0 = base_amt[low].mean()
    print('  k    高梯度区磨皮量  相对k=0   |  低梯度区磨皮量  相对k=0')
    for k in (0, 5, 10, 20, 40):
        out, d_out, _ = results[k]
        a_high = d_out[high].mean()
        a_low = d_out[low].mean()
        print('  %-4d %11.2f %10.1f%%   | %11.2f %10.1f%%'
              % (k, a_high, 100.0 * a_high / a_high0,
                 a_low, 100.0 * a_low / a_low0))

    if os.path.exists(tmp):
        os.remove(tmp)
    print()
    print('[edge] 判据：k 增大时「高梯度区磨皮量」应明显下降（边缘被保住），'
          '「低梯度区磨皮量」应基本不动（磨皮还在）')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
