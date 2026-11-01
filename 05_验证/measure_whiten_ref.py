# -*- coding: utf-8 -*-
"""用「关闭效果」与「美白 50」两张同机位截图，反推第三方美白的真实提亮曲线。

用法：
    python measure_whiten_ref.py <关闭效果.png> <美白50.png>

两张图必须同一机位、同一光线、同一窗口尺寸、同一姿势。
脚本会自动切掉右侧参数面板和底部黑边，只留预览区。

输出：
    1) 肤色区 Y / Cr 的均值差（这就是「美白 50 提亮多少级」）
    2) 按输入亮度分箱的传递曲线（输入 Y -> 输出 Y），可直接用来拟合 kMax
    3) 高频 / 中频 / 低频 std 变化（确认美白是否顺手改了纹理）
"""
import sys

import numpy as np
from PIL import Image, ImageFilter

FACE_BOX = None      # 需要时手动指定 (x0, y0, x1, y1)，None = 自动


def preview_area(a):
    """右侧参数面板是平坦 UI，列标准差很低；从右往左找到第一段平坦区。"""
    h, w, _ = a.shape
    colstd = a.std(axis=(0, 2))
    # 从最右开始，向左找连续低方差列
    x = w - 1
    while x > 0 and colstd[x] > 25:
        x -= 1
    right = x + 1
    # 底部黑边
    rowmean = a.mean(axis=(1, 2))
    y = h - 1
    while y > 0 and rowmean[y] < 40:
        y -= 1
    bottom = y + 1
    return 0, 0, max(right, int(w * 0.5)), max(bottom, int(h * 0.8))


def skin_mask(a):
    Y = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    Cr = (a[:, :, 0] - Y) * 0.713 + 128
    Cb = (a[:, :, 2] - Y) * 0.564 + 128
    return (Cr > 133) & (Cr < 178) & (Cb > 75) & (Cb < 130) & (Y > 40) & (Y < 250)


def load(p, crop):
    im = Image.open(p).convert("RGB")
    if crop:
        im = im.crop(crop)
    return np.asarray(im).astype(np.float32)


def luma(a):
    return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]


def chroma_r(a):
    return (a[:, :, 0] - luma(a)) * 0.713 + 128


def bands(a, m):
    im = Image.fromarray(a.astype(np.uint8))
    b1 = np.asarray(im.filter(ImageFilter.BoxBlur(1))).astype(np.float32)
    b3 = np.asarray(im.filter(ImageFilter.BoxBlur(3))).astype(np.float32)
    b7 = np.asarray(im.filter(ImageFilter.BoxBlur(7))).astype(np.float32)
    return (float((a - b1)[m].std()), float((b1 - b3)[m].std()),
            float((b3 - b7)[m].std()))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    raw0 = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(np.float32)
    crop = preview_area(raw0)
    if FACE_BOX:
        crop = FACE_BOX
    a = load(sys.argv[1], crop)
    b = load(sys.argv[2], crop)
    if a.shape != b.shape:
        print("两张图尺寸不一致：%s vs %s（请用同一窗口尺寸重截）"
              % (a.shape[:2], b.shape[:2]))
        return 2
    print("预览区 %dx%d" % (a.shape[1], a.shape[0]))

    # 肤色掩码取两张的并集，避免「提亮后掉出肤色阈值」造成的选择偏差
    m = skin_mask(a) | skin_mask(b)
    if m.sum() < 5000:
        print("肤色像素太少（%d），请确认预览区里脸足够大" % m.sum())
        return 3

    Y0, Y1 = luma(a)[m], luma(b)[m]
    C0, C1 = chroma_r(a)[m], chroma_r(b)[m]
    print()
    print("肤色像素 %d" % m.sum())
    print("  Y   %.2f -> %.2f   (%+.2f 级)" % (Y0.mean(), Y1.mean(), Y1.mean() - Y0.mean()))
    print("  Cr  %.2f -> %.2f   (%+.2f)" % (C0.mean(), C1.mean(), C1.mean() - C0.mean()))
    h0, mi0, lo0 = bands(a, m)
    h1, mi1, lo1 = bands(b, m)
    print("  高频 %.3f -> %.3f (%+.1f%%)   中频 %.3f -> %.3f (%+.1f%%)   低频 %.3f -> %.3f (%+.1f%%)"
          % (h0, h1, 100 * (h1 / h0 - 1), mi0, mi1, 100 * (mi1 / mi0 - 1),
             lo0, lo1, 100 * (lo1 / lo0 - 1)))

    print()
    print("传递曲线（按输入亮度分箱）：")
    print("  %-14s %6s %8s %8s" % ("输入 Y 区间", "像素", "输出 Y", "提亮"))
    y0f, y1f = luma(a), luma(b)
    for lo in range(60, 220, 20):
        sel = m & (y0f >= lo) & (y0f < lo + 20)
        if sel.sum() < 200:
            continue
        d = y1f[sel].mean() - y0f[sel].mean()
        print("  %3d..%-3d      %6d %8.2f %+8.2f"
              % (lo, lo + 19, sel.sum(), y1f[sel].mean(), d))
    print()
    print("提示：把上表按「输入 Y」读，就是对方美白 50 档的色调曲线。")
    print("      我们的实现是 delta = k * v * (255-v) / 254，k = 面板/100 * kMax。")
    print("      用其中一行即可反解 kMax：k = delta * 254 / (v * (255-v)) * (100/面板)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
