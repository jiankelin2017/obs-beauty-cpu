# -*- coding: utf-8 -*-
"""按掩码区域拆分帧间闪动：内部(soft>=250) / 过渡带(1..249) / 掩码外(0)。

用来判断回填引入的闪动是否集中在皮肤边界 —— 用户报「脸颊交界处轻微屏闪」。
"""
import os
import struct
import sys

import numpy as np

W, H = 1074, 604


def load_mask(k):
    d = open("mask_dump_%03d.raw" % k, "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)
    # 与 buildMaskMap 一致：角对齐 + 16.16 定点
    def idx(cnt, mc):
        q = (np.arange(cnt, dtype=np.int64) * (mc - 1) * 65536) // (cnt - 1)
        i0 = np.minimum(q >> 16, mc - 1)
        i1 = np.minimum(i0 + 1, mc - 1)
        return i0, i1
    x0, x1 = idx(W, mw)
    y0, y1 = idx(H, mh)
    return soft[np.ix_(y0, x0)], soft  # 最近邻近似即可（只做区域划分）


def load_raw(p):
    with open(p, "rb") as f:
        b = f.read()
    return np.frombuffer(b, dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.int16)


def analyze(d, label):
    prev = load_raw(os.path.join(d, "seq_000.raw"))
    acc = {z: [] for z in ("内部", "过渡带", "掩码外")}
    for k in range(1, 12):
        cur = load_raw(os.path.join(d, "seq_%03d.raw" % k))
        diff = np.abs(cur - prev).max(axis=2)
        soft = load_mask(k)[0]
        zones = {"内部": soft >= 250, "过渡带": (soft > 0) & (soft < 250), "掩码外": soft == 0}
        for z, m in zones.items():
            if m.sum():
                acc[z].append(diff[m].mean())
        prev = cur
    print("%-14s" % label, end="")
    for z in ("内部", "过渡带", "掩码外"):
        v = np.array(acc[z])
        print("  %s %5.3f(峰%5.2f)" % (z, v.mean(), v.max()), end="")
    print()


if __name__ == "__main__":
    print("帧间平均 |diff|（逐像素取三通道最大）")
    for tag, d in (("磨皮50", "flick/noisy2_s0_out"),
                   ("磨50+锐50", "flick/noisy2_s50_out")):
        analyze(d, tag)
    # 掩码自身的帧间摆动
    print()
    a = load_mask(0)[1].astype(np.int16)
    mx = 0
    for k in range(1, 12):
        b = load_mask(k)[1].astype(np.int16)
        tr = (a > 0) & (a < 250)
        if tr.sum():
            mx = max(mx, int(np.abs(b - a)[tr].max()))
        a = b
    print("过渡带掩码帧间最大摆动: %d 级" % mx)
