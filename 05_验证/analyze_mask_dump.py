# -*- coding: utf-8 -*-
"""分析 mask_dump.raw：把软化后的掩码按 buildMaskMap 的算法双线性上采样到全分辨率，
沿 verify_soft_boundary.py 取样行打印掩码值与预测提亮量，与实测对照。

要查的问题：残留的 27 级硬跳变到底在掩码里（软化不够），还是在上采样/施加环节。
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

W, H = 640, 394
DUMP = os.path.join(HERE, "mask_dump.raw")
RAW = os.path.join(HERE, "probe_in.raw")
K_MAX = 0.70          # applyRegionEffects 的常数，面板美白 100 时 k = 1.0*0.70


def luma(b, i):
    return (b[i * 4] * 299 + b[i * 4 + 1] * 587 + b[i * 4 + 2] * 114) // 1000


def main():
    d = open(DUMP, "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    off = 8
    mask = d[off:off + n]
    soft = d[off + n:off + 2 * n]
    print("掩码分辨率 %dx%d  原始值直方图：" % (mw, mh))
    for name, buf in (("mask_（原始）", mask), ("maskSoft_（软化后）", soft)):
        h = {}
        for v in buf:
            h[v] = h.get(v, 0) + 1
        top = sorted(h.items(), key=lambda kv: -kv[1])[:6]
        print("  %-16s 0=%d(%.2f%%) 255=%d(%.2f%%) 中间=%d(%.2f%%) 其余档位=%s"
              % (name, h.get(0, 0), h.get(0, 0) * 100.0 / n,
                 h.get(255, 0), h.get(255, 0) * 100.0 / n,
                 sum(c for v, c in h.items() if 0 < v < 255),
                 sum(c for v, c in h.items() if 0 < v < 255) * 100.0 / n,
                 sorted((v, c) for v, c in h.items() if 0 < v < 255)[:12]))

    # ---- 复算 buildMaskMap 的双线性上采样（逐位复刻，含 8bit 小数截断）----
    xs = []
    for x in range(W):
        q = (x * (mw - 1) * 65536) // (W - 1)
        i0 = q >> 16
        f = ((q & 0xFFFF) * 256) // 65536
        if i0 >= mw - 1:
            i0, f = mw - 1, 0
        xs.append((i0, min(i0 + 1, mw - 1), f))
    ys = []
    for y in range(H):
        q = (y * (mh - 1) * 65536) // (H - 1)
        i0 = q >> 16
        f = ((q & 0xFFFF) * 256) // 65536
        if i0 >= mh - 1:
            i0, f = mh - 1, 0
        ys.append((i0, min(i0 + 1, mh - 1), f))

    rgba = open(RAW, "rb").read()
    assert len(rgba) == W * H * 4

    def upsample_row(y):
        y0, y1, fy = ys[y]
        out = []
        for x in range(W):
            x0, x1, fx = xs[x]
            a0 = soft[y0 * mw + x0]; a1 = soft[y0 * mw + x1]
            b0 = soft[y1 * mw + x0]; b1 = soft[y1 * mw + x1]
            top = a0 * (256 - fx) + a1 * fx
            bot = b0 * (256 - fx) + b1 * fx
            out.append((top * (256 - fy) + bot * fy) >> 16)
        return out

    def predict_row(y, mv_row):
        """按 applyRegionEffects 的美白公式预测每像素提亮级数"""
        k = K_MAX
        res = []
        for x in range(W):
            mv = mv_row[x]
            t = int(k * mv * 16777216.0 / 65025.0)
            i = y * W + x
            tot = 0
            for c in range(3):
                v = rgba[i * 4 + c]
                tot += (v * (255 - v) * t) >> 24
            res.append(tot // 3)   # 三通道平均，和 luma 量级一致
        return res

    # 找提亮最大行（与 verify_soft_boundary.py 同一规则）
    best = None
    for y in range(60, H - 60, 4):
        s = 0
        for x in range(W):
            i = y * W + x
            s += max(0, luma(rgba, i) - luma(rgba, i))  # 占位
        best = (0, y)
        break
    y = 164
    print("\n取样行 y=%d -> 掩码行 y0=%d y1=%d fy=%d" % (y, ys[y][0], ys[y][1], ys[y][2]))

    mv = upsample_row(y)
    pr = predict_row(y, mv)

    print("\n  x  : mv  预测提亮")
    line = ""
    for x in range(360, 395):
        line += "%d:%d/%d " % (x, mv[x], pr[x])
    for i in range(0, len(line), 90):
        print("  " + line[i:i + 90])

    # 原始掩码在同一行（不上采样，只看掩码像素）
    y0, y1, fy = ys[y]
    print("\n  原始掩码行 y=%d，x 105..120：" % y0)
    line = ""
    for x in range(105, min(121, mw)):
        line += "%d:%d " % (x, mask[y0 * mw + x])
    print("  " + line)
    print("  软化掩码行 y=%d，x 105..120：" % y0)
    line = ""
    for x in range(105, min(121, mw)):
        line += "%d:%d " % (x, soft[y0 * mw + x])
    print("  " + line)
    if y1 != y0:
        print("  原始掩码行 y=%d，x 105..120：" % y1)
        line = ""
        for x in range(105, min(121, mw)):
            line += "%d:%d " % (x, mask[y1 * mw + x])
        print("  " + line)
        print("  软化掩码行 y=%d，x 105..120：" % y1)
        line = ""
        for x in range(105, min(121, mw)):
            line += "%d:%d " % (x, soft[y1 * mw + x])
        print("  " + line)

    # 相邻跳变统计（上采样后的掩码）
    jumps = 0
    maxj = 0
    where = -1
    for x in range(1, W):
        dd = abs(mv[x] - mv[x - 1])
        if dd > maxj:
            maxj, where = dd, x
        if dd > 30:
            jumps += 1
    print("\n上采样后掩码：相邻跳变 >30 的次数 %d，最大 %d（x=%d）" % (jumps, maxj, where))
    return 0


if __name__ == "__main__":
    sys.exit(main())
