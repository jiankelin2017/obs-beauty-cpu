# -*- coding: utf-8 -*-
"""消融分析：脸内掩码区域里，各面板配置输出的 1-2px / 3-7px 细节能量。

每个 tag 一目录 flick/nz_<tag>_out，掩码在 flick/mask_<tag>.raw。
输入帧在 flick/nz_in/。全部为同一段测试片的人脸，静帧为主。
"""
import os
import struct

import numpy as np

HERE = r"C:\legacy_e2e"
INDIR = os.path.join(HERE, "flick", "nz_in")
TAGS = ["ab0", "ablur", "ashrp", "aboth", "afull"]
LABEL = {
    "ab0": "全关（0/0/0/0）",
    "ablur": "磨皮50",
    "ashrp": "锐化50",
    "aboth": "磨皮50+锐化50",
    "afull": "磨皮50+美白30+红润30+锐化50",
}


def load_frame(p):
    d = np.frombuffer(open(p, "rb").read(), np.uint8)
    return d.reshape(-1, 4)[:, :3].astype(np.float32)


def mask_of(tag):
    p = os.path.join(HERE, "flick", "mask_%s.raw" % tag)
    d = open(p, "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    soft = np.frombuffer(d[8 + mw * mh:8 + 2 * mw * mh], np.uint8).reshape(mh, mw)
    return soft >= 200


def detail(img, rect, mask_full):
    """在 rect 内、掩码内像素上算高频能量。"""
    y0, y1, x0, x1 = rect
    g = img.reshape(HEIGHT, WIDTH, 3)[y0:y1, x0:x1]
    m = mask_full[y0:y1, x0:x1]
    if m.sum() < 50:
        return None
    y = (g[:, :, 0] * 0.114 + g[:, :, 1] * 0.587 + g[:, :, 2] * 0.299)
    # 简单 3x3 均值高频（避免引入 scipy）
    k = np.ones((3, 3), np.float32) / 9.0
    pad = np.pad(y, 1, mode="edge")
    box = sum(pad[dy:dy + y.shape[0], dx:dx + y.shape[1]]
              for dy in range(3) for dx in range(3)) / 9.0
    hi = (y - box)[m]
    b7 = np.ones((7, 7), np.float32) / 49.0
    pad7 = np.pad(y, 3, mode="edge")
    box7 = np.zeros_like(y)
    for dy in range(7):
        for dx in range(7):
            box7 += pad7[dy:dy + y.shape[0], dx:dx + y.shape[1]]
    box7 /= 49.0
    mid = (box - box7)[m]
    gy, gx = np.gradient(y)
    mag = np.hypot(gx, gy)[m]
    return hi.std(), mid.std(), np.percentile(mag, 95), y[m].mean()


def main():
    global HEIGHT, WIDTH
    # 尺寸信息来自 mask_*.raw 无法拿到全帧，改用输出帧长度推断
    n = os.path.getsize(os.path.join(HERE, "flick", "nz_ab0_out", "seq_000.raw")) // 4
    WIDTH, HEIGHT = 1074, n // 1074
    print("帧尺寸 %dx%d" % (WIDTH, HEIGHT))

    # 掩码内包围盒（用 ab0 的掩码）
    m0 = mask_of("ab0")
    mw, mh = m0.shape[1], m0.shape[0]
    ys, xs = np.where(m0)
    fy0 = int(ys.min() * HEIGHT / mh); fy1 = int(ys.max() * HEIGHT / mh)
    fx0 = int(xs.min() * WIDTH / mw); fx1 = int(xs.max() * WIDTH / mw)
    # 缩到脸中心区域，避开边缘
    h = fy1 - fy0; w = fx1 - fx0
    rect = (fy0 + int(h * 0.22), fy0 + int(h * 0.72),
            fx0 + int(w * 0.22), fx0 + int(w * 0.78))
    print("分析区域 (y%d-%d, x%d-%d)" % (rect[0], rect[1], rect[2], rect[3]))

    # 全帧掩码（最近邻上采样）
    yi = (np.arange(HEIGHT) * mh // HEIGHT).clip(0, mh - 1)
    xi = (np.arange(WIDTH) * mw // WIDTH).clip(0, mw - 1)
    mask_full = m0[yi][:, xi]

    print("\n%-30s %9s %9s %9s %8s" % ("配置", "1-2px", "3-7px", "边缘p95", "亮度Y"))
    base = None
    for tag in TAGS:
        d = os.path.join(HERE, "flick", "nz_%s_out" % tag)
        files = sorted(f for f in os.listdir(d) if f.endswith(".raw"))
        vals = []
        for f in files[4:]:          # 跳过 EMA 预热的前 4 帧
            img = load_frame(os.path.join(d, f))
            r = detail(img, rect, mask_full)
            if r:
                vals.append(r)
        a = np.array(vals)
        m = a.mean(0)
        if base is None:
            base = m
        print("%-30s %9.2f %9.2f %9.2f %8.2f  (相对全关 1-2px %+5.1f%%)" %
              (LABEL[tag], m[0], m[1], m[2], m[3], 100 * (m[0] - base[0]) / base[0]))

    # 输入原始帧的细节（下限参照）
    fin = sorted(f for f in os.listdir(INDIR) if f.endswith(".raw"))
    vals = []
    for f in fin[4:]:
        img = load_frame(os.path.join(INDIR, f))
        r = detail(img, rect, mask_full)
        if r:
            vals.append(r)
    a = np.array(vals).mean(0)
    print("%-30s %9.2f %9.2f %9.2f %8.2f" % ("原始输入帧（未处理）", a[0], a[1], a[2], a[3]))


if __name__ == "__main__":
    main()
