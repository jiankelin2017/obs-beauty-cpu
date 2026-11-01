# -*- coding: utf-8 -*-
"""验证 3.0.8 强度混合的噪声注入模型，并离线仿真修法。

模型（已由 nz_probe 实测证实）：
    out = src + (sdk - src)·t = (1-t)·src + t·sdk
    → 脸内帧间噪声 noise(t) = (1-t)·σ_src + t·σ_sdk
    实测 σ_src=3.64（±5 噪声输入）、σ_sdk=0.81，t=0.5 时 2.22 —— 与线性模型吻合。

修法 A（失败，仅作记录）：对回填残差 r=t(sdk-src) 做时间 EMA 再 out=src+r_ema。
    实测 2.22 → 3.53，**更差**。原因：src 与 -t·src 这两项的时间白噪本来是
    相互抵消的，把残差平滑掉就等于只留下 src 的噪声、抵消项没了。

修法 B（本脚本验证）：把混合的「原图端」换成时间平滑后的原图 srcT
    out = (1-t)·srcT + t·sdk = out + (1-t)·(srcT - src)
    srcT = β·src + (1-β)·srcT
    静止时 β 小 → src 的时间白噪被压到 sqrt(β/(2-β))，静态纹理在稳态下 100%
    保留（EMA 的稳态值等于输入本身）；运动时 β→1 → 完全退回原行为，无拖影。
    与 3.0.1 细节层、3.0.7 逐像素 β 是同一套思路。

用法：python sim_ema.py <tag> [t] [beta]
"""
import os
import sys

HERE = os.path.abspath(".")
sys.path.insert(0, HERE)
from nz_probe import INDIR, mask_index, lum, diff


def frames(tag):
    d = os.path.join(HERE, "flick", "nz_%s_out" % tag)
    fs = sorted(f for f in os.listdir(d) if f.endswith(".raw"))
    return [open(os.path.join(d, f), "rb").read() for f in fs]


def srcs():
    fs = sorted(f for f in os.listdir(INDIR) if f.endswith(".raw"))
    return [open(os.path.join(INDIR, f), "rb").read() for f in fs]


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "d309_b50"
    t = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    beta = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25

    ins, _ = mask_index(tag)
    ins = ins[::3]
    outs, ss = frames(tag), srcs()
    n = min(len(outs), len(ss))
    outs, ss = outs[:n], ss[:n]

    raw_dp = [diff(ss[k], ss[k - 1], ins) for k in range(1, n)]
    out_dp = [diff(outs[k], outs[k - 1], ins) for k in range(1, n)]

    # 修法 B：srcT 逐通道 EMA，再 out' = out + (1-t)(srcT - src)
    srcT = None
    sim_dp, sim_fy, base_fy, sim_eff, base_eff = [], [], [], [], []
    prevbuf = None
    for k in range(n):
        o, s = outs[k], ss[k]
        if srcT is None:
            srcT = bytearray(s)
        buf = bytearray(len(o))
        for i in range(0, len(o), 4):
            for c in range(3):
                j = i + c
                v = s[j]
                srcT[j] = int(beta * v + (1.0 - beta) * srcT[j])
                x = o[j] + (1.0 - t) * (srcT[j] - v)
                buf[j] = 0 if x < 0 else (255 if x > 255 else int(x + 0.5))
            buf[i + 3] = o[i + 3]
        base_fy.append(lum(o, ins))
        sim_fy.append(lum(bytes(buf), ins))
        base_eff.append(diff(o, s, ins))
        sim_eff.append(diff(bytes(buf), s, ins))
        if prevbuf is not None:
            sim_dp.append(diff(bytes(buf), prevbuf, ins))
        prevbuf = bytes(buf)

    print("组 %s   t=%.2f  β=%.2f   掩码内像素 %d" % (tag, t, beta, len(ins)))
    print("  %-26s %-10s" % ("口径", "脸内帧间差均值"))
    print("  %-26s %-10.3f" % ("输入(±5噪声)", sum(raw_dp) / len(raw_dp)))
    print("  %-26s %-10.3f" % ("当前输出(=3.0.9)", sum(out_dp) / len(out_dp)))
    print("  %-26s %-10.3f" % ("修法B输出", sum(sim_dp) / len(sim_dp)))
    print("")
    print("  纹理保留（脸内 |out-src|，越小越糊）: 当前 %.3f → 修法B %.3f"
          % (sum(base_eff) / n, sum(sim_eff) / n))
    print("  脸Y均值: 当前 %.2f → 修法B %.2f（应几乎不变）"
          % (sum(base_fy) / n, sum(sim_fy) / n))
    print("  说明：β=1 时退化为当前行为，可用来核对仿真是否自洽。")


if __name__ == "__main__":
    main()
