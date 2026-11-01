# -*- coding: utf-8 -*-
"""「同质心形变」测试：验证 3.0.5 的平滑开关。

为什么需要这个测试：原来的开关是**掩码质心速度**，而平移会让质心动、形变
（转头/点头/靠近镜头）不会。现有的滞后测试用 20px/帧 平移，恰好测不出这个
bug —— 用户报的偏偏是「快速移动时遮罩跟不上脸型」。

做法：同一帧前 6 帧原尺寸，后 6 帧围绕**掩码质心**放大 1.15 倍（等价于靠近
镜头）。质心按构造几乎不动，但轮廓面积变化 32%，fuai 掩码会大改。

指标：
  * 质心位移（掩码像素/帧）—— 证明这套场景质心确实"不动"
  * 收敛度：第 i 帧掩码与最终收敛掩码（第 11 帧）的 mean|Δ|
    值越小说明跟得越紧；3.0.4 应该在切换后 5~6 帧才追上，3.0.5 应 1~2 帧
"""
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

W, H = fp.W, fp.H
SCENE = os.path.join("flick", "shape")
OUT = os.path.join("flick", "shape_out")
SCALE = 1.15
SWITCH = 6          # 第 6 帧起切换成放大版
COUNT = 12


def load_rgba(path):
    return np.frombuffer(open(path, "rb").read(), dtype=np.uint8).reshape(H, W, 4)


def make_scene():
    os.makedirs(SCENE, exist_ok=True)
    src = load_rgba(os.path.join("flick", "static", "seq_000.raw"))
    # 掩码质心 → 帧坐标（角点对齐映射）
    d = open("mask_dump_000.raw", "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)
    ys, xs = np.nonzero(soft >= 128)
    ax = xs.mean() * (W - 1) / (mw - 1)
    ay = ys.mean() * (H - 1) / (mh - 1)

    rgb = Image.fromarray(src[:, :, :3])
    a = 1.0 / SCALE
    zoom = rgb.transform((W, H), Image.AFFINE,
                         (a, 0, ax * (1 - a), 0, a, ay * (1 - a)),
                         resample=Image.BICUBIC)
    zs = np.dstack([np.array(zoom), src[:, :, 3]])
    for i in range(COUNT):
        img = src if i < SWITCH else zs
        img.tofile(os.path.join(SCENE, "seq_%03d.raw" % i))
    print("场景：%d 帧，第 %d 帧起放大 %.2f 倍（锚点 %.1f, %.1f）"
          % (COUNT, SWITCH, SCALE, ax, ay))
    return ax, ay


def read_dump(path):
    d = open(path, "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    mask = np.frombuffer(d[8:8 + n], dtype=np.uint8).reshape(mh, mw)
    soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)
    raw = np.frombuffer(d[8 + 2 * n:8 + 3 * n], dtype=np.uint8).reshape(mh, mw)
    return mask, soft, raw


def soften(s):
    mh, mw = s.shape
    xi = np.arange(mw)
    xm2, xm1 = np.maximum(xi - 2, 0), np.maximum(xi - 1, 0)
    xp1, xp2 = np.minimum(xi + 1, mw - 1), np.minimum(xi + 2, mw - 1)
    v = s.astype(np.int32)
    t = (v[:, xm2] + 4 * v[:, xm1] + 6 * v + 4 * v[:, xp1] + v[:, xp2] + 8) >> 4
    yi = np.arange(mh)
    ym2, ym1 = np.maximum(yi - 2, 0), np.maximum(yi - 1, 0)
    yp1, yp2 = np.minimum(yi + 1, mh - 1), np.minimum(yi + 2, mh - 1)
    o = (t[ym2] + 4 * t[ym1] + 6 * t + 4 * t[yp1] + t[yp2] + 8) >> 4
    return np.clip(o, 0, 255).astype(np.uint8)


def chain_304(raws):
    """3.0.4：中值常开（vEma_ 很小）+ EMA alpha 固定 0.10。"""
    out, prev = [], None
    for i, r in enumerate(raws):
        if i >= 2:
            m = np.median(np.stack([raws[i - 2], raws[i - 1], r]), axis=0)
        else:
            m = r
        cur = soften(m.astype(np.uint8)).astype(np.int32)
        if prev is None:
            prev = cur.copy()
        else:
            cur = (cur * 26 + prev * 230 + 128) >> 8
            prev = cur.copy()
        out.append(np.clip(cur, 0, 255).astype(np.uint8))
    return out


def chain_305(raws, k_lo=0.40, k_hi=3.00, k_still=0.10, e_lo=0.30, e_hi=1.50):
    """3.0.5：中值由「连续两帧都在大改」门控；alpha 由 rawChg 的 motion 与
    落后误差 err 两路取大决定。"""
    out, prev = [], None
    chg_prev = 0.0
    for i, r in enumerate(raws):
        chg = 0.0 if i == 0 else float(np.abs(r.astype(np.int16)
                                               - raws[i - 1].astype(np.int16)).mean())
        if i >= 2 and chg < k_hi:
            m = np.median(np.stack([raws[i - 2], raws[i - 1], r]), axis=0).astype(np.uint8)
        else:
            m = r
        chg_prev = chg
        cur = soften(m).astype(np.int32)
        if prev is None:
            prev = cur.copy()
        else:
            motion = 0.0 if chg <= k_lo else (1.0 if chg >= k_hi else (chg - k_lo) / (k_hi - k_lo))
            err = float(np.abs(cur - prev).mean())
            if err > e_lo:
                e = 1.0 if err >= e_hi else (err - e_lo) / (e_hi - e_lo)
                motion = max(motion, e)
            alpha = k_still + (1 - k_still) * motion
            ai = int(alpha * 256 + 0.5)
            cur = (cur * ai + prev * (256 - ai) + 128) >> 8
            prev = cur.copy()
        out.append(np.clip(cur, 0, 255).astype(np.uint8))
    return out


def centroid(m):
    ys, xs = np.nonzero(m >= 128)
    if len(ys) == 0:
        return float("nan"), float("nan")
    return xs.mean(), ys.mean()


def report(name, series):
    ref = series[-1].astype(np.int16)
    print("  %-12s 收敛度 mean|mask_i - mask_11|（帧 %d 是切换点）" % (name, SWITCH))
    line = []
    for i, s in enumerate(series):
        d = float(np.abs(s.astype(np.int16) - ref).mean())
        line.append(d)
    for i in range(0, len(line), 6):
        print("      " + "  ".join("f%-2d %5.2f" % (i + j, line[i + j])
                                   for j in range(min(6, len(line) - i))))
    return line


def main():
    make_scene()
    os.makedirs(OUT, exist_ok=True)
    fp.clear_logs()
    open("dump_mask.txt", "w").write("on")
    ret, msg = fp.run_seq(SCENE, OUT, "0:50,2:50,3:30,4:50")
    if os.path.exists("dump_mask.txt"):
        os.remove("dump_mask.txt")
    print("LegacySeqTest ret=%d  %s" % (ret, msg))

    dumps = [read_dump("mask_dump_%03d.raw" % i) for i in range(COUNT)]
    raws = [d[2] for d in dumps]
    actual = [d[1] for d in dumps]

    print("\n质心位移（掩码像素/帧，证明这套场景质心几乎不动）")
    cs = [centroid(m) for m in actual]
    for i in range(1, COUNT):
        dx = cs[i][0] - cs[i - 1][0]
        dy = cs[i][1] - cs[i - 1][1]
        print("  f%-2d 位移 %6.3f  (dx %+6.3f dy %+6.3f)" % (i, (dx * dx + dy * dy) ** 0.5, dx, dy))

    print("\nrawChg（0..255 尺度）")
    for i in range(1, COUNT):
        c = float(np.abs(raws[i].astype(np.int16) - raws[i - 1].astype(np.int16)).mean())
        print("  f%-2d rawChg %7.3f" % (i, c))

    print()
    a = report("3.0.4 复刻", chain_304(raws))
    b = report("3.0.5 实测", actual)
    sim = chain_305(raws)
    dev = max(int(np.abs(sim[i].astype(np.int16) - actual[i].astype(np.int16)).max())
              for i in range(COUNT))
    print("\n  复刻自检：3.0.5 Python 复刻 vs DLL 实测 最大偏差 %d 级 %s"
          % (dev, "OK" if dev <= 2 else "!! 不一致"))

    def settle(line, tol=1.0):
        for i in range(SWITCH, COUNT):
            if line[i] < tol:
                return i - SWITCH
        return -1

    print("\n  切换后收敛帧数（收敛度 < 1.0 视为跟上）：3.0.4 %s 帧 / 3.0.5 %s 帧"
          % (settle(a), settle(b)))
    print("  切换后第 1 帧残留：3.0.4 %.2f / 3.0.5 %.2f"
          % (a[SWITCH], b[SWITCH]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
