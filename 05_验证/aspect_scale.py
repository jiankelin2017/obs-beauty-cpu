# -*- coding: utf-8 -*-
"""aspect_scale.py —— 测核尺度随画幅怎么变（验证「UV 固定」是否真的成立）。

为什么需要
----------
C23 §3.2 / §9.1 反复强调：SDK 的核是 **UV 半轴固定**，所以核的像素尺度
必须 ∝ 画幅宽度（实测 SDK σx ∝ W^0.98）。

但我们的实现是：

    w1 = bandBoxW(ww, 5/960, 3)   // ww = 处理宽度
    r1 = (w1 - 1) / 2

`bandBoxW` 把结果**取整到奇数**。于是：

    画幅         ww    5/960*ww    取整后宽度   r
    1920×1080   960     5.00          5         2
    1280×720    640     3.33          3         1     ← 理论 3.33，被压到 3
    1080×1920   540     2.81          3         1
    2560×1440  1280     6.67          7         3     ← 被抬到 7

r/ww 在 0.00156 ~ 0.00234 之间波动（±25%）。**取整把「UV 固定」量子化了**，
换画幅时核尺度不再严格 ∝ 宽度。

本脚本用光栅法实测：主凹陷的**像素周期**是否 ∝ 画幅宽度。
UV 固定的话，720p 的主凹陷应落在 24×(720/1080)=16px；若落在 24px 说明
退化成了「像素固定」（那正是 C23 §10.2 判盒式在真机上过磨 53% 的原因）。

输入：真机帧 cam_in.raw 几何缩放到各画幅（人脸可被 DLL 检出，掩码随之缩放）。

用法
----
    python aspect_scale.py --band 1 --sizes 1920x1080,1280x720
"""
import argparse
import ctypes
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import real_grating as rg   # noqa: E402

WORK = rg.WORK
TAG = rg.TAG
SRC_W, SRC_H = rg.W, rg.H

PERIODS = (8, 12, 16, 20, 24, 32, 48, 64)
AMPS = (2.0, 8.0)


def run_core_at(d, raw_in, raw_out, w, h, warm=3):
    """BeautyCoreRun 支持任意 w/h；real_grating.run_core 写死了 1920×1080。"""
    msg = ctypes.create_string_buffer(512)
    rc = 0
    for _ in range(warm):
        rc = d.BeautyCoreRun(raw_in.encode(), raw_out.encode(), w, h,
                             100.0, 0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))


def resize_rgba(src, w1, h1):
    im = Image.fromarray(np.ascontiguousarray(src[:, :, :3]))
    im = im.resize((w1, h1), Image.LANCZOS)
    return np.dstack([np.asarray(im, np.uint8),
                      np.full((h1, w1, 1), 255, np.uint8)])


def add_grating_w(arr, period, amp, w, h, axis='x'):
    """axis='x' 测横向核宽，'y' 测纵向核宽 —— 各向异性只能靠比较两者看出来。"""
    out = arr.copy()
    n = w if axis == 'x' else h
    t = np.arange(n, dtype=np.float32)
    g = amp * np.cos(2.0 * np.pi * t / float(period))
    if axis == 'x':
        v = out[:, :, 1].astype(np.float32) + g[None, :]
    else:
        v = out[:, :, 1].astype(np.float32) + g[:, None]
    out[:, :, 1] = np.clip(v, 0, 255).astype(np.uint8)
    return out


def basis_w(period, w, h, axis='x'):
    n = w if axis == 'x' else h
    t = np.arange(n, dtype=np.float32)
    ph = 2.0 * np.pi * t / float(period)
    c = np.cos(ph)
    s = np.sin(ph)
    if axis == 'x':
        c, s = c[None, :], s[None, :]
    else:
        c, s = c[:, None], s[:, None]
    return np.broadcast_to(c, (h, w)), np.broadcast_to(s, (h, w))


def complex_gain(d, cos_b, sin_b, reg):
    c, s, v = cos_b[reg], sin_b[reg], d[reg]
    dc = float((c * c).sum())
    ds = float((s * s).sum())
    gc = float((v * c).sum()) / dc if dc > 0 else 0.0
    gs = float((v * s).sum()) / ds if ds > 0 else 0.0
    return abs(complex(gc, gs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='surface3')
    ap.add_argument('--band', type=int, default=1)
    ap.add_argument('--bt', type=float, default=14.0)
    ap.add_argument('--sizes', default='1920x1080,1280x720')
    args = ap.parse_args()

    os.environ['BEAUTY_SMOOTH_MODEL'] = args.model
    os.environ['BEAUTY_S3_TAP25'] = '0'
    os.environ['BEAUTY_S3_HALF'] = '1'
    os.environ['BEAUTY_S3_BAND'] = str(args.band)
    os.environ['BEAUTY_S3_BT'] = str(args.bt)

    sizes = []
    for s in args.sizes.split(','):
        w, h = s.strip().lower().split('x')
        sizes.append((int(w), int(h)))

    d = rg.load_core()
    src0 = rg.load_raw(os.path.join(WORK, '%s_in.raw' % TAG))
    mask0 = rg.read_mask(os.path.join(WORK, '%s_fuai.mask' % TAG))

    tmp_in = os.path.join(WORK, '_as_in.raw')
    tmp_out = os.path.join(WORK, '_as_out.raw')
    base_p = os.path.join(WORK, '_as_base.raw')

    print('band=%d BT=%g   每个画幅：%d 周期 × %d 振幅'
          % (args.band, args.bt, len(PERIODS), len(AMPS)))
    print()
    summary = {}

    for (w, h) in sizes:
        src = src0 if (w, h) == (SRC_W, SRC_H) else resize_rgba(src0, w, h)
        mask = rg.upscale_mask(mask0, w, h)
        reg = rg.erode(mask, 8)
        if reg.sum() < 5000:
            print('%dx%d 跳过：掩码内缩后只有 %d px（DLL 未检出人脸）'
                  % (w, h, int(reg.sum())))
            continue

        src.tofile(tmp_in)
        run_core_at(d, tmp_in, base_p, w, h)
        base = rg.load_raw(base_p, w, h).astype(np.float32)

        # 自检：改动量必须非 0，否则说明掩码是空的、测的是恒等映射
        chg = float(np.abs(base[:, :, 1] - src[:, :, 1].astype(np.float32))[reg].mean())

        print('--- %dx%d  掩码 %d px  改动量 %.3f ---' % (w, h, int(reg.sum()), chg))
        for axis in ('x', 'y'):
            print('  [%s 向光栅]' % axis)
            print('  %-8s' % '周期px', end='')
            for A in AMPS:
                print('  A=%-6g' % A, end='')
            print()
            for P in PERIODS:
                cos_b, sin_b = basis_w(P, w, h, axis)
                print('  %-8d' % P, end='')
                for A in AMPS:
                    g = add_grating_w(src, P, A, w, h, axis)
                    g.tofile(tmp_in)
                    run_core_at(d, tmp_in, tmp_out, w, h)
                    dout = (rg.load_raw(tmp_out, w, h).astype(np.float32) - base)[:, :, 1]
                    print('  %8.3f' % (complex_gain(dout, cos_b, sin_b, reg) / A), end='')
                print()
        print()
        summary[(w, h)] = (reg.sum(), chg)

    print('=== 画幅覆盖情况 ===')
    for (w, h), (n, chg) in summary.items():
        print('  %4dx%-4d  r/ww 理论 = %.2fpx 宽（取整前 %s）  掩码 %d  改动量 %.3f'
              % (w, h, 5.0 / 960.0 * (w / 2.0),
                 '%.2f' % (5.0 / 960.0 * (w / 2.0)), n, chg))
    return 0


if __name__ == '__main__':
    sys.exit(main())
