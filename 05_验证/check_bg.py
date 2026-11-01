# -*- coding: utf-8 -*-
"""背景保护校验：掩码外（双线性上采样后恰好为 0）的像素必须逐字节不变。

关键：LegacyEngine::buildMaskMap 的映射是**角点对齐**的
    q = x*(mw-1)*65536/(w-1); i0=q>>16; i1=min(i0+1,mw-1)
    wx = ((q & 0xFFFF)*256)>>16
用 x*mw//w 会把边界算错半个像素，误报几百个「越界改动」。
"""
import os
import struct
import sys

import numpy as np

W, H = 1074, 604
CASES = ("base", "s50", "s100", "c100")


def axis_map(n_out, n_in):
    """返回 (i0, i1, f) 三个长度 n_out 的数组，逐行复刻 buildMaskMap。"""
    x = np.arange(n_out, dtype=np.int64)
    q = x * (n_in - 1) * 65536 // (n_out - 1)
    i0 = q >> 16
    f = ((q & 0xFFFF) * 256) // 65536
    over = i0 >= n_in - 1
    i0 = np.where(over, n_in - 1, i0)
    f = np.where(over, 0, f)
    i1 = np.where(i0 + 1 < n_in, i0 + 1, i0)
    return i0, i1, f


def load_mask(path):
    """复刻 buildMaskMap + applyRegionEffects 的 mv 计算。

    必须**先横后竖、最后只 >>16 一次**（引擎就是这么写的）。先竖后横各 >>8
    会在每趟各截断一次，边界附近偶尔把 1 截成 0，制造出几百个假「越界改动」。
    """
    d = open(path, "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw).astype(np.int64)
    y0, y1, fy = axis_map(H, mh)
    x0, x1, fx = axis_map(W, mw)
    a0 = soft[np.ix_(y0, x0)]
    a1 = soft[np.ix_(y0, x1)]
    b0 = soft[np.ix_(y1, x0)]
    b1 = soft[np.ix_(y1, x1)]
    top = a0 * (256 - fx)[None, :] + a1 * fx[None, :]
    bot = b0 * (256 - fx)[None, :] + b1 * fx[None, :]
    return (top * (256 - fy)[:, None] + bot * fy[:, None]) >> 16


def main():
    mask = load_mask("mask_dump_048.raw")
    outside = mask == 0
    print("掩码外像素 %d / %d（%.1f%%）"
          % (outside.sum(), mask.size, outside.mean() * 100))
    src = np.frombuffer(open("flick/static/seq_000.raw", "rb").read(),
                        dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.int32)
    # 对照组必须是 base（磨皮50），不能是原图：SDK 自己的磨皮**不受我们的掩码
    # 控制**，它在背景上本来就会改 1 级左右（base 对原图 142 px @1 级）。
    # base 与 s50/s100/c100 之间只差 applySharpen（含 clarity 折算的中频增益），
    # 而那一层是 100% 由皮肤掩码门控的 —— 掩码外必须逐字节相同。
    base = np.frombuffer(open("flick/p302_base_out/seq_000.raw", "rb").read(),
                         dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.int32)
    d0 = np.abs(base - src).max(axis=2)
    print("  参考：base 对原图 掩码外 %d px 最大 %d 级（SDK 磨皮自带，不归掩码管）"
          % (int((d0[outside] > 0).sum()), int(d0[outside].max()) if outside.any() else 0))
    ok = True
    for tag in CASES:
        p = os.path.join("flick", "p302_%s_out" % tag, "seq_000.raw")
        out = np.frombuffer(open(p, "rb").read(),
                            dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.int32)
        d = np.abs(out - base).max(axis=2)
        bad = int((d[outside] > 0).sum())
        mx = int(d[outside].max()) if outside.any() else 0
        print("  %-5s 相对 base 掩码外改动 %5d px  最大 %d 级  %s"
              % (tag, bad, mx, "OK" if bad == 0 else "!! 越界"))
        ok = ok and bad == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
