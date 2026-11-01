# -*- coding: utf-8 -*-
"""把「脸内逐像素时间噪声」画出来：同一输入噪声序列，3.0.9 vs 3.0.7。

三格横排（裁到人脸框）：
  1) 3.0.9 输出的一帧（对照，看清脸的位置）
  2) 3.0.9 的时间标准差图 ×40
  3) 3.0.7 的时间标准差图 ×40
白 = 该像素每帧都在变（肉眼看到的就是「脸在沸」）；黑 = 稳定。
"""
import os
import sys

HERE = os.path.abspath(".")
sys.path.insert(0, HERE)
from nz_probe import W, H, mask_index, load_mask
from raw2png import write_png

AMP = 40


def frames(tag):
    d = os.path.join(HERE, "flick", "nz_%s_out" % tag)
    fs = sorted(f for f in os.listdir(d) if f.endswith(".raw"))
    return [open(os.path.join(d, f), "rb").read() for f in fs]


def luma(buf, i):
    return buf[i] * 299 + buf[i + 1] * 587 + buf[i + 2] * 114


def bbox(tag):
    mw, mh, soft = load_mask(tag)
    x0, y0, x1, y1 = mw, mh, -1, -1
    for y in range(mh):
        row = y * mw
        for x in range(mw):
            if soft[row + x] >= 128:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    # 掩码坐标 → 帧坐标，外扩 8 帧像素
    fx0 = max(0, x0 * W // mw - 8)
    fx1 = min(W - 1, x1 * W // mw + 8)
    fy0 = max(0, y0 * H // mh - 8)
    fy1 = min(H - 1, y1 * H // mh + 8)
    return fx0, fy0, fx1, fy1


def stdmap(tag, box):
    fs = frames(tag)
    fx0, fy0, fx1, fy1 = box
    cw, ch = fx1 - fx0 + 1, fy1 - fy0 + 1
    n = len(fs)
    sums = [0.0] * (cw * ch)
    sqs = [0.0] * (cw * ch)
    for f in fs:
        for y in range(ch):
            base = ((fy0 + y) * W + fx0) * 4
            for x in range(cw):
                i = base + x * 4
                v = luma(f, i) / 1000.0
                k = y * cw + x
                sums[k] += v
                sqs[k] += v * v
    out = bytearray(cw * ch * 4)
    for k in range(cw * ch):
        m = sums[k] / n
        var = sqs[k] / n - m * m
        s = var ** 0.5 if var > 0 else 0.0
        g = min(255, int(s * AMP))
        o = k * 4
        out[o] = out[o + 1] = out[o + 2] = g
        out[o + 3] = 255
    return cw, ch, bytes(out)


def crop(tag, box, idx=5):
    fs = frames(tag)
    f = fs[min(idx, len(fs) - 1)]
    fx0, fy0, fx1, fy1 = box
    cw, ch = fx1 - fx0 + 1, fy1 - fy0 + 1
    out = bytearray(cw * ch * 4)
    for y in range(ch):
        src = ((fy0 + y) * W + fx0) * 4
        dst = y * cw * 4
        out[dst:dst + cw * 4] = f[src:src + cw * 4]
    return cw, ch, bytes(out)


def main():
    a = sys.argv[1] if len(sys.argv) > 1 else "d309_b50"
    b = sys.argv[2] if len(sys.argv) > 2 else "d307_b50"
    box = bbox(a)
    print("人脸框 %s" % (box,))
    cw, ch, face = crop(a, box)
    _, _, m1 = stdmap(a, box)
    _, _, m2 = stdmap(b, box)

    GAP = 6
    tw = cw * 3 + GAP * 2
    out = bytearray(tw * ch * 4)
    for y in range(ch):
        for panel, src in enumerate((face, m1, m2)):
            x0 = panel * (cw + GAP)
            o = (y * tw + x0) * 4
            out[o:o + cw * 4] = src[y * cw * 4:(y + 1) * cw * 4]
        for gx in range(2):
            x0 = cw + gx * (cw + GAP)
            o = (y * tw + x0) * 4
            for x in range(GAP):
                p = o + x * 4
                out[p] = out[p + 1] = out[p + 2] = 255
                out[p + 3] = 255
    dst = os.path.join(HERE, "out", "noise_map.png")
    write_png(dst, tw, ch, bytes(out))
    print("左=脸(3.0.9) 中=3.0.9 时间噪声×%d 右=3.0.7 时间噪声×%d" % (AMP, AMP))


if __name__ == "__main__":
    main()
