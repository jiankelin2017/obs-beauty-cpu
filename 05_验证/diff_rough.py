# -*- coding: utf-8 -*-
"""帧间差异的"粗糙度"分析（3.0.1 根因闸门）。

动机：meanAbs 只告诉你"输出有多抖"，不告诉你"抖成什么样"。
  - 掩码抖动传播 → 大尺度平滑振荡（强度斑块缓慢呼吸）→ 高频成分少
  - 细节回填带回的噪点 → 逐像素白噪闪烁 → 几乎全是高频
对每个相邻帧对计算 diff = |f[k] - f[k-1]|（RGB），再把它过一个 3x3 box
平滑拿掉低频，剩下的 rough 就是"细粒度闪烁"的直接观测量。

白噪过 3x3 平均只掉 ~6% 幅度（σ→0.94σ），平滑斑块则被大幅削掉，
所以 rough/meanAbs 比值：接近 1 = 细粒度噪闪主导；接近 0 = 平滑振荡主导。

用法：python diff_rough.py <目录A> <目录B> ...
每个目录里需有 seq_000.raw 起的连续输出帧（1074x604 RGBA）。
"""
import os
import sys

from PIL import Image, ImageChops, ImageFilter, ImageStat

W, H = 1074, 604


def load(d, k):
    p = os.path.join(d, "seq_%03d.raw" % k)
    with open(p, "rb") as f:
        return Image.frombytes("RGBA", (W, H), f.read())


def analyze(d):
    ms, rs = [], []
    k = 1
    while os.path.exists(os.path.join(d, "seq_%03d.raw" % k)):
        a = load(d, k - 1).convert("RGB")
        b = load(d, k).convert("RGB")
        diff = ImageChops.difference(a, b)
        rough = ImageChops.difference(diff, diff.filter(ImageFilter.BoxBlur(1)))
        ms.append(sum(ImageStat.Stat(diff).mean) / 3.0)
        rs.append(sum(ImageStat.Stat(rough).mean) / 3.0)
        k += 1
    n = len(ms)
    if not n:
        print("  %-24s 无输出帧" % d)
        return
    m = sum(ms) / n
    r = sum(rs) / n
    print("  %-24s meanAbs=%.3f  rough=%.3f  rough/mean=%.2f  (n=%d)"
          % (os.path.basename(d.rstrip("/\\")), m, r, r / m if m else 0.0, n))


if __name__ == "__main__":
    for d in sys.argv[1:]:
        analyze(d)
