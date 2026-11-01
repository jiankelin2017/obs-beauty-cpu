# -*- coding: utf-8 -*-
"""core_grating.py —— 用**同一把尺子**量自研引擎的等效核宽。

为什么必须做这件事
------------------
`s3_pixel_eval.py` 显示 25 tap 的幅度整体偏大 1.33 倍，但"偏大"可能来自
核太宽、也可能来自缺第一级 `dis` 门控。要分开这两者，只能拿光栅法直接量
自研引擎的 σ，和 SDK 的 σ 并排比 —— 这是**测量**，不是拿金标去拟合参数。

判据（C23 §8.4 反拟合纪律）：如果自研 σ 明显大于 SDK σ，那是核抄宽了，
改的是"抄错了"；如果 σ 对得上而幅度还是大，那问题在混合/门控，不许动核。

用法
----
    python core_grating.py                    # 默认 640x394, blur=100, tap25=1
    python core_grating.py --tap25 0          # 盒式基线
    python core_grating.py --half 0
"""
import argparse
import ctypes
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from synth_grating import (boxsum, make_basis, add_grating, complex_gain,  # noqa: E402
                           ACT_ERODE, PERIODS)
import grating_fit as GF  # noqa: E402

DLL = os.path.join(HERE, 'beauty_core_test.dll')
SRC = os.path.join(HERE, 'goldens', 'src')
OUT = os.path.join(HERE, 'goldens', 'grating')

W, H = 640, 394
AMP = 16.0


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
    return d


def setup(d):
    d.BeautyCoreSetTone(0.0, 0.0)
    d.BeautyCoreSetDetail(0.0, 0.0)
    d.BeautyCoreSetClarityPanel(0.0)
    for i in range(5):
        d.BeautyCoreSetRegion(i, 0.0)


def run(d, arr, tag, blur):
    ri = os.path.join(OUT, '_cg_in.raw')
    ro = os.path.join(OUT, '_cg_%s.raw' % tag)
    arr.tofile(ri)
    msg = ctypes.create_string_buffer(512)
    rc = 0
    for _ in range(3):      # 预热：首帧含模型加载
        rc = d.BeautyCoreRun(ri.encode(), ro.encode(), W, H, float(blur),
                             0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
    a = np.fromfile(ro, np.uint8)
    return a.reshape((H, W, 4)), msg.value.decode('utf-8', 'replace')


def load_src(name):
    p = os.path.join(SRC, name + '.raw')
    a = np.fromfile(p, np.uint8)
    return a.reshape((H, W, 4)).copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scene', default='crop_c')
    ap.add_argument('--blur', type=int, default=100)
    ap.add_argument('--tap25', type=int, default=1)
    ap.add_argument('--half', type=int, default=1)
    ap.add_argument('--amp', type=float, default=AMP)
    ap.add_argument('--yf1', type=float, default=None)
    ap.add_argument('--yf2', type=float, default=None)
    ap.add_argument('--sx', type=float, default=None)
    ap.add_argument('--sy', type=float, default=None)
    args = ap.parse_args()

    os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
    os.environ['BEAUTY_S3_TAP25'] = str(args.tap25)
    os.environ['BEAUTY_S3_HALF'] = str(args.half)
    if args.yf1 is not None:
        os.environ['BEAUTY_S3_YF1'] = repr(args.yf1)
    if args.yf2 is not None:
        os.environ['BEAUTY_S3_YF2'] = repr(args.yf2)
    if args.sx is not None:
        os.environ['BEAUTY_S3_SX'] = repr(args.sx)
    if args.sy is not None:
        os.environ['BEAUTY_S3_SY'] = repr(args.sy)

    os.makedirs(OUT, exist_ok=True)
    d = load_dll()
    setup(d)

    base = load_src(args.scene)
    out0, _ = run(d, base, 'z', 0)
    out1, msg = run(d, base, 'base', args.blur)
    print('core: %s' % msg.strip())

    dd = np.abs(out1[:, :, :3].astype(np.int16)
                - out0[:, :, :3].astype(np.int16)).max(axis=2)
    act = dd >= 1
    er = boxsum(act, ACT_ERODE) == (2 * ACT_ERODE + 1) ** 2
    print('活跃区 %d px（act %d）' % (int(er.sum()), int(act.sum())))
    if er.sum() < 500:
        print('活跃区太小，跳过')
        return 1

    # 空探针复现性
    again, _ = run(d, base, 'null', args.blur)
    null_max = int(np.abs(again[:, :, 1].astype(np.int16)
                          - out1[:, :, 1].astype(np.int16)).max())
    print('空探针(A=0)：max|diff|=%d' % null_max)

    ys, xs = np.nonzero(er)
    ext_x = int(xs.max() - xs.min() + 1)
    ext_y = int(ys.max() - ys.min() + 1)
    pmax = int(min(ext_x, ext_y) / 2.5)
    periods = [p for p in PERIODS if p <= pmax] or [8, 10, 12, 16]
    print('bbox %dx%d  周期 %s' % (ext_x, ext_y, periods))

    rows = []
    for orient in ('x', 'y'):
        for p in periods:
            cb, sb = make_basis(W, H, orient, p)
            probe = add_grating(base, cb, args.amp)
            outp, _ = run(d, probe, '%s%02d' % (orient, p), args.blur)
            dout = outp[:, :, 1].astype(np.float64) \
                - out1[:, :, 1].astype(np.float64)
            g, rms = complex_gain(dout, cb, sb, er)
            rows.append({'orient': orient, 'period': p, 'f_px': 1.0 / p,
                         'mag': abs(g) / args.amp,
                         'phase_deg': float(np.degrees(np.angle(g))),
                         'rms': rms})
            print('  %s P=%2d f=%.4f  |H|=%6.4f  rms=%.3f'
                  % (orient, p, 1.0 / p, abs(g) / args.amp, rms))

    print()
    res = {}
    for o in ('x', 'y'):
        rs = sorted([r for r in rows if r['orient'] == o],
                    key=lambda r: r['f_px'])
        fit = GF.fit_curve([r['f_px'] for r in rs], [r['mag'] for r in rs])
        res[o] = fit
        print('%s: σ=%.2f px  a=%.3f b=%.3f  R²=%.3f'
              % (o, fit['sigma_px'], fit['a'], fit['b'], fit['r2']))
    print('各向异性 σx/σy = %.3f' % (res['x']['sigma_px'] / res['y']['sigma_px']))

    jf = os.path.join(OUT, 'core_grating_t%d_h%d.json' % (args.tap25, args.half))
    with open(jf, 'w', encoding='utf-8') as f:
        json.dump({'rows': rows, 'fit': {k: {kk: float(vv) for kk, vv in v.items()}
                                         for k, v in res.items()},
                   'null_max': null_max, 'active_px': int(er.sum())},
                  f, ensure_ascii=False, indent=2)
    print('-> %s' % jf)
    return 0


if __name__ == '__main__':
    sys.exit(main())
