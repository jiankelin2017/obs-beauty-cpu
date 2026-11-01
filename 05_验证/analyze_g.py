# -*- coding: utf-8 -*-
"""全局锐化效果评估：分别统计「掩码内（脸）」与「掩码外（背景）」的细节能量。

掩码在 flick/mask_<tag>.raw（soft 分量），输出帧在 flick/nz_<tag>_out/*.raw。
"""
import os
import struct

import numpy as np

HERE = r"C:\legacy_e2e"
FLICK = os.path.join(HERE, "flick")
TAGS = [
    ("t_3013p", "磨皮50（全局0，基线）"),
    ("g50",     "磨皮50 + 全局50"),
    ("g100",    "磨皮50 + 全局100"),
    ("gon",     "仅全局100（磨皮0）"),
    ("gf",      "磨皮50+锐化50+全局50"),
]


def mask_soft(tag):
    d = open(os.path.join(FLICK, "mask_%s.raw" % tag), "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    soft = np.frombuffer(d[8 + mw * mh:8 + 2 * mw * mh], np.uint8).reshape(mh, mw)
    return soft, mw, mh


def hi_energy(y, sel):
    pad = np.pad(y, 1, mode="edge")
    box = np.zeros_like(y)
    for dy in range(3):
        for dx in range(3):
            box += pad[dy:dy + y.shape[0], dx:dx + y.shape[1]]
    box /= 9.0
    return (y - box)[sel].std()


def run():
    soft0, mw, mh = mask_soft("t_3013p")
    n = os.path.getsize(os.path.join(FLICK, "nz_t_3013p_out", "seq_000.raw")) // 4
    W, H = 1074, n // 1074
    yi = (np.arange(H) * mh // H).clip(0, mh - 1)
    xi = (np.arange(W) * mw // W).clip(0, mw - 1)
    mfull = soft0[yi][:, xi]

    ys, xs = np.where(mfull >= 200)
    fy0, fy1, fx0, fx1 = ys.min(), ys.max(), xs.min(), xs.max()
    hh, ww = fy1 - fy0, fx1 - fx0
    inner = np.zeros_like(mfull, bool)
    sl = (slice(fy0 + int(hh * 0.18), fy0 + int(hh * 0.75)),
          slice(fx0 + int(ww * 0.22), fx0 + int(ww * 0.78)))
    inner[sl] = mfull[sl] >= 200

    occ = mfull > 8
    dil = occ.copy()
    for _ in range(7):
        p = np.pad(dil, 1, mode="constant", constant_values=False)
        dil = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] |
               p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:] | p[1:-1, 1:-1])
    outer = ~dil
    outer[:8, :] = False
    outer[-8:, :] = False
    outer[:, :8] = False
    outer[:, -8:] = False
    print("帧 %dx%d  脸内像素 %d  背景像素 %d（%.1f%%）" %
          (W, H, inner.sum(), outer.sum(), 100.0 * outer.sum() / (W * H)))

    print("\n%-26s %10s %10s %9s %9s" %
          ("配置", "脸内1-2px", "背景1-2px", "脸内Y", "背景Y"))
    base = None
    for tag, label in TAGS:
        d = os.path.join(FLICK, "nz_%s_out" % tag)
        if not os.path.isdir(d):
            print("%-26s 缺输出" % label)
            continue
        vals = []
        for f in sorted(os.listdir(d))[4:]:
            if not f.endswith(".raw"):
                continue
            a = np.frombuffer(open(os.path.join(d, f), "rb").read(), np.uint8)
            img = a.reshape(-1, 4)[:, 2::-1].astype(np.float32)   # BGRA → RGB
            y = (img[:, 0] * 0.114 + img[:, 1] * 0.587 +
                 img[:, 2] * 0.299).reshape(H, W)
            vals.append((hi_energy(y, inner), hi_energy(y, outer),
                         y[inner].mean(), y[outer].mean()))
        m = np.array(vals).mean(0)
        if base is None:
            base = m
        print("%-26s %10.2f %10.2f %9.2f %9.2f   (背景 %+.0f%%)" %
              (label, m[0], m[1], m[2], m[3], 100 * (m[1] - base[1]) / base[1]))


if __name__ == "__main__":
    run()
