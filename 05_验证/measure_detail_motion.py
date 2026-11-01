# -*- coding: utf-8 -*-
"""细节信号自身的帧间变化量分布（给逐像素自适应 beta 定阈值）。

眼镜「多重延迟的重影」= 多层时间常数不同的时间平滑叠加。
细节层的运动判据目前吃**掩码轮廓**的变化量，而眼镜这种高对比细纹的移动
在低分辨率掩码上根本看不出来，所以慢动时 β 还压在静止档。

本脚本测 |Δh_fine| / |Δh_mid| 的分布：
  静止+噪声  —— 要压住的
  缓慢运动   —— 要立刻放开的
"""
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.abspath("."))
from shape_test import read_dump, soften

W, H = 1074, 604


def frames_of(d, n=12):
    out = []
    for k in range(n):
        p = os.path.join(d, "seq_%03d.raw" % k)
        if not os.path.exists(p):
            break
        out.append(np.frombuffer(open(p, "rb").read(),
                                 dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(np.float32))
    return out


def box(a, r):
    return np.asarray(Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.BoxBlur(r)),
                      dtype=np.float32)


def report(name, frames, mask=None):
    if len(frames) < 3:
        print("%-18s 帧数不足 %d" % (name, len(frames)))
        return
    df, dm = [], []
    for i in range(1, len(frames)):
        b1a, b1b = box(frames[i - 1], 1), box(frames[i], 1)
        b3a, b3b = box(frames[i - 1], 3), box(frames[i], 3)
        f_a = frames[i - 1] - b1a
        f_b = frames[i] - b1b
        m_a = b1a - b3a
        m_b = b1b - b3b
        df.append(np.abs(f_b - f_a))
        dm.append(np.abs(m_b - m_a))
    df = np.concatenate([x.reshape(-1) for x in df])
    dm = np.concatenate([x.reshape(-1) for x in dm])
    for tag, arr in (("fine", df), ("mid", dm)):
        print("  %-18s %s  中位 %5.2f  p75 %5.2f  p90 %5.2f  p99 %6.2f  max %6.1f"
              % (name, tag, np.median(arr), np.percentile(arr, 75),
                 np.percentile(arr, 90), np.percentile(arr, 99), arr.max()))


def main():
    for name, d in (("±2 静止噪声", "flick/noisy2"),
                    ("±5 静止噪声", "flick/noisy5"),
                    ("±12 静止噪声", "flick/noisy12"),
                    ("slow 缓动", "flick/sweep_slow"),
                    ("mid 中速", "flick/sweep_mid"),
                    ("fast 快速", "flick/sweep_fast")):
        report(name, frames_of(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
