# -*- coding: utf-8 -*-
"""s3_perf.py —— 25 tap 路径的性能测量（第 2 批-A 的隐含前置）。

为什么先测性能再写 #8
--------------------
25 tap × 3 通道 × 两趟 = 每像素 150 次双线性采样，比可分离盒式重两个数量级。
#8（第一级 `dis` 门控 + preEnlighten）是在这之上**再加一级**，所以如果 25 tap
本身已经超预算，先写 #8 等于白写 —— 得先定优化策略。

**一个配置一个进程**：`g_cfg` 只在 `ensureReady` 里读一次环境变量，同进程内
换不了 tap25/half。所以本脚本只测一组，多组要在外面循环（见 run_perf_matrix.bat）。

测量口径
--------
预热 5 帧，取 N 帧中位数（首帧含模型加载，不能用）。
参考预算：滤镜跑在采集线程上，1080p60 每帧总预算 16.7ms，磨皮应 ≤6ms
（3.1.13 的 1080p 基线 5.73ms）。

用法
----
    python s3_perf.py --tap25 1 --half 1
    python s3_perf.py --tap25 1 --half 1 --single 1
"""
import argparse
import ctypes
import os
import statistics
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
TMP = os.path.join(HERE, 'goldens', 'grating')
SRC_PNG = os.path.join(HERE, 'crop_c.png')
if not os.path.exists(SRC_PNG):
    SRC_PNG = os.path.join(HERE, 'goldens', 'src', 'crop_c.png')


def load_dll():
    if not os.path.exists(DLL):
        print('缺 %s，先跑 build_core_test.bat' % DLL)
        sys.exit(2)
    d = ctypes.WinDLL(DLL)
    d.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_double, ctypes.c_int,
                                ctypes.c_float, ctypes.c_float,
                                ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    d.BeautyCoreRun.restype = ctypes.c_int
    for n in ('BeautyCoreSetTone', 'BeautyCoreSetDetail'):
        getattr(d, n).argtypes = [ctypes.c_double, ctypes.c_double]
        getattr(d, n).restype = None
    d.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    d.BeautyCoreSetClarityPanel.restype = None
    d.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]
    d.BeautyCoreSetRegion.restype = None
    d.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]
    d.BeautyCoreSetPerf.restype = None
    return d


def letterbox(path, w, h):
    im = Image.open(path)
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    iw, ih = im.size
    s = min(float(w) / iw, float(h) / ih)
    nw, nh = max(1, int(round(iw * s))), max(1, int(round(ih * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    cv = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    cv.paste(im, ((w - nw) // 2, (h - nh) // 2))
    return np.asarray(cv, dtype=np.uint8)


def bench(d, raw_in, raw_out, w, h, reps, blur=100.0):
    msg = ctypes.create_string_buffer(512)
    for _ in range(5):
        d.BeautyCoreRun(raw_in.encode(), raw_out.encode(), w, h, blur,
                        0, 0.0, 0.0, 1, msg, 512)
    ts, txt = [], ''
    for _ in range(reps):
        rc = d.BeautyCoreRun(raw_in.encode(), raw_out.encode(), w, h, blur,
                             0, 0.0, 0.0, 1, msg, 512)
        if rc != 0:
            raise RuntimeError('rc=%d' % rc)
        txt = msg.value.decode('utf-8', 'replace')
        for tok in txt.split():
            if tok.startswith('ms='):
                ts.append(float(tok[3:]))
                break
    return (statistics.median(ts) if ts else float('nan')), ts, txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tap25', type=int, default=1)
    ap.add_argument('--band', type=int, default=0)
    ap.add_argument('--bt', type=float, default=14.0)
    ap.add_argument('--half', type=int, default=1)
    ap.add_argument('--single', type=int, default=0)
    ap.add_argument('--sizes', default='640x394,1280x720,1920x1080')
    ap.add_argument('--reps', type=int, default=20)
    ap.add_argument('--blur', type=float, default=100.0)
    ap.add_argument('--active', type=int, default=1,
                    help='额外跑一次 blur=0 减出纯磨皮开销，并统计改动区')
    args = ap.parse_args()

    os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
    os.environ['BEAUTY_S3_TAP25'] = str(args.tap25)
    os.environ['BEAUTY_S3_HALF'] = str(args.half)
    os.environ['BEAUTY_S3_BAND'] = str(args.band)
    os.environ['BEAUTY_S3_BT'] = str(args.bt)

    os.makedirs(TMP, exist_ok=True)
    d = load_dll()
    d.BeautyCoreSetTone(0.0, 0.0)
    d.BeautyCoreSetDetail(0.0, 0.0)
    d.BeautyCoreSetClarityPanel(0.0)
    for i in range(5):
        d.BeautyCoreSetRegion(i, 0.0)
    d.BeautyCoreSetPerf(1 if args.single else 0, 0)

    tag = 'band=%d bt=%g tap25=%d half=%d %s blur=%g' % (
        args.band, args.bt, args.tap25, args.half,
        '单线程' if args.single else '默认线程', args.blur)
    print('配置：%s' % tag)
    print('%-11s %9s %9s %9s %9s %9s %9s'
          % ('画幅', '全链路', 'blur0', '纯磨皮', '改动px', '改动bbox', 'ms/Mpx'))
    print('-' * 78)
    for tok in args.sizes.split(','):
        w, h = tok.strip().lower().replace('*', 'x').split('x')
        w, h = int(w), int(h)
        arr = letterbox(SRC_PNG, w, h)
        raw_in = os.path.join(TMP, '_perf_%dx%d.raw' % (w, h))
        arr.tofile(raw_in)
        out1 = os.path.join(TMP, '_perf_out.raw')
        ms, ts, _ = bench(d, raw_in, out1, w, h, args.reps, args.blur)
        if not args.active:
            print('%-11s %9.2f %9s %9s %9s %9s %9s'
                  % ('%dx%d' % (w, h), ms, '-', '-', '-', '-', '-'))
            continue
        out0 = os.path.join(TMP, '_perf_out0.raw')
        ms0, ts0, _ = bench(d, raw_in, out0, w, h, max(5, args.reps // 4), 0.0)
        a = np.fromfile(out1, dtype=np.uint8)
        b = np.fromfile(out0, dtype=np.uint8)
        n = min(a.size, b.size)
        d4 = np.abs(a[:n].astype(np.int16) - b[:n].astype(np.int16)).reshape(-1, 4)
        nz = (d4.max(axis=1) > 0)
        px = int(nz.sum())
        if px:
            m = nz.reshape(h, w)
            ys, xs = np.nonzero(m)
            bbox = (int(xs.max() - xs.min() + 1)) * (int(ys.max() - ys.min() + 1))
        else:
            bbox = 0
        pure = ms - ms0
        per = (pure / (bbox / 1e6)) if bbox else float('nan')
        print('%-11s %9.2f %9.2f %9.2f %9d %9d %9.3f'
              % ('%dx%d' % (w, h), ms, ms0, pure, px, bbox, per))
    return 0


if __name__ == '__main__':
    sys.exit(main())
