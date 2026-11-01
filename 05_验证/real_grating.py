# -*- coding: utf-8 -*-
"""real_grating.py —— 在真机帧上测 SDK 与自研的「振幅-频率」响应。

为什么需要
----------
`real_frame_eval.py` 的频谱对比只能给出「平均保留率」，那是把整幅图的统计
混在一起的数。而磨皮是**非线性**的（值域权重 / dis 门控都依赖局部对比度），
所以同一个空间频率，低振幅纹理和高振幅纹理会得到不同的增益。

线性模型（双高斯 / 三高斯）在真机帧上已经证伪：
    谱形状 MAE 0.0194 拟合得很好，但改动量只有 0.915，而 SDK 是 2.704。
说明必须测「增益随振幅怎么变」，才能刻画这个非线性。

方法：差分 + 复数投影
--------------------
对每个 (振幅 A, 周期 P)：

    1. 跑一次基准帧（不加光栅）        -> out0
    2. 跑一次加了余弦光栅的帧          -> out1
    3. dOut = out1 - out0             -> 底图纹理完全抵消，只剩滤波器对光栅的响应
    4. 把 dOut 投影到 cos/sin 基上      -> 复数增益 g
    5. |H| = |g| / A

这样测出来的是「该振幅下该频率的等效增益」，不受脸部纹理干扰。

关键约定
--------
- 光栅加在**绿通道**（磨皮的值域权重只测绿通道，放绿通道信号最强）
- 振幅用灰阶（0-255）表示，A=4 就是 ±4 灰阶
- 周期用**全分辨率像素**表示

用法
----
    python real_grating.py --model sdk
    python real_grating.py --model surface3 --tap25 1
"""
import argparse
import ctypes
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CORE_DLL = os.path.join(HERE, 'beauty_core_test.dll')
GOLD_DLL = os.path.join(HERE, 'ref_golden.dll')
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')
WORK = os.path.join(HERE, 'goldens', 'real')

W, H = 1920, 1080
TAG = 'cam'
WARMUP = 6
PERIODS = (8, 12, 16, 24, 32, 48, 64)
AMPS = (2.0, 4.0, 8.0, 16.0)


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
    """在绿通道加余弦光栅，横向。返回新数组（不修改原数组）。"""
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


# ---------------------------------------------------------------------------
def load_gold():
    d = ctypes.WinDLL(GOLD_DLL)
    d.RefGoldenRun.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(ctypes.c_double), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    return d


def run_gold(d, raw_in, raw_out, blur=100.0):
    p = (ctypes.c_double * 11)()
    p[0] = blur
    msg = ctypes.create_string_buffer(512)
    return d.RefGoldenRun(ENGINE_DIR.encode('utf-8'), raw_in.encode('utf-8'),
                           raw_out.encode('utf-8'), W, H, p, 11, 1, 1, 0, 1,
                           msg, 512)


def load_core():
    d = ctypes.WinDLL(CORE_DLL)
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
    d.BeautyCoreSetTone(0.0, 0.0)
    d.BeautyCoreSetDetail(0.0, 0.0)
    d.BeautyCoreSetClarityPanel(0.0)
    for i in range(5):
        d.BeautyCoreSetRegion(i, 0.0)
    return d


def run_core(d, raw_in, raw_out):
    msg = ctypes.create_string_buffer(512)
    rc = 0
    for _ in range(3):
        rc = d.BeautyCoreRun(raw_in.encode(), raw_out.encode(), W, H,
                             100.0, 0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='sdk', choices=['sdk', 'surface3'])
    ap.add_argument('--tap25', type=int, default=0)
    ap.add_argument('--band', type=int, default=0)
    ap.add_argument('--bt', type=float, default=14.0)
    ap.add_argument('--half', type=int, default=1)
    args = ap.parse_args()

    os.environ['BEAUTY_SMOOTH_MODEL'] = args.model
    os.environ['BEAUTY_S3_TAP25'] = str(args.tap25)
    os.environ['BEAUTY_S3_HALF'] = str(args.half)
    os.environ['BEAUTY_S3_BAND'] = str(args.band)
    os.environ['BEAUTY_S3_BT'] = str(args.bt)

    src = load_raw(os.path.join(WORK, '%s_in.raw' % TAG))
    reg = erode(upscale_mask(read_mask(
        os.path.join(WORK, '%s_fuai.mask' % TAG)), W, H), 8)
    tmp_in = os.path.join(WORK, '_g_in.raw')
    tmp_out = os.path.join(WORK, '_g_out.raw')
    base_p = os.path.join(WORK, '_g_base.raw')

    # 基准帧（不加光栅）
    src.tofile(tmp_in)
    if args.model == 'sdk':
        d = load_gold()
        for _ in range(WARMUP):
            run_gold(d, tmp_in, tmp_out, 0.0)
        run_gold(d, tmp_in, base_p)
        runner = lambda a: (a.tofile(tmp_in), run_gold(d, tmp_in, tmp_out))
    else:
        d = load_core()
        run_core(d, tmp_in, base_p)
        runner = lambda a: (a.tofile(tmp_in), run_core(d, tmp_in, tmp_out))
    base = load_raw(base_p).astype(np.float32)

    name = 'SDK bt1' if args.model == 'sdk' else (
        'core band' if args.band else ('core 25tap' if args.tap25 else 'core box'))
    print('模型：%s   区域：掩码内缩 8px，%d px' % (name, int(reg.sum())))
    print()
    print('%-8s' % '周期px', end='')
    for A in AMPS:
        print('  A=%-6g' % A, end='')
    print('   (等效增益 |H|，1.0 = 完全不动)')
    print('-' * (10 + 9 * len(AMPS)))
    for P in PERIODS:
        cos_b, sin_b = basis(P)
        print('%-8d' % P, end='')
        for A in AMPS:
            g = add_grating(src, P, A)
            runner(g)
            dout = (load_raw(tmp_out).astype(np.float32) - base)[:, :, 1]
            h = complex_gain(dout, cos_b, sin_b, reg) / A
            print('  %8.3f' % h, end='')
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
