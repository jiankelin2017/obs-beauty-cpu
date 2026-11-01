# -*- coding: utf-8 -*-
"""3.0.1 回归：细节保留率（多尺度）+ 背景保护（掩码外零改动）。

细节保留率 = mean|out - box_r(out)| / mean|in - box_r(in)|，r=1/2/3/5。
3.0.0 基线（用户同参数、静态帧）：各尺度 95~105%。
背景保护：fuai 软化掩码为 0 的像素，输出必须与输入逐比特一致
（2.2.1 基线：539848 px 零改动）。
"""
import os
import struct
import sys

from PIL import Image, ImageChops, ImageFilter, ImageStat

HERE = os.path.abspath(".")
W, H = 1074, 604


def load_png(p):
    return Image.open(p).convert("RGB")


def load_raw(p):
    with open(p, "rb") as f:
        return Image.frombytes("RGBA", (W, H), f.read()).convert("RGB")


def detail_energy(img, r):
    sm = img.filter(ImageFilter.BoxBlur(r - 1)) if r > 1 else img.filter(ImageFilter.BoxBlur(1))
    d = ImageChops.difference(img, sm)
    return sum(ImageStat.Stat(d).mean) / 3.0


def detail_retention(inp, outp):
    print("  尺度   输入细节   输出细节   保留率")
    for r in (1, 2, 3, 5):
        ei = detail_energy(inp, r)
        eo = detail_energy(outp, r)
        print("  r=%-3d  %8.4f  %8.4f  %6.1f%%" % (r, ei, eo, 100.0 * eo / ei))


def background(inpath, outpath, maskpath):
    with open(maskpath, "rb") as f:
        d = f.read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = d[8 + n:8 + 2 * n]
    with open(inpath, "rb") as f:
        a = f.read()
    with open(outpath, "rb") as f:
        b = f.read()
    assert len(a) == len(b) == W * H * 4, (len(a), len(b))
    # 引擎对掩码做双线性采样（buildMaskMap）。保守判定：某像素的 4 个
    # tap 全为 0 时双线性结果必为 0，引擎不可能碰它 —— 这种像素若被改了
    # 就是真违规；tap 有非零的跳过（边界四舍五入差异，不较真）。
    viol = changed = 0
    for y in range(H):
        my0 = y * mh // H
        my1 = min(my0 + 1, mh - 1)
        for x in range(W):
            i = y * W + x
            if a[i * 4:i * 4 + 4] != b[i * 4:i * 4 + 4]:
                changed += 1
                mx0 = x * mw // W
                mx1 = min(mx0 + 1, mw - 1)
                if (soft[my0 * mw + mx0] or soft[my0 * mw + mx1] or
                        soft[my1 * mw + mx0] or soft[my1 * mw + mx1]):
                    continue
                viol += 1
    inside = sum(1 for v in soft if v > 0)
    print("  掩码 %dx%d：掩码内(soft>0) %d px，总变化 %d px，掩码外(4 tap 全 0)变化 %d px（必须为 0）"
          % (mw, mh, inside, changed, viol))


if __name__ == "__main__":
    print("=== 细节保留率（静态帧 + 用户同参数 磨50/白50/红30/锐50）===")
    detail_retention(load_png(os.path.join(HERE, "out", "frame_0.png")),
                     load_raw(os.path.join(HERE, "flick", "static_out", "seq_011.raw")))
    print("=== 背景保护（同一次静态运行，掩码外必须零改动）===")
    background(os.path.join(HERE, "flick", "static", "seq_011.raw"),
               os.path.join(HERE, "flick", "static_out", "seq_011.raw"),
               os.path.join(HERE, "mask_dump_011.raw"))
