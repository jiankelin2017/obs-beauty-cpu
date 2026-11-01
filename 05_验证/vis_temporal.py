# -*- coding: utf-8 -*-
"""把 temporal_ab.py 跑出来的连续输出帧可视化成胶片 + 帧间差异图。

目的：用眼睛找出「脸颊处黑白灰快速跳」到底是哪一种故障：
  A) 掩码边界闪烁 —— 差异会集中在脸颊/下颌一圈
  B) 全局亮度振荡 —— 整帧差异
  C) 孤立的黑/白噪点 —— 差异呈椒盐状
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from raw2png import write_png  # noqa: E402

IN = os.path.join(HERE, "tb_in")
OUT = os.path.join(HERE, "tb_out")
W, H = 640, 394


def load(p):
    return open(p, "rb").read()


def main():
    n = len([f for f in os.listdir(OUT) if f.startswith("seq_")])
    print("frames in %s: %d" % (OUT, n))
    frames = [load(os.path.join(OUT, "seq_%03d.raw" % k)) for k in range(n)]
    ins = [load(os.path.join(IN, "seq_%03d.raw" % k)) for k in range(n)]

    # ---- 1) 胶片：第 0..7 帧，缩到 1/2 拼一排 --------------------------
    cols = 8
    sw, sh = W // 2, H // 2
    strip = bytearray(sw * cols * 4)
    for c in range(cols):
        f = frames[c]
        for y in range(sh):
            for x in range(sw):
                s = ((y * 2) * W + (x * 2)) * 4
                o = (y * sw * cols + (c * sw + x)) * 4
                strip[o:o + 4] = f[s:s + 4]
    write_png(os.path.join(HERE, "vis_strip.png"), sw * cols, sh, bytes(strip))

    # ---- 2) 帧间差异热图：|out[k]-out[k-1]| 放大 4 倍 -------------------
    for k in (1, 2, 3):
        a, b = frames[k - 1], frames[k]
        d = bytearray(W * H * 4)
        for i in range(W * H):
            o = i * 4
            m = max(abs(b[o] - a[o]), abs(b[o + 1] - a[o + 1]), abs(b[o + 2] - a[o + 2]))
            v = min(255, m * 4)
            d[o] = d[o + 1] = d[o + 2] = v
            d[o + 3] = 255
        write_png(os.path.join(HERE, "vis_diff_%d.png" % k), W, H, bytes(d))

    # ---- 3) 输出 vs 输入差异（效果作用范围）------------------------------
    a, b = ins[0], frames[0]
    d = bytearray(W * H * 4)
    for i in range(W * H):
        o = i * 4
        m = max(abs(b[o] - a[o]), abs(b[o + 1] - a[o + 1]), abs(b[o + 2] - a[o + 2]))
        v = min(255, m * 2)
        d[o] = d[o + 1] = d[o + 2] = v
        d[o + 3] = 255
    write_png(os.path.join(HERE, "vis_effect.png"), W, H, bytes(d))

    # ---- 4) 统计：差异最大的 20 个像素位置 -------------------------------
    print("")
    print("帧间差异最大的像素（看是否集中在一处 = 掩码边界）:")
    for k in (1, 2, 3):
        a, b = frames[k - 1], frames[k]
        px = []
        for i in range(W * H):
            o = i * 4
            m = max(abs(b[o] - a[o]), abs(b[o + 1] - a[o + 1]), abs(b[o + 2] - a[o + 2]))
            if m > 40:
                px.append((i % W, i // W, m))
        px.sort(key=lambda t: -t[2])
        print("  k=%d  差异>40 的像素 %d 个" % (k, len(px)))
        if px:
            xs = [p[0] for p in px]
            ys = [p[1] for p in px]
            print("     x 范围 %d..%d (中位 %d)   y 范围 %d..%d (中位 %d)"
                  % (min(xs), max(xs), sorted(xs)[len(xs) // 2],
                     min(ys), max(ys), sorted(ys)[len(ys) // 2]))
            print("     前 8 个: %s" % px[:8])
    print("")
    print("生成: vis_strip.png / vis_diff_1..3.png / vis_effect.png")


if __name__ == "__main__":
    main()
