# -*- coding: utf-8 -*-
"""3.0.4 验证：3 帧时域中值对掩码过渡带抖动的实际效果。

mask_dump_%03d.raw 结构（每帧）：
    int hdr[2] = {mw, mh}
    npx 字节  mask_     —— 3.0.4 起是**中值后**的掩码
    npx 字节  maskSoft_ —— 最终输出掩码（喂给 applyRegionEffects / applySharpen）
    npx 字节  rawTmp_   —— 真正未处理的 fuai 原始掩码（3.0.4 起才有）

因为同一批 dump 里的 rawTmp_ 序列对所有版本都相同，可以在这条**同一条原始
序列**上重建 3.0.3 的链路（soften + EMA0.10）做同输入对比，避免跨批次对比
（fuai 的 inferCnt 会变，跨批次像素数不可比）。

用法: python analyze_304.py [目录]
"""
import glob
import os
import struct
import sys

import numpy as np


def read_dump(path):
    d = open(path, "rb").read()
    mw, mh = struct.unpack("<2i", d[:8])
    n = mw * mh
    mask = np.frombuffer(d[8:8 + n], dtype=np.uint8).reshape(mh, mw)
    soft = np.frombuffer(d[8 + n:8 + 2 * n], dtype=np.uint8).reshape(mh, mw)
    raw = None
    if len(d) >= 8 + 3 * n:
        raw = np.frombuffer(d[8 + 2 * n:8 + 3 * n], dtype=np.uint8).reshape(mh, mw)
    return mw, mh, mask, soft, raw


def soften(src):
    """完全复刻 LegacyRegion::softenMask()：可分离 5-tap 二项式，边界夹取。"""
    mh, mw = src.shape
    if mw < 3 or mh < 3:
        return src.copy()
    xi = np.arange(mw)
    xm2 = np.maximum(xi - 2, 0)
    xm1 = np.maximum(xi - 1, 0)
    xp1 = np.minimum(xi + 1, mw - 1)
    xp2 = np.minimum(xi + 2, mw - 1)
    s = src.astype(np.int32)
    t = (s[:, xm2] + 4 * s[:, xm1] + 6 * s + 4 * s[:, xp1] + s[:, xp2] + 8) >> 4
    yi = np.arange(mh)
    ym2 = np.maximum(yi - 2, 0)
    ym1 = np.maximum(yi - 1, 0)
    yp1 = np.minimum(yi + 1, mh - 1)
    yp2 = np.minimum(yi + 2, mh - 1)
    o = (t[ym2] + 4 * t[ym1] + 6 * t + 4 * t[yp1] + t[yp2] + 8) >> 4
    return np.clip(o, 0, 255).astype(np.uint8)


def ema_chain(raws, alpha=0.10):
    """3.0.3 链路：逐帧 soften(raw) 再 EMA。alpha 按 0.10 固定（vEma~0 时就是它）。"""
    ai = int(alpha * 256.0 + 0.5)
    out = []
    prev = None
    for r in raws:
        cur = soften(r).astype(np.int32)
        if prev is None:
            prev = cur.copy()
        else:
            cur = (cur * ai + prev * (256 - ai) + 128) >> 8
            prev = cur.copy()
        out.append(np.clip(cur, 0, 255).astype(np.uint8))
    return out


def median3(raws):
    """3.0.4 新增那一步：逐像素三帧中值。

    与 DLL 一致：前两帧历史不够，直接透传（不冻结），第 3 帧起才表决。
    """
    out = []
    for i, r in enumerate(raws):
        if i < 2:
            out.append(r.copy())
        else:
            st = np.stack([raws[i - 2], raws[i - 1], r])
            out.append(np.median(st, axis=0).astype(np.uint8))
    return out


def band_mask(a, b):
    """过渡带：任一帧的 soft 落在 1..249。"""
    return ((a > 0) & (a < 250)) | ((b > 0) & (b < 250))


def stats(series, name):
    rows = []
    for i in range(1, len(series)):
        a = series[i - 1].astype(np.int32)
        b = series[i].astype(np.int32)
        m = band_mask(series[i - 1], series[i])
        d = np.abs(b - a)[m]
        if d.size == 0:
            continue
        rows.append((d.mean(), d.max(), int((d > 4).sum()), d.size))
    rows = np.array(rows, dtype=np.float64)
    print("  %-26s 帧间|d|均值 %5.2f  中位 %5.2f  最大 %4.0f   >4级 %6.1f px"
          % (name, rows[:, 0].mean(), np.median(rows[:, 0]),
             rows[:, 1].max(), rows[:, 2].mean()))
    return rows


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else r"C:/legacy_e2e"
    files = sorted(glob.glob(os.path.join(d, "mask_dump_*.raw")))
    if not files:
        print("没有 mask_dump_*.raw")
        return 1
    frames = [read_dump(f) for f in files]
    if frames[0][4] is None:
        print("dump 里没有 rawTmp_ 块 —— 请用 3.0.4 的钩子重跑")
        return 1
    raws = [f[4] for f in frames]
    soft_304 = [f[3] for f in frames]
    print("帧数 %d  掩码 %dx%d  文件 %s"
          % (len(frames), frames[0][0], frames[0][1], os.path.basename(files[0])))

    print("\n[A] 最终输出掩码（maskSoft_）帧间抖动，只在过渡带统计")
    r303 = stats(ema_chain(raws), "3.0.3  soften+EMA0.10")
    r304 = stats(soft_304, "3.0.4  实测（中值+EMA）")
    sim = ema_chain(median3(raws))
    rsim = stats(sim, "3.0.4  Python 复刻")

    # 复刻自检：Python 复刻应当和 DLL 实测几乎逐像素一致
    diff = [np.abs(sim[i].astype(np.int32) - soft_304[i].astype(np.int32))
            for i in range(len(sim))]
    md = max(int(x.max()) for x in diff)
    print("  复刻自检：与 DLL 实测最大偏差 %d 级 %s" % (md, "OK" if md <= 2 else "!! 不一致"))

    print("\n[B] 结论")
    base = r303[:, 0].mean()
    now = r304[:, 0].mean()
    print("  帧间残差 %.3f -> %.3f  (%+.1f%%)" % (base, now, (now / base - 1) * 100))
    print("  帧间尖峰上限 %.0f -> %.0f 级" % (r303[:, 1].max(), r304[:, 1].max()))
    print("  >4 级像素 %.1f -> %.1f px/帧对" % (r303[:, 2].mean(), r304[:, 2].mean()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
