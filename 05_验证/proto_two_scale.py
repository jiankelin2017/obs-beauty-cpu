# -*- coding: utf-8 -*-
"""proto_two_scale.py —— C23 §11 双尺度带通设计的 numpy 原型验证。

为什么先做 numpy
----------------
§10.5 已经用 RMSE 扫参证明「只调强度 / 只加梯度门控」都到不了 2.0，
所以这一轮不再拿金标 RMSE 当优化目标，而是先拿**传递函数**当目标：
用 real_grating.py 同一把尺子（差分 + 复数投影）测原型的振幅-频率响应，
对上 SDK 的三条结构判据之后再落 C++。

设计（C23 §11.6）
----------------
    B1 = 窄模糊  σ1
    B2 = 宽模糊  σ2
    D  = B2 - B1                     带通（signed）
    E  = C + wc·D + (1-wc)·(B2 - C)   ≡ §3.3 的 even（I=1, evenfactor=0.7 → wc=0.3）
    A  = |D_g|                        振幅代理（只测绿通道，同 §3.1）
    w  = 1 / (1 + (A/T)^2)            Wiener 式收缩，强纹理自动放过
    out = C + w·(E - C)

`w` 的推导（写在 C23 §12）：SDK 的「改动量」在 A=2→A=16 之间**与频率无关地**
缩到 0.58 倍，说明振幅门控是作用在整段改动上的**标量**，不是频带相关项。
用 1/(1+(A/T)^2) 拟合四个振幅档得 T≈19（灰阶，作用在光栅振幅上）。

用法
----
    python proto_two_scale.py                 # 默认参数，跑光栅表 + RMSE
    python proto_two_scale.py --scan          # 粗扫 σ1/σ2，看判据落点
    python proto_two_scale.py --s1 3.9 --s2 8.6 --T 15 --dump
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'goldens', 'real')

W, H = 1920, 1080
TAG = 'cam'
PERIODS = (8, 12, 16, 24, 32, 48, 64)
AMPS = (2.0, 4.0, 8.0, 16.0)

# SDK bt1, blur=100 的实测表（C23 §11.2），原型的对标基准
SDK = {
    8:  (0.289, 0.283, 0.369, 0.579),
    12: (0.424, 0.465, 0.485, 0.620),
    16: (0.279, 0.302, 0.384, 0.553),
    24: (0.201, 0.240, 0.319, 0.544),
    32: (0.353, 0.388, 0.452, 0.609),
    48: (0.579, 0.636, 0.660, 0.722),
    64: (0.698, 0.765, 0.797, 0.826),
}


# --------------------------------------------------------------------------
# 基础工具（与 real_grating.py 保持一致，避免两把尺子）
# --------------------------------------------------------------------------
def load_raw(p, w=W, h=H):
    return np.fromfile(p, np.uint8).reshape((h, w, 4))


def read_mask(p):
    raw = open(p, 'rb').read()
    mw, mh = np.frombuffer(raw[:8], np.int32)
    return np.frombuffer(raw[8:], np.uint8).reshape((mh, mw))


def upscale_mask(m, w, h):
    ys = (np.arange(h) * m.shape[0]) // h
    xs = (np.arange(w) * m.shape[1]) // w
    return m[ys][:, xs] > 127


def boxsum(a, r):
    p = np.pad(a.astype(np.int32), r)
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def erode(reg, r):
    return boxsum(reg, r) == (2 * r + 1) ** 2


def add_grating(arr, period, amp):
    out = arr.copy()
    x = np.arange(W, dtype=np.float32)
    g = amp * np.cos(2.0 * np.pi * x / float(period))
    v = out[:, :, 1].astype(np.float32) + g[None, :]
    out[:, :, 1] = np.clip(v, 0, 255).astype(np.uint8)
    return out


def basis(period):
    x = np.arange(W, dtype=np.float32)
    ph = 2.0 * np.pi * x / float(period)
    return np.cos(ph)[None, :], np.sin(ph)[None, :]


def complex_gain(d, cos_b, sin_b, reg):
    c = np.broadcast_to(cos_b, d.shape)[reg]
    s = np.broadcast_to(sin_b, d.shape)[reg]
    v = d[reg]
    dc = float((c * c).sum())
    ds = float((s * s).sum())
    gc = float((v * c).sum()) / dc if dc > 0 else 0.0
    gs = float((v * s).sum()) / ds if ds > 0 else 0.0
    return abs(complex(gc, gs))


# --------------------------------------------------------------------------
# 原型本体
# --------------------------------------------------------------------------
BOX_N = 0          # >0 时用 N 次盒式近似高斯（C++ 侧要落地的是这个）


def box_width(sigma, n):
    """N 次宽 w 的盒式 ≈ 高斯 σ：σ² = n(w²-1)/12 → w = sqrt(12σ²/n+1)。取奇数。"""
    if sigma <= 0:
        return 1
    w = int(round(np.sqrt(12.0 * sigma * sigma / n + 1.0)))
    return max(1, w | 1)


def gblur(plane, sigma):
    """单通道模糊，边界反射。BOX_N>0 时用 N 次盒式，否则真高斯。"""
    if sigma <= 0:
        return plane
    if BOX_N <= 0:
        return cv2.GaussianBlur(plane, (0, 0), sigmaX=sigma, sigmaY=sigma,
                                borderType=cv2.BORDER_REFLECT)
    w = box_width(sigma, BOX_N)
    r = w // 2
    out = plane
    for _ in range(BOX_N):
        p = np.pad(out, ((r, r), (0, 0)), mode='reflect')
        c = np.pad(p.cumsum(0), ((1, 0), (0, 0)))
        out = (c[w:] - c[:-w]) / float(w)
        p = np.pad(out, ((0, 0), (r, r)), mode='reflect')
        c = np.pad(p.cumsum(1), ((0, 0), (1, 0)))
        out = (c[:, w:] - c[:, :-w]) / float(w)
    return out.astype(np.float32)


def split(rgba, s1, s2):
    """算 B1/B2，返回 (C, B1, B2)，都是 float32 RGB。"""
    c = rgba[:, :, :3].astype(np.float32)
    b1 = np.empty_like(c)
    b2 = np.empty_like(c)
    for k in range(3):
        b1[:, :, k] = gblur(c[:, :, k], s1)
        b2[:, :, k] = gblur(c[:, :, k], s2)
    return c, b1, b2


def amp_proxy(c, b1, b2, mode):
    """振幅代理，只测绿通道。三种候选：
         d  = |B2-B1|   带通能量（高频处趋 0，测不到高频振幅 → 已知缺陷）
         c1 = |C -B1|   窄尺度以上的细节量
         c2 = |C -B2|   宽尺度以上的细节量（近似「局部对比度」）
    """
    if mode == 'd':
        return np.abs(b2[:, :, 1] - b1[:, :, 1])
    if mode == 'c1':
        return np.abs(c[:, :, 1] - b1[:, :, 1])
    if mode == 'c2':
        return np.abs(c[:, :, 1] - b2[:, :, 1])
    raise ValueError(mode)


def compose(c, b1, b2, wc, T, amp, gate_mode='abs', gate_pow=2.0, floor=0.0):
    d = b2 - b1
    e = c + wc * d + (1.0 - wc) * (b2 - c)
    if T <= 0:
        w = np.ones((c.shape[0], c.shape[1], 1), np.float32)
    elif gate_mode == 'abs':
        a = np.maximum(amp - floor, 0.0)
        w = 1.0 / (1.0 + (a / T) ** gate_pow)
        w = w[:, :, None]
    elif gate_mode == 'quad':
        a = np.maximum(amp - floor, 0.0)
        w = 1.0 - np.minimum((a / T) ** 2, 1.0)
        w = w[:, :, None]
    else:
        raise ValueError(gate_mode)
    return np.clip(c + w * (e - c), 0, 255)


def proto(rgba, s1, s2, wc, T, gate_mode='abs', proxy='c2', gate_blur=0.0,
          gate_pow=2.0, floor=0.0, half=0):
    """跑一遍双尺度带通。输入 uint8 RGBA，返回 float32 RGB (0..255)。

    half=1 时按 C++ 的落地形态走：B1/B2/振幅都在半分辨率上算，合成时
    双线性放大回全分辨率（C/mask/protect 仍用全分辨率）。
    """
    if half:
        hh = (H + 1) // 2
        hw = (W + 1) // 2
        sm = rgba[:hh * 2, :hw * 2, :3].astype(np.float32)
        sm = sm.reshape(hh, 2, hw, 2, 3).mean(axis=(1, 3))
        c, b1, b2 = split(sm, s1 * 0.5, s2 * 0.5)
        amp = amp_proxy(c, b1, b2, proxy)
        if gate_blur > 0:
            amp = gblur(amp, gate_blur * 0.5)
        up = lambda a: cv2.resize(a, (W, H), interpolation=cv2.INTER_LINEAR)
        b1f = np.dstack([up(b1[:, :, k]) for k in range(3)])
        b2f = np.dstack([up(b2[:, :, k]) for k in range(3)])
        ampf = up(amp)
        cf = rgba[:, :, :3].astype(np.float32)
        return compose(cf, b1f, b2f, wc, T, ampf, gate_mode, gate_pow, floor)

    c, b1, b2 = split(rgba, s1, s2)
    amp = amp_proxy(c, b1, b2, proxy)
    if gate_blur > 0:
        amp = gblur(amp, gate_blur)
    return compose(c, b1, b2, wc, T, amp, gate_mode, gate_pow, floor)


# --------------------------------------------------------------------------
# 评估
# --------------------------------------------------------------------------
def metrics(out, src, gold, reg):
    """注意：RMSE 是 out 与 gold 的残差，不是改动量。改动量单独给。"""
    ds = (out - src)[reg]
    dg = (gold - src)[reg]
    res = (out - gold)[reg]
    rmse = float(np.sqrt((res * res).mean()))
    chg = float(np.abs(ds).mean())
    gchg = float(np.abs(dg).mean())
    a = ds - ds.mean()
    b = dg - dg.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    corr = float((a * b).sum() / den) if den > 0 else float('nan')
    return rmse, chg, gchg, corr


def grad_bands(src_gray, reg):
    gx = cv2.Sobel(src_gray, cv2.CV_32F, 1, 0, ksize=3) * 0.125
    gy = cv2.Sobel(src_gray, cv2.CV_32F, 0, 1, ksize=3) * 0.125
    mag = np.sqrt(gx * gx + gy * gy)
    return mag


def grating_table(src, reg, fn, name):
    """fn(uint8 RGBA) -> float32 RGB；返回 7×4 增益表。"""
    base = fn(src)
    tab = {}
    for P in PERIODS:
        cos_b, sin_b = basis(P)
        row = []
        for A in AMPS:
            g = add_grating(src, P, A)
            dout = (fn(g) - base)[:, :, 1]
            row.append(complex_gain(dout, cos_b, sin_b, reg) / A)
        tab[P] = row
    return tab


def print_table(tab, title):
    print(title)
    print('%-8s' % '周期px', end='')
    for A in AMPS:
        print('  A=%-6g' % A, end='')
    print()
    print('-' * (10 + 9 * len(AMPS)))
    for P in PERIODS:
        print('%-8d' % P, end='')
        for v in tab[P]:
            print('  %8.3f' % v, end='')
        print()
    print()


def compare(tab):
    """与 SDK 表逐格比，报 MAE + 三条结构判据。"""
    err = []
    for P in PERIODS:
        for i in range(len(AMPS)):
            err.append(abs(tab[P][i] - SDK[P][i]))
    print('与 SDK 表 MAE = %.4f   max = %.4f' % (np.mean(err), np.max(err)))
    print()
    # 判据 1：A=2 时主凹陷位置
    col = [tab[P][0] for P in PERIODS]
    trough = PERIODS[int(np.argmin(col))]
    print('判据1 主凹陷位置      : %2d px  (SDK 24)   %s'
          % (trough, 'PASS' if trough == 24 else 'FAIL'))
    print('判据2 A=2  P=24 增益  : %.3f   (SDK 0.201) %s'
          % (tab[24][0], 'PASS' if abs(tab[24][0] - 0.201) <= 0.04 else 'FAIL'))
    print('判据3 A=16 P=8  增益  : %.3f   (SDK 0.579) %s'
          % (tab[8][3], 'PASS' if abs(tab[8][3] - 0.579) <= 0.08 else 'FAIL'))
    # 附带：振幅依赖强度
    amp_dep = tab[8][3] / max(tab[8][0], 1e-6)
    print('附   振幅依赖 P=8     : %.2fx (SDK 2.00x)  %s'
          % (amp_dep, 'PASS' if amp_dep >= 1.5 else 'FAIL'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--s1', type=float, default=3.9)
    ap.add_argument('--s2', type=float, default=8.6)
    ap.add_argument('--wc', type=float, default=0.3)
    ap.add_argument('--T', type=float, default=12.0)
    ap.add_argument('--gate-mode', default='abs', choices=['abs', 'quad'])
    ap.add_argument('--proxy', default='c2', choices=['d', 'c1', 'c2'])
    ap.add_argument('--gate-blur', type=float, default=4.0)
    ap.add_argument('--gate-pow', type=float, default=2.0)
    ap.add_argument('--floor', type=float, default=0.0)
    ap.add_argument('--box', type=int, default=0,
                    help='>0 时用 N 次盒式近似高斯（C++ 落地形态）')
    ap.add_argument('--grid', action='store_true',
                    help='二维扫 (幂次 × T)，只看像素指标，快')
    ap.add_argument('--fit', action='store_true',
                    help='扫 T，同时报像素指标和两个关键格子的增益')
    ap.add_argument('--no-grating', action='store_true')
    ap.add_argument('--dump', action='store_true')
    args = ap.parse_args()
    global BOX_N
    BOX_N = args.box

    src = load_raw(os.path.join(WORK, '%s_in.raw' % TAG))
    gold = load_raw(os.path.join(WORK, '%s_gold.raw' % TAG))[:, :, :3].astype(np.float32)
    reg3 = erode(upscale_mask(read_mask(
        os.path.join(WORK, '%s_fuai.mask' % TAG)), W, H), 8)
    src_f = src[:, :, :3].astype(np.float32)

    print('区域：掩码内缩 8px，%d px' % int(reg3.sum()))
    print('参数：s1=%.2f s2=%.2f wc=%.2f proxy=%s gate=%s/%s'
          % (args.s1, args.s2, args.wc, args.proxy, args.gate_mode,
             args.gate_blur))
    print()

    def fn(a, s1=None, s2=None, T=None, proxy=None, pw=None):
        return proto(a, args.s1 if s1 is None else s1,
                     args.s2 if s2 is None else s2,
                     args.wc, args.T if T is None else T,
                     args.gate_mode,
                     args.proxy if proxy is None else proxy,
                     args.gate_blur,
                     args.gate_pow if pw is None else pw,
                     args.floor)

    def gain_at(a_base, a_gr, P, A, **kw):
        """只测一个格子：gain = |g|/A，用 base 差分消掉底图。"""
        cb, sb = basis(P)
        d = (fn(a_gr, **kw) - a_base)[:, :, 1]
        return complex_gain(d, cb, sb, reg3) / A

    # ---------------- 像素级 ----------------
    out = fn(src)
    rmse, chg, gchg, corr = metrics(out, src_f, gold, reg3)
    print('像素（掩码内缩 8px）：RMSE %.3f   改动量 %.3f（SDK %.3f）  空间相关 %.3f'
          % (rmse, chg, gchg, corr))
    out0 = fn(src, T=0.0)
    r0, c0, _, k0 = metrics(out0, src_f, gold, reg3)
    print('  无门控（纯 LTI）    ：RMSE %.3f   改动量 %.3f  空间相关 %.3f'
          % (r0, c0, k0))
    print()

    if args.dump:
        for nm, arr in (('proto', out), ('proto_lti', out0)):
            Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(
                os.path.join(WORK, 'p_%s.png' % nm))
        d = np.abs(out - gold).max(axis=2)
        Image.fromarray(np.clip(d * 8, 0, 255).astype(np.uint8)).save(
            os.path.join(WORK, 'p_diff.png'))
        Image.fromarray(np.clip(np.abs(out - src_f).max(axis=2) * 12, 0,
                                255).astype(np.uint8)).save(
            os.path.join(WORK, 'p_chg_core.png'))
        Image.fromarray(np.clip(np.abs(gold - src_f).max(axis=2) * 12, 0,
                                255).astype(np.uint8)).save(
            os.path.join(WORK, 'p_chg_sdk.png'))
        print('已导出 p_proto.png / p_diff.png / p_chg_*.png')
        print()

    # ---------------- 二维扫 (幂次 × T)，只算像素指标 ----------------
    if args.grid:
        c, b1, b2 = split(src, args.s1, args.s2)
        amp = amp_proxy(c, b1, b2, args.proxy)
        if args.gate_blur > 0:
            amp = gblur(amp, args.gate_blur)
        print('=== 幂次 × T（proxy=%s, gate_blur=%.1f, floor=%.1f）'
              % (args.proxy, args.gate_blur, args.floor))
        print('每格 "RMSE/改动量"；目标 RMSE<2.0 且 改动量≈2.74')
        Ts = (8, 10, 12, 14, 16, 18, 22)
        print('%-6s' % 'p\\T', end='')
        for T in Ts:
            print('   T=%-4d' % T, end='')
        print()
        for p in (2.0, 3.0, 4.0, 6.0, 8.0):
            print('%-6.1f' % p, end='')
            for T in Ts:
                o = compose(c, b1, b2, args.wc, T, amp, args.gate_mode,
                            p, args.floor)
                r, ch, _, _ = metrics(o, src_f, gold, reg3)
                print('  %5.2f/%5.2f' % (r, ch), end='')
            print()
        print()
        return 0

    # ---------------- 扫 T ----------------
    if args.fit:
        print('=== 扫 T（proxy=%s）：像素指标 + 关键格子增益 ===' % args.proxy)
        print('%6s %8s %8s %8s | %8s %8s | %8s %8s'
              % ('T', 'RMSE', '改动量', '相关',
                 'A2/P24', 'A16/P24', 'A2/P8', 'A16/P8'))
        print('-' * 78)
        base_src = fn(src)
        for T in (0.0, 6.0, 8.0, 10.0, 12.0, 15.0, 18.0, 22.0, 26.0):
            o = fn(src, T=T)
            r, ch, _, cr = metrics(o, src_f, gold, reg3)
            g24_2 = gain_at(base_src, add_grating(src, 24, 2.0), 24, 2.0, T=T)
            g24_16 = gain_at(base_src, add_grating(src, 24, 16.0), 24, 16.0, T=T)
            g8_2 = gain_at(base_src, add_grating(src, 8, 2.0), 8, 2.0, T=T)
            g8_16 = gain_at(base_src, add_grating(src, 8, 16.0), 8, 16.0, T=T)
            print('%6.1f %8.3f %8.3f %8.3f | %8.3f %8.3f | %8.3f %8.3f'
                  % (T, r, ch, cr, g24_2, g24_16, g8_2, g8_16))
        print('目标：改动量 2.74，A2/P24 0.201，A16/P24 0.544，'
              'A2/P8 0.289，A16/P8 0.579')
        print()
        return 0

    if args.no_grating:
        return 0

    tab = grating_table(src, reg3, fn, 'proto')
    print_table(tab, '=== 原型 ===')
    compare(tab)
    print()
    print_table({P: list(SDK[P]) for P in PERIODS}, '=== SDK（基准）===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
