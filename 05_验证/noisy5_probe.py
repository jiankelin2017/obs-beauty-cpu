# -*- coding: utf-8 -*-
"""高幅噪声探针（3.0.1 根因闸门补强）。

flicker_probe.py 的 noisy 场景固定 ±2，不足以复现真实摄像头的噪点幅度。
本驱动复用它的 run_seq / clear_logs，把噪声幅度参数化，对比
「磨皮50+锐化50」与「仅磨皮50」在帧间稳定性上的差异。

用法：python noisy5_probe.py [幅度]   （默认 5）
输出目录：flick/noisy<幅度>_s50_out 与 flick/noisy<幅度>_s0_out
随后用 diff_rough.py 分析两个目录。
"""
import os
import random
import sys

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp


def prep_noisy(d, amp):
    os.makedirs(d, exist_ok=True)
    rgba, w, h = fp.read_png_rgba("out/frame_0.png")
    assert (w, h) == (fp.W, fp.H), (w, h)
    rnd = random.Random(20261025)
    for k in range(fp.COUNT):
        b = bytearray(rgba)
        for i in range(0, len(b), 4):
            for c in range(3):
                v = b[i + c] + rnd.randint(-amp, amp)
                b[i + c] = 0 if v < 0 else (255 if v > 255 else v)
        open(os.path.join(d, "seq_%03d.raw" % k), "wb").write(bytes(b))


def analyze_masks():
    """复现引擎 temporalSmooth 的质心速度计算，校准 EMA 速度阈值。"""
    import struct
    cents = []
    for f in sorted(os.listdir(".")):
        if not f.startswith("mask_dump_"):
            continue
        d = open(f, "rb").read()
        mw, mh = struct.unpack_from("<ii", d, 0)
        n = mw * mh
        soft = d[8 + n:8 + 2 * n]
        sx = sy = sw = 0.0
        for i, v in enumerate(soft):
            if v:
                y, x = divmod(i, mw)
                sx += x * v
                sy += y * v
                sw += v
        cents.append((sx / sw, sy / sw) if sw > 0 else (-1.0, -1.0))
    vema = 0.0
    print("  掩码质心（soft）帧间位移与引擎同款 vEma_ 复现：")
    for i in range(1, len(cents)):
        if cents[i][0] < 0 or cents[i - 1][0] < 0:
            print("    %03d->%03d: 质心缺失" % (i - 1, i))
            continue
        dx = cents[i][0] - cents[i - 1][0]
        dy = cents[i][1] - cents[i - 1][1]
        v = (dx * dx + dy * dy) ** 0.5
        vema = 0.6 * v + 0.4 * vema
        print("    %03d->%03d: v=%.3f  vEma_=%.3f" % (i - 1, i, v, vema))


def main():
    amp = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    indir = os.path.join("flick", "noisy%d" % amp)
    prep_noisy(indir, amp)
    here = os.path.abspath(".")
    for tag, panel in (("s50", "0:50,4:50"), ("s0", "0:50")):
        outdir = os.path.join("flick", "noisy%d_%s_out" % (amp, tag))
        os.makedirs(outdir, exist_ok=True)
        fp.clear_logs()
        dump = tag == "s50"   # 掩码与参数无关，借 s50 这轮转一份就够
        if dump:
            open(os.path.join(here, "dump_mask.txt"), "w").write("on")
        ret, msg = fp.run_seq(indir, outdir, panel)
        if dump:
            os.remove(os.path.join(here, "dump_mask.txt"))
            analyze_masks()
        print("amp=%d %s ret=%d  %s" % (amp, tag, ret, msg))


if __name__ == "__main__":
    main()
