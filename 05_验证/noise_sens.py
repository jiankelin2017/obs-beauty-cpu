# -*- coding: utf-8 -*-
"""noise_sens.py —— 测「底图噪声水平」对振幅门控的影响（只跑自研侧）。

为什么需要
----------
C23 §12.5 的结构判据 2 不过：噪声级弱纹理（A=2）在 P=24 处，SDK 增益 0.201，
我们 0.382 —— 我们对低幅纹理不够狠。C24 把它留作「已知偏差，不硬凑」。

但用户的实际场景是**低画质摄像头**。低画质 = 传感器噪声大。
而 `gw = 1/(1+(a/T)²)`、`a = blur(|C.g − B2.g|)/T` 是**局部振幅**门控：
底图噪声会抬高 a 的基线，把 gw 压低 → 磨皮被自己关掉。

也就是说，判据 2 在干净图上只是「偏保守」，在噪声图上可能变成「基本不磨」。
本脚本量化这个敏感性，不依赖 SDK 重跑（SDK 那一路开销大、直播中不占资源）。

方法
----
1. 取真机帧 cam_in.raw（有 SDK 掩码，掩码内缩 8px 作测量区）
2. 叠加不同强度的高斯噪声 σ（模拟不同画质的摄像头传感器）
3. 每个 σ 下：跑基准帧 + 跑加光栅帧 → 差分投影 → 等效增益 |H|
4. 看 |H| 随 σ 怎么变

注意：差分法能抵消一阶噪声，所以这里测到的是「噪声改变了门控状态」
这个二阶效应 —— 正是要测的东西。

用法
----
    python noise_sens.py --band 1 --sigmas 0,2,4,8,16,32
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import real_grating as rg   # noqa: E402  复用取证/掩码/增益函数

W, H = rg.W, rg.H
WORK = rg.WORK
TAG = rg.TAG

# 只测关键格子，省时间：P=24 是主凹陷，P=8 是高频端，P=64 是低频端
PERIODS = (8, 12, 16, 24, 32, 48, 64)
AMPS = (2.0, 4.0, 16.0)


def add_sensor_noise(arr, sigma, rng):
    """三通道共享的亮度噪声（传感器噪声主体是亮度噪声，不是色噪）。"""
    if sigma <= 0:
        return arr.copy()
    lum = rng.normal(0.0, sigma, (arr.shape[0], arr.shape[1], 1)).astype(np.float32)
    out = arr[:, :, :3].astype(np.float32) + lum
    dst = arr.copy()
    dst[:, :, :3] = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='surface3')
    ap.add_argument('--band', type=int, default=1)
    ap.add_argument('--bt', type=float, default=14.0)
    ap.add_argument('--half', type=int, default=1)
    ap.add_argument('--sigmas', default='0,2,4,8,16,32')
    ap.add_argument('--seed', type=int, default=12345)
    args = ap.parse_args()

    os.environ['BEAUTY_SMOOTH_MODEL'] = args.model
    os.environ['BEAUTY_S3_TAP25'] = '0'
    os.environ['BEAUTY_S3_HALF'] = str(args.half)
    os.environ['BEAUTY_S3_BAND'] = str(args.band)
    os.environ['BEAUTY_S3_BT'] = str(args.bt)

    sigmas = [float(s) for s in args.sigmas.split(',') if s.strip()]
    d = rg.load_core()

    src = rg.load_raw(os.path.join(WORK, '%s_in.raw' % TAG))
    reg = rg.erode(rg.upscale_mask(
        rg.read_mask(os.path.join(WORK, '%s_fuai.mask' % TAG)), W, H), 8)
    print('模型：%s band=%d BT=%g   区域：掩码内缩 8px，%d px'
          % (args.model, args.band, args.bt, int(reg.sum())))
    print()

    tmp_in = os.path.join(WORK, '_ns_in.raw')
    tmp_out = os.path.join(WORK, '_ns_out.raw')
    base_p = os.path.join(WORK, '_ns_base.raw')
    rng = np.random.default_rng(args.seed)

    rows = {}
    for sigma in sigmas:
        # 同一 σ 下 base 与 grating 用同一噪声实现，差分才能抵消噪声
        noisy = add_sensor_noise(src, sigma, rng)
        noisy.tofile(tmp_in)
        rg.run_core(d, tmp_in, base_p)
        base = rg.load_raw(base_p).astype(np.float32)
        rows[sigma] = {}
        for P in PERIODS:
            cos_b, sin_b = rg.basis(P)
            for A in AMPS:
                g = rg.add_grating(noisy, P, A)
                g.tofile(tmp_in)
                rg.run_core(d, tmp_in, tmp_out)
                dout = (rg.load_raw(tmp_out).astype(np.float32) - base)[:, :, 1]
                rows[sigma][(P, A)] = rg.complex_gain(dout, cos_b, sin_b, reg) / A
        sys.stderr.write('  sigma=%g done\n' % sigma)

    # ---- 输出：每个 (P, A) 一格，行是 σ ----------------------------------
    for A in AMPS:
        print('=== A=%g 灰阶 · 等效增益 |H|（1.0 = 完全不动）===' % A)
        print('%-8s' % 'σ灰阶', end='')
        for P in PERIODS:
            print('  P=%-6d' % P, end='')
        print()
        print('-' * (10 + 9 * len(PERIODS)))
        for sigma in sigmas:
            print('%-8g' % sigma, end='')
            for P in PERIODS:
                print('  %8.3f' % rows[sigma][(P, A)], end='')
            print()
        print()

    # ---- 关键判据：主凹陷格 P=24, A=2 随 σ 的变化 ------------------------
    print('=== 判据 2 格子（P=24, A=2）随噪声漂移 ===')
    print('目标 SDK = 0.201（C23 §11.2，干净底图实测）')
    for sigma in sigmas:
        v = rows[sigma][(24, 2.0)]
        print('  σ=%-4g  |H|=%.3f   相对目标 %+.3f' % (sigma, v, v - 0.201))
    return 0


if __name__ == '__main__':
    sys.exit(main())
