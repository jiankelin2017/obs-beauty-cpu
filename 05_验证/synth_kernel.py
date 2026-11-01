# -*- coding: utf-8 -*-
"""用低幅白噪声探针 + 互相关，直接测出磨皮的**等效二维核** K(x,y)。

为什么这条路最硬
----------------
磨皮在局部是线性的（低幅探针下值域权重 wk≈1），所以

    dOut(x) = (K * dIn)(x)          K = 等效核（含直通分量）

若 dIn 是**白噪声**，则它的自相关是 δ，于是互相关直接就是核：

    R(τ) = <dIn(x) * dOut(x+τ)> = <dIn^2> * K(τ)
    =>  K(τ) = R(τ) / <dIn^2>

不需要假设核是高斯还是 box、不需要建模 L1/L2 两级混合、不需要知道
blending 权重。测到什么形状就是什么形状。

精度：本 SDK 对同一输入**逐字节确定性**（空探针 max|diff|=0），所以唯一
误差是 dOut 的 uint8 量化。取 A=6（均匀分布 ±6），dIn 方差 12，量化噪声
0.29，区域 4.5e4 px：

    K 的估计噪声 ~ 0.29/sqrt(4.5e4) / sqrt(12) ~ 4e-4

而核的旁瓣量级是 1e-2，信噪比 25 倍以上。

为什么 A 只能取 6
-----------------
值域权重 wk = 1 - min(dg^2*yFactor, 1)，yFactor=40，dg 归一化。
均匀 ±6 噪声的相邻色差最大 12 灰阶：

    (12/255)^2 * 40 = 0.089  ->  wk >= 0.91

再大就进入非线性（A=16 时 dg 可达 32，(32/255)^2*40=0.63 -> wk=0.37）。

用法
----
    python synth_kernel.py                        # crop_c, 640x394, bt 0/1/2
    python synth_kernel.py --size 640x394,1920x1080 --bt 1
    python synth_kernel.py --blur 50 --amp 6
"""
import argparse
import ctypes
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'ref_golden.dll')
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')
SRC = os.path.join(HERE, 'goldens', 'src')
OUT = os.path.join(HERE, 'goldens', 'kernel')

P_COUNT = 11
P_BLUR = 0

AMP = 6.0
WARMUP = 3
ACT_MIN = 1
ACT_ERODE = 6
SEED = 20261029
TAU = 20            # 互相关搜索半径（px）。25 tap 环核最大环 ~6px，20 足够


def load_dll():
    if not os.path.exists(DLL):
        print('[kernel] DLL not found: %s (run build_golden.bat first)' % DLL)
        sys.exit(2)
    d = ctypes.WinDLL(DLL)
    d.RefGoldenRun.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(ctypes.c_double), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    return d


class Runner(object):
    def __init__(self, dll, w, h, bt, blur):
        self.dll, self.w, self.h, self.bt, self.blur = dll, w, h, bt, blur
        self.last_msg = ''

    def run(self, arr, tag):
        ri = os.path.join(OUT, '_in_%dx%d.raw' % (self.w, self.h))
        ro = os.path.join(OUT, '_o_%dx%d_%s.raw' % (self.w, self.h, tag))
        arr.tofile(ri)
        panel = (ctypes.c_double * P_COUNT)()
        panel[P_BLUR] = float(self.blur)
        msg = ctypes.create_string_buffer(512)
        rc = self.dll.RefGoldenRun(
            ENGINE_DIR.encode('utf-8'), ri.encode('utf-8'),
            ro.encode('utf-8'), self.w, self.h, panel, P_COUNT,
            self.bt, 1, 0, 1, msg, 512)
        self.last_msg = msg.value.decode('utf-8', 'replace')
        if rc != 0:
            raise RuntimeError('rc=%d %s' % (rc, self.last_msg))
        a = np.fromfile(ro, dtype=np.uint8)
        need = self.w * self.h * 4
        if a.size != need:
            raise RuntimeError('out %d != %d' % (a.size, need))
        return a.reshape((self.h, self.w, 4))


def warmup(dll):
    os.makedirs(OUT, exist_ok=True)
    z = np.zeros((394, 640, 4), dtype=np.uint8)
    z[:, :, 3] = 255
    r = Runner(dll, 640, 394, 1, 0)
    for _ in range(WARMUP):
        r.run(z, 'warm')


def load_src(scene, w, h):
    need = w * h * 4
    p = os.path.join(SRC, scene + '.raw')
    if os.path.exists(p):
        a = np.fromfile(p, dtype=np.uint8)
        if a.size == need:
            return a.reshape((h, w, 4)).copy()
    png = os.path.join(SRC, scene + '.png')
    if not os.path.exists(png):
        png = os.path.join(HERE, scene + '.png')
    if not os.path.exists(png):
        raise IOError('source not found: %s' % scene)
    im = Image.open(png)
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    iw, ih = im.size
    s = min(float(w) / iw, float(h) / ih)
    nw, nh = max(1, int(round(iw * s))), max(1, int(round(ih * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    canvas.paste(im, ((w - nw) // 2, (h - nh) // 2))
    return np.asarray(canvas, dtype=np.uint8).copy()


def boxsum(a, r):
    p = np.pad(a.astype(np.int32), r, mode='constant')
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def cross_kernel(din, dout, region, tau):
    """K(t) = sum(din(x)*dout(x+t)) / sum(din(x)^2)，只在 x 与 x+t 都在区域内求和。"""
    h, w = din.shape
    K = np.zeros((2 * tau + 1, 2 * tau + 1), dtype=np.float64)
    den = float((din[region] ** 2).sum())
    for dy in range(-tau, tau + 1):
        for dx in range(-tau, tau + 1):
            # 把 dout 平移 (dy,dx)：取 x 与 x+t 都有效的重叠块
            ys0, ys1 = max(0, -dy), min(h, h - dy)
            xs0, xs1 = max(0, -dx), min(w, w - dx)
            sub_r = region[ys0:ys1, xs0:xs1]
            sub_in = din[ys0:ys1, xs0:xs1]
            sub_out = dout[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
            m = sub_r
            K[dy + tau, dx + tau] = float((sub_in[m] * sub_out[m]).sum())
    return K / den if den > 0 else K


def profile(K, tau):
    """从二维核取 x / y 两条过中心的剖面。"""
    c = tau
    return K[c, :].copy(), K[:, c].copy()


def half_width(p):
    """剖面从中心降到一半处的偏移（线性插值，px）。"""
    c = len(p) // 2
    peak = p[c]
    if peak <= 0:
        return 0.0
    half = peak * 0.5
    for i in range(c + 1, len(p)):
        if p[i] <= half:
            a, b = p[i - 1], p[i]
            if a == b:
                return float(i - c)
            t = (a - half) / (a - b)
            return float(i - 1 - c + t)
    return float(len(p) - c)


def run_one_size(dll, scene, w, h, bt, blur, amp, tau):
    print()
    print('=' * 74)
    print('等效核   blur_type=%d  blur=%d  scene=%s  %dx%d  A=%.1f'
          % (bt, blur, scene, w, h, amp))
    print('=' * 74)
    base = load_src(scene, w, h)
    r0 = Runner(dll, w, h, bt, 0)
    r1 = Runner(dll, w, h, bt, blur)
    out0 = r0.run(base, 'b%d_z' % bt)
    out1 = r1.run(base, 'b%d_base' % bt)
    print('  %s' % r1.last_msg)

    d = np.abs(out1[:, :, :3].astype(np.int16)
               - out0[:, :, :3].astype(np.int16)).max(axis=2)
    act = (d >= ACT_MIN)
    er = boxsum(act, ACT_ERODE) == (2 * ACT_ERODE + 1) ** 2
    print('  活跃区 %d px（内缩 %d）' % (int(er.sum()), ACT_ERODE))
    if er.sum() < 2000:
        print('  太小，跳过')
        return None

    # 空探针复现性
    again = r1.run(base, 'b%d_null' % bt)
    null_max = int(np.abs(again[:, :, 1].astype(np.int16)
                          - out1[:, :, 1].astype(np.int16)).max())
    print('  空探针(A=0)：max|diff|=%d' % null_max)

    # 白噪声探针
    rng = np.random.default_rng(SEED)
    u = rng.uniform(-1.0, 1.0, size=(h, w))
    probe = base.copy()
    probe[:, :, :3] = np.clip(base[:, :, :3].astype(np.float32)
                              + amp * u[:, :, None], 0, 255).astype(np.uint8)
    outp = r1.run(probe, 'b%d_noise' % bt)

    din = amp * u
    dout = outp[:, :, 1].astype(np.float64) - out1[:, :, 1].astype(np.float64)

    # 形态学内缩 tau，保证任意 |t|<=tau 的平移后重叠区都完整
    # （注意：不能只清数组边框 —— 区域在画面中间时那样等于没缩，分母会偏大）
    #
    # 但先做一次开运算：act = (d>0) 会把掩码边缘的散斑算进来，区域长满细
    # 触须，直接内缩 12 会碎成 2000 px。开运算（先蚀后胀）削掉触须，留下
    # 实心核，再内缩才不掉面积。
    e6 = boxsum(er, 3) == 49
    opened = boxsum(e6, 3) > 0
    tau_eff = tau
    er2 = boxsum(opened, tau_eff) == (2 * tau_eff + 1) ** 2
    while er2.sum() < 3000 and tau_eff > 6:
        tau_eff -= 2
        er2 = boxsum(opened, tau_eff) == (2 * tau_eff + 1) ** 2
    print('  开运算后 %d px  互相关区域 %d px（内缩 %d）'
          % (int(opened.sum()), int(er2.sum()), tau_eff))
    if er2.sum() < 1000:
        print('  互相关区域太小，跳过')
        return None
    tau = tau_eff

    # 去直流：管线是非线性的，dout 在区域内可能有整体偏移；不去掉会通过
    # 有限窗口的 Σdin≠0 泄漏进核，表现为 sum(K) 系统性偏大。
    din = din - float(din[er2].mean())
    dout = dout - float(dout[er2].mean())

    K = cross_kernel(din, dout, er2, tau)
    px, py = profile(K, tau)
    hw_x, hw_y = half_width(px), half_width(py)
    ksum = float(K.sum())
    print('  K(0,0) = %.4f   sum(K) = %.4f (= 直流增益)' % (K[tau, tau], ksum))
    print('  半高半宽  x=%.2f px  y=%.2f px  各向异性 x/y=%.3f'
          % (hw_x, hw_y, (hw_x / hw_y) if hw_y else 0.0))
    print('  x 剖面（中心两侧各 12）:')
    print('    ' + ' '.join('%+.3f' % v for v in px[tau - 12:tau + 13]))
    print('  y 剖面:')
    print('    ' + ' '.join('%+.3f' % v for v in py[tau - 12:tau + 13]))

    # 旁瓣：离中心 >3px 的最大绝对值，box 核会有明显旁瓣，高斯没有
    yy, xx = np.mgrid[-tau:tau + 1, -tau:tau + 1]
    r2 = yy * yy + xx * xx
    outer = K[(r2 > 9)]
    print('  旁瓣：r>3px 的 max|K|=%.4f   RMS=%.4f  （K(0,0)=%.4f）'
          % (np.abs(outer).max(), float(np.sqrt((outer ** 2).mean())),
             K[tau, tau]))

    return {'scene': scene, 'size': '%dx%d' % (w, h), 'blur': blur,
            'blur_type': bt, 'amp': amp, 'tau': tau,
            'K00': float(K[tau, tau]), 'Ksum': ksum,
            'hw_x': hw_x, 'hw_y': hw_y,
            'aniso_xy': (hw_x / hw_y) if hw_y else 0.0,
            'profile_x': [float(v) for v in px],
            'profile_y': [float(v) for v in py],
            'sidelobe_max': float(np.abs(outer).max()),
            'sidelobe_rms': float(np.sqrt((outer ** 2).mean())),
            'active_px': int(er.sum()), 'xcorr_px': int(er2.sum()),
            'null_max': null_max}


def parse_sizes(txt):
    out = []
    for tok in txt.split(','):
        tok = tok.strip().lower().replace('*', 'x')
        if tok:
            a, b = tok.split('x')
            out.append((int(a), int(b)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scene', default='crop_c')
    ap.add_argument('--blur', type=int, default=100)
    ap.add_argument('--bt', default='0,1,2')
    ap.add_argument('--size', default='640x394')
    ap.add_argument('--amp', type=float, default=AMP)
    ap.add_argument('--tau', type=int, default=TAU)
    ap.add_argument('--tag', default='')
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    dll = load_dll()
    warmup(dll)

    bts = [int(x) for x in args.bt.split(',') if x.strip()]
    res = []
    for (w, h) in parse_sizes(args.size):
        for bt in bts:
            r = run_one_size(dll, args.scene, w, h, bt, args.blur,
                             args.amp, args.tau)
            if r:
                res.append(r)

    name = 'kernel_%s_b%d%s.json' % (args.scene, args.blur,
                                     ('_' + args.tag) if args.tag else '')
    jf = os.path.join(OUT, name)
    with open(jf, 'w', encoding='utf-8') as f:
        json.dump({'runs': res}, f, ensure_ascii=False, indent=2)
    print()
    print('[kernel] %d 组 -> %s' % (len(res), jf))


if __name__ == '__main__':
    main()
