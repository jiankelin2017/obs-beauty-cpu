# -*- coding: utf-8 -*-
"""持续形变下的拖尾定量 + 阈值扫描。

3.0.5 的阶跃测试（一步放大 1.15 倍）显示 0 帧收敛，但真实转头是**持续**形变，
中等速度可能落在 rawChg 的灰色区（α 只有 0.15~0.4），稳态拖尾 = (1-α)/α × v。
本脚本用**线性持续放大**的人脸序列测三种速度下的拖尾，并用已验证（0 级偏差）
的 Python 复刻扫描候选阈值。

拖尾定义：mean|mask_out(i) − soften(raw(i))|，即「输出离当前输入还差多少」。
"""
import glob
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp
from shape_test import soften, read_dump, chain_305, chain_304

W, H = fp.W, fp.H
COUNT = 12          # fp.run_seq 写死 12 帧


def make_seq(scale_end, frames, tag, anchor):
    """前 2 帧静止（1.0），随后线性放大到 scale_end。"""
    d = os.path.join("flick", "sweep_" + tag)
    os.makedirs(d, exist_ok=True)
    src = np.frombuffer(open(os.path.join("flick", "static", "seq_000.raw"), "rb").read(),
                        dtype=np.uint8).reshape(H, W, 4)
    ax, ay = anchor
    rgb = Image.fromarray(src[:, :, :3])
    base = np.array(rgb)
    for i in range(COUNT):
        if i < 2:
            s = 1.0
        else:
            s = 1.0 + (scale_end - 1.0) * (i - 1) / 9.0
        a = 1.0 / s
        z = rgb.transform((W, H), Image.AFFINE, (a, 0, ax * (1 - a), 0, a, ay * (1 - a)),
                          resample=Image.BICUBIC)
        out = np.dstack([np.array(z), src[:, :, 3]])
        out.tofile(os.path.join(d, "seq_%03d.raw" % i))
    return d, (ax, ay)


def trailing(series, soft_raw):
    """每帧 mean|out - soften(raw)|。"""
    return [float(np.abs(series[i].astype(np.int16) - soft_raw[i].astype(np.int16)).mean())
            for i in range(len(series))]


def main():
    # 先跑一次静态拿到掩码质心（make_seq 需要）
    fp.clear_logs()
    open("dump_mask.txt", "w").write("on")
    fp.run_seq(os.path.join("flick", "static"), os.path.join("flick", "static_out"), "0:50")
    if os.path.exists("dump_mask.txt"):
        os.remove("dump_mask.txt")

    # 1.30 会把人脸推出检测范围（推理中断），上限取 1.20
    cases = [("fast", 1.20), ("mid", 1.12), ("slow", 1.05)]
    # 锚点只算一次：后面 clear_logs 会把 mask_dump 清掉
    f0 = sorted(glob.glob("mask_dump_*.raw"))[0]
    dd = open(f0, "rb").read()
    mw, mh = struct.unpack_from("<ii", dd, 0)
    npx0 = mw * mh
    soft0 = np.frombuffer(dd[8 + npx0:8 + 2 * npx0], dtype=np.uint8).reshape(mh, mw)
    ys0, xs0 = np.nonzero(soft0 >= 128)
    anchor = (xs0.mean() * (W - 1) / (mw - 1), ys0.mean() * (H - 1) / (mh - 1))
    for tag, send in cases:
        d, _ = make_seq(send, COUNT, tag, anchor)
        out = os.path.join("flick", "sweep_%s_out" % tag)
        os.makedirs(out, exist_ok=True)
        fp.clear_logs()
        open("dump_mask.txt", "w").write("on")
        ret, msg = fp.run_seq(d, out, "0:50,2:50,3:30,4:50")
        if os.path.exists("dump_mask.txt"):
            os.remove("dump_mask.txt")
        files = sorted(glob.glob("mask_dump_*.raw"))[-COUNT:]
        # 人脸丢失会让序列提前中止，取实际拿到的帧数
        COUNT_USE = len(files)
        dumps = [read_dump(f) for f in files]
        raws = [x[2] for x in dumps]
        actual = [x[1] for x in dumps]
        print("  实际拿到 %d 帧" % COUNT_USE)
        soft_raw = [soften(r) for r in raws]
        chg = [0.0] + [float(np.abs(raws[i].astype(np.int16) - raws[i - 1].astype(np.int16)).mean())
                       for i in range(1, COUNT_USE)]
        soft_raw = soft_raw[:COUNT_USE]
        tr = trailing(actual, soft_raw)
        act = [float(np.mean(tr[2:]))]
        print("\n== %s  放大到 %.2f  ret=%d ==" % (tag, send, ret))
        print("  rawChg : " + " ".join("%.1f" % c for c in chg[2:]))
        print("  3.0.5 实测拖尾: " + " ".join("%.2f" % t for t in tr))
        print("  稳态平均拖尾 %.2f 级（≈ %.1f 帧像素）" % (act[0], act[0] / 255 * 0 + act[0] / 64 * 5.6))

        # 阈值扫描（Python 复刻，已验证 0 级偏差）
        cands = [
            ("3.0.5 现值  chg .40/3.0 err .30/1.5", 0.40, 3.00, 0.30, 1.50),
            ("A            chg .25/2.0 err .15/0.8", 0.25, 2.00, 0.15, 0.80),
            ("B            chg .20/1.5 err .12/0.6", 0.20, 1.50, 0.12, 0.60),
            ("C            chg .15/1.2 err .10/0.5", 0.15, 1.20, 0.10, 0.50),
        ]
        for name, lo, hi, elo, ehi in cands:
            ser = chain_305(raws, k_lo=lo, k_hi=hi, e_lo=elo, e_hi=ehi)
            t = trailing(ser, soft_raw)
            print("    %-38s 稳态拖尾 %.2f 级" % (name, float(np.mean(t[2:]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
