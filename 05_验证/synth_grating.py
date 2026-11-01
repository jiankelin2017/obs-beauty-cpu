# -*- coding: utf-8 -*-
"""合成光栅测磨皮端到端传递函数 H_eff(f)（C23 §6.0 前置验证）。

为什么要这个
------------
C23 第 2 批工单 #5（25 tap 环核）是唯一一处「结构本身可能没抄对」的地方。
写完再推翻的代价远高于先花半天验证。本脚本给出磨皮的**端到端**频率响应，
用它可以同时回答三件事：

    1. 环半径 / 核尺度  —— 看 |H| 的截止位置
    2. 各向异性        —— 同 f_px 下 gx/gy
    3. box vs 高斯     —— 看 |H| 有没有旁瓣/过零（box 有，高斯没有）

为什么不用脉冲/阶跃
------------------
surface blur 的值域权重是

    wk = 1 - min(dg^2 * yFactor, 1)          # yFactor: pass1=40, pass2=20

dg 是中心与抽头的归一化色差。单像素脉冲 A 灰阶会让 dg = A/255：

    A=9   -> dg^2*40 = 0.050 -> wk=0.95，但每抽头响应只有 A/26*gain ~ 0.3 灰阶，
             uint8 舍入后基本是 0
    A=30  -> dg^2*40 = 0.553 -> wk=0.45，幅度越大反而被压得越狠，且已非线性
    强阶跃 -> 边缘处 dg 很大 -> wk~0 -> 边缘根本不被磨，ESF 就是阶跃本身

这个权重天生就是拒绝孤立离群点的，脉冲响应接近零。低幅光栅才在线性区：

    A=16, P=20px -> dg_max = 2*pi*16/20 = 5.03 -> dg^2*40 = 0.0156 -> wk=0.984

而响应幅度是 16*|H|，远大于量化步长。

测量方法（差分 + 复投影）
------------------------
同一底图跑两遍，一遍原样、一遍叠低幅余弦光栅，取差分：

    dOut = out_probe - out_base  ==  A * H_eff(f) * exp(i*phi) * cos(...)

底图真实纹理在差分里**精确抵消**，不需要平坦皮肤、也不需要建模掩码。
再把 dOut 投影到 cos / sin 两个正交基上取复增益：

    g = <d, cos>/<cos,cos> + i * <d, sin>/<sin,sin>
    |H_eff| = |g| / A,   phi = arg(g)

x / y 两向用**相同像素周期**，所以同一 f_px 下 gx/gy 直接就是各向异性。

已实测的前提（本脚本会自己复验）
    - 同一输入两次运行输出**逐字节相同**（空探针 max|diff|=0），噪声底为零
    - blur=100 对真实底图的改动在皮肤区内均值仅 ~1.9 灰阶、且散斑状，
      所以活跃区判据必须用 d>0，不能设高阈值

用法
----
    python synth_grating.py                          # crop_c 640x394, bt 0/1/2
    python synth_grating.py --bt 1 --size 640x394,1280x720,1080x1920
    python synth_grating.py --scene crop_d --blur 50
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
OUT = os.path.join(HERE, 'goldens', 'grating')

P_COUNT = 11
P_BLUR = 0

AMP = 16.0          # 光栅幅度（灰阶）。见文件头推导，16 稳在线性区
WARMUP = 3          # 进程级预热帧数（fuai 首帧在建会话，faces 要到第 2 帧才出）
ACT_MIN = 1         # 活跃区阈值。别调高：blur=100 的改动是散斑状，阈值一高就碎
ACT_ERODE = 6       # 活跃区内缩，躲开掩码羽化带
PERIODS = (8, 10, 12, 16, 20, 24, 32, 48, 64)

UV_SX, UV_SY = 0.002640845, 0.0046875


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------
def load_dll():
    if not os.path.exists(DLL):
        print('[grating] DLL not found: %s (run build_golden.bat first)' % DLL)
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
    def __init__(self, dll, w, h, bt, blur, skin_detect=1, smooth_mode=0):
        self.dll, self.w, self.h = dll, w, h
        self.bt, self.blur = bt, blur
        self.sd, self.sm = skin_detect, smooth_mode
        self.n = 0
        self.last_msg = ''

    def run(self, arr, tag):
        raw_in = os.path.join(OUT, '_in_%dx%d.raw' % (self.w, self.h))
        raw_out = os.path.join(OUT, '_o_%dx%d_%s.raw' % (self.w, self.h, tag))
        arr.tofile(raw_in)
        panel = (ctypes.c_double * P_COUNT)()
        panel[P_BLUR] = float(self.blur)
        msg = ctypes.create_string_buffer(512)
        rc = self.dll.RefGoldenRun(
            ENGINE_DIR.encode('utf-8'), raw_in.encode('utf-8'),
            raw_out.encode('utf-8'), self.w, self.h, panel, P_COUNT,
            self.bt, self.sd, self.sm, 1, msg, 512)
        self.last_msg = msg.value.decode('utf-8', 'replace')
        if rc != 0:
            raise RuntimeError('RefGoldenRun rc=%d: %s' % (rc, self.last_msg))
        self.n += 1
        a = np.fromfile(raw_out, dtype=np.uint8)
        need = self.w * self.h * 4
        if a.size != need:
            raise RuntimeError('out size %d != %d' % (a.size, need))
        return a.reshape((self.h, self.w, 4))


def warmup(dll):
    """进程级预热：吃掉 GL 纹理 / ONNX 会话的懒加载，否则首帧 faces=0。"""
    if not os.path.exists(OUT):
        os.makedirs(OUT)
    w, h = 640, 394
    z = np.zeros((h, w, 4), dtype=np.uint8)
    z[:, :, 3] = 255
    r = Runner(dll, w, h, 1, 0)
    for _ in range(WARMUP):
        r.run(z, 'warm')


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def load_src(scene, w, h):
    """优先用 goldens/src 里已备好的 raw；尺寸不符就按等比 letterbox 重采样。"""
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
        raise IOError('source not found: %s(.raw/.png)' % scene)
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


def make_basis(w, h, orient, period):
    """返回 (cos, sin) 两个零均值基，形状 (h, w)。"""
    if orient == 'x':
        idx = np.arange(w, dtype=np.float64) + 0.5
        c1 = np.cos(2.0 * np.pi * idx / period)[None, :]
        s1 = np.sin(2.0 * np.pi * idx / period)[None, :]
    else:
        idx = np.arange(h, dtype=np.float64) + 0.5
        c1 = np.cos(2.0 * np.pi * idx / period)[:, None]
        s1 = np.sin(2.0 * np.pi * idx / period)[:, None]
    return (np.broadcast_to(c1, (h, w)).copy(),
            np.broadcast_to(s1, (h, w)).copy())


def add_grating(base, cos_b, amp):
    out = base[:, :, :3].astype(np.float32) + amp * cos_b[:, :, None]
    res = base.copy()
    res[:, :, :3] = np.clip(out, 0, 255).astype(np.uint8)
    return res


def complex_gain(dout, cos_b, sin_b, region):
    """把 dout 投影到 cos/sin 基上，返回复增益（未除幅度）。"""
    c = cos_b[region]
    s = sin_b[region]
    d = dout[region]
    dc = float((c * c).sum())
    ds = float((s * s).sum())
    gc = float((d * c).sum()) / dc if dc > 0 else 0.0
    gs = float((d * s).sum()) / ds if ds > 0 else 0.0
    g = gc + 1j * gs
    resid = d - (gc * c + gs * s)
    rms = float(np.sqrt((resid * resid).mean())) if d.size else 0.0
    return g, rms


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def parse_sizes(txt):
    out = []
    for tok in txt.split(','):
        tok = tok.strip().lower().replace('*', 'x')
        if not tok:
            continue
        w, h = tok.split('x')
        out.append((int(w), int(h)))
    return out


def run_group(dll, scene, w, h, bt, blur, amp, actmin, periods_req):
    print()
    print('=' * 72)
    print('blur_type=%d  blur=%d  scene=%s  %dx%d' % (bt, blur, scene, w, h))
    print('=' * 72)

    base_arr = load_src(scene, w, h)
    r0 = Runner(dll, w, h, bt, 0)
    r1 = Runner(dll, w, h, bt, blur)
    out0 = r0.run(base_arr, 'b%d_z' % bt)
    out1 = r1.run(base_arr, 'b%d_base' % bt)
    print('  %s' % r1.last_msg)

    d = np.abs(out1[:, :, :3].astype(np.int16)
               - out0[:, :, :3].astype(np.int16)).max(axis=2)
    act = (d >= actmin)
    er = boxsum(act, ACT_ERODE) == (2 * ACT_ERODE + 1) ** 2
    print('  act(d>=%d) %d px  内缩 %d 后 %d px  mean|d|=%.2f max=%d'
          % (actmin, int(act.sum()), ACT_ERODE, int(er.sum()),
             float(d[act].mean()) if act.sum() else 0.0, int(d.max())))
    if er.sum() < 500:
        print('  活跃区太小，跳过')
        return None
    ys, xs = np.nonzero(er)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    ext_x, ext_y = x1 - x0 + 1, y1 - y0 + 1
    print('  bbox x[%d..%d] y[%d..%d] -> %dx%d' % (x0, x1, y0, y1, ext_x, ext_y))

    # 空探针：复现性
    again = r1.run(base_arr, 'b%d_null' % bt)
    dn = again[:, :, 1].astype(np.int16) - out1[:, :, 1].astype(np.int16)
    null_max = int(np.abs(dn).max())
    print('  空探针(A=0)：max|diff|=%d  非零 %.4f%%'
          % (null_max, 100.0 * float((dn != 0).mean())))

    # 频点：周期上限受活跃区短边约束（至少留 2.5 个周期）
    pmax = int(min(ext_x, ext_y) / 2.5)
    periods = [p for p in periods_req if p <= pmax]
    if len(periods) < 3:
        periods = [p for p in (8, 10, 12, 16) if p <= pmax]
    print('  周期(px): %s   f_px %.4f..%.4f cycles/px'
          % (periods, 1.0 / periods[-1], 1.0 / periods[0]))

    rows = []
    for orient in ('x', 'y'):
        for p in periods:
            cb, sb = make_basis(w, h, orient, p)
            probe = add_grating(base_arr, cb, amp)
            outp = r1.run(probe, 'b%d_%s%02d' % (bt, orient, p))
            dout = outp[:, :, 1].astype(np.float64) \
                - out1[:, :, 1].astype(np.float64)
            g, rms = complex_gain(dout, cb, sb, er)
            rows.append({'orient': orient, 'period': p, 'f_px': 1.0 / p,
                         'gc': g.real / amp, 'gs': g.imag / amp,
                         'mag': abs(g) / amp,
                         'phase_deg': float(np.degrees(np.angle(g))),
                         'rms': rms})
            print('    %s P=%2d f=%.4f  |H|=%6.4f  phi=%+7.2f  rms=%.3f'
                  % (orient, p, 1.0 / p, abs(g) / amp,
                     float(np.degrees(np.angle(g))), rms))

    gx = {r['period']: r for r in rows if r['orient'] == 'x'}
    gy = {r['period']: r for r in rows if r['orient'] == 'y'}
    aniso = []
    for p in periods:
        if p in gx and p in gy and abs(gy[p]['mag']) > 1e-9:
            aniso.append({'period': p,
                          'ratio': gx[p]['mag'] / gy[p]['mag']})
    pred = (UV_SY * h) / (UV_SX * w)
    print('  各向异性 gx/gy（固定 UV 半轴预测 %.3f）：' % pred)
    for a in aniso:
        print('    P=%2d  gx/gy=%.3f' % (a['period'], a['ratio']))
    if aniso:
        rs = [a['ratio'] for a in aniso]
        print('    -> 均值 %.3f  范围 %.3f..%.3f'
              % (float(np.mean(rs)), min(rs), max(rs)))

    return {'scene': scene, 'size': '%dx%d' % (w, h), 'blur': blur,
            'blur_type': bt, 'amp': amp, 'rows': rows, 'aniso': aniso,
            'aniso_pred_fixed_uv': pred,
            'active_px': int(er.sum()), 'bbox': [x0, y0, x1, y1],
            'active_mean': float(d[act].mean()) if act.sum() else 0.0,
            'active_max': int(d.max()), 'null_max': null_max,
            'periods': periods}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scene', default='crop_c')
    ap.add_argument('--blur', type=int, default=100)
    ap.add_argument('--bt', default='0,1,2')
    ap.add_argument('--size', default='640x394')
    ap.add_argument('--amp', type=float, default=AMP)
    ap.add_argument('--actmin', type=int, default=ACT_MIN)
    ap.add_argument('--tag', default='')
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    dll = load_dll()
    warmup(dll)

    bts = [int(x) for x in args.bt.split(',') if x.strip() != '']
    sizes = parse_sizes(args.size)
    groups = []
    for (w, h) in sizes:
        for bt in bts:
            g = run_group(dll, args.scene, w, h, bt, args.blur, args.amp,
                          args.actmin, PERIODS)
            if g:
                groups.append(g)

    name = 'grating_%s_b%d%s.json' % (args.scene, args.blur,
                                      ('_' + args.tag) if args.tag else '')
    jf = os.path.join(OUT, name)
    with open(jf, 'w', encoding='utf-8') as f:
        json.dump({'groups': groups}, f, ensure_ascii=False, indent=2)
    print()
    print('[grating] %d 组 -> %s' % (len(groups), jf))


if __name__ == '__main__':
    main()
