# -*- coding: utf-8 -*-
"""量化「重影」：强边缘像素的细节残影幅度。

定义：对 h_fine 做时序 EMA，残影 = |平滑后的 h − 当前真实的 h|。
重影最显眼的是**强边缘像素**（眼镜框这类），所以只在 |Δh| 最大的 1% 像素上
统计均值。

对比两条 β 规则：
  全局静止档   β = 0.20（细）/ 0.08（中）—— 3.0.6 及以前在慢动时的实际值
  逐像素自适应 β = still + (1-still)·clamp((|Δh|-Lo)/(Hi-Lo)) —— 3.0.7
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.abspath("."))

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


def bands(frames):
    fine, mid = [], []
    for f in frames:
        b1 = box(f, 1)
        b3 = box(f, 3)
        fine.append(f - b1)
        mid.append(b1 - b3)
    return fine, mid


def ghost(series, still, lo, hi, adaptive):
    """返回强边缘（|Δh| 前 1%）上的平均残影幅度。"""
    prev = series[0]
    vals = []
    for i in range(1, len(series)):
        cur = series[i]
        dd = np.abs(cur - prev)
        if adaptive:
            t = np.clip((dd - lo) / float(hi - lo), 0.0, 1.0)
            b = still + (1.0 - still) * t
        else:
            b = np.full(cur.shape, still, dtype=np.float32)
        out = b * cur + (1.0 - b) * prev
        # 强边缘像素：本帧 |Δh| 的前 1%
        thresh = np.percentile(dd, 99)
        sel = dd >= thresh
        vals.append(float(np.abs(out - cur)[sel].mean()))
        prev = out
    return float(np.mean(vals))


def main():
    for name, d in (("slow 缓动", "flick/sweep_slow"),
                    ("mid 中速", "flick/sweep_mid"),
                    ("fast 快速", "flick/sweep_fast"),
                    ("±5 静止噪声", "flick/noisy5")):
        fr = frames_of(d)
        if len(fr) < 3:
            print("%-14s 帧数不足" % name)
            continue
        fine, mid = bands(fr)
        # 3.0.7 最终标定值：细频 10/12，中频 6/10（中频是 1/64 定点）
        gf0 = ghost(fine, 0.20, 10, 12, False)
        gf1 = ghost(fine, 0.20, 10, 12, True)
        gm0 = ghost(mid, 0.08, 6, 10, False)
        gm1 = ghost(mid, 0.08, 6, 10, True)
        print("%-14s 细频残影 %6.2f -> %5.2f 级   中频残影 %6.2f -> %5.2f 级"
              % (name, gf0, gf1, gm0, gm1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
