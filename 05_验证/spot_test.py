# -*- coding: utf-8 -*-
"""
spot_test —— 方案 B：合成阳性样本，量化「痘印 / 鼻翼阴影 / 唇纹」到底抹不抹得掉
================================================================================

为什么要合成
------------
真实素材里没有痘印（263 张相机照片扫过一遍，全是合影 / 舞台灯 / 侧脸），
于是「额头痘印、鼻翼阴影、嘴唇纹理全留着」这条反馈在离线层面**没有因变量可测** ——
测出来 100% 保留也算通过，是假通过。

所以改为**自己造因变量**：在现有 `640x394.raw` 的脸上叠加已知强度、已知尺寸的
缺陷，再让 SDK 与 core 各跑一遍磨皮，量「缺陷还剩下多少」。

合成参数按真实量级取：脸框宽 111 px（真脸约 15 cm），
    痘印直径 4~7 px  → 真实约 0.5~0.9 cm
    痘印深度 −13~−22 灰阶（炎症后色沉的典型对比度）
    偏色 R×0.80 / G×1.00 / B×1.20  → 痘印偏红棕而不是纯灰

量化口径
--------
**用差值图，不用绝对深度。** 第一版直接量「合成图的中心-环形亮度差」，结果在额头
痘印·大上失真：那块皮肤本来就比周围亮 20 灰阶，痘印压下去后净深度只剩 2.37，
基数接近 0，残留率没法算。

改成：同一档磨皮分别跑原图与合成图，取差

    diff = 引擎(合成图) − 引擎(原图)

这个 diff 就是「缺陷经过磨皮之后还剩多少」，原图本身的纹理被完全抵消掉。

    缺陷强度 = 中心 3×3 与环形(6~11 px)的 diff 亮度差    （负值 = 还是个暗斑）
    残留%    = 磨皮后强度 / 磨皮前强度 × 100
    残留灰阶 = |磨皮后强度|                              （人眼能否察觉看这个）

    经验阈值：<1 灰阶基本看不见；2~3 灰阶凑近能辨；>5 灰阶明显。

**唇纹的尺度限制（必须知道）**：人脸框宽 111 px ≈ 真实 15 cm，即 1 px ≈ 1.35 mm。
真实唇纹间距约 0.3~0.8 mm —— 不足 1 px，**这个素材的分辨率根本表达不了**。
所以这里的唇纹是「放大版代理」：周期 5 px（≈6.7 mm），振幅 8 灰阶。
它测的是「条状中等尺度纹理能不能被磨掉」，不等于真实唇纹。
度量用 std(Y − box21)，因为周期 5 px 的正弦在 |Y − box3| 细频带里会被
3×3 均值削掉八成，测不出来（第一版实测只增加 0.85，信噪比不够）。

用法
----
    python spot_test.py synth          # 只生成合成图，输出 PNG + raw，人工确认位置
    python spot_test.py                # 合成 + SDK/core 对拍（磨皮 30/50/80）
    python spot_test.py 50             # 只跑指定档位
"""

from __future__ import print_function

import ctypes
import json
import os
import re
import sys

import numpy as np
from PIL import Image

import low_path_test as L

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

W, H = 640, 394
P_COUNT = 11
P_BLUR = 0
P_DELSPOT = 10

# 人脸框（cv2 YuNet 在 640x394.raw 上的实测值，与 region_gap.py 同源）
BX, BY, BW, BH = 276.4, 84.8, 111.3, 140.8

ORIG_RAW = os.path.join(L.RES, '640x394.raw')
SYNTH_RAW = os.path.join(L.RES, '_spot_src.raw')
SYNTH_PNG = os.path.join(L.RES, '_spot_src.png')
DEFECT_JSON = os.path.join(L.RES, '_spot_defects.json')

SDK_DLL = os.path.join(L.HERE, 'ref_golden.dll')
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')


def P(nx, ny):
    """归一化（相对人脸框）→ 绝对像素"""
    return BX + nx * BW, BY + ny * BH


# ---------------------------------------------------------------- 缺陷定义
# type=spot   高斯暗斑，直径 d px，深度 depth 灰阶（负=变暗）
# type=band   椭圆暗带，rx/ry 为两个方向的 σ
# type=line   竖直条纹，period px、振幅 amp，用高斯窗限制在唇区
DEFECTS = [
    dict(name='额头痘印·大', type='spot', nx=0.50, ny=0.20, d=7.0, depth=-22.0),
    dict(name='额头痘印·小', type='spot', nx=0.62, ny=0.27, d=4.0, depth=-13.0),
    dict(name='脸颊痘印',   type='spot', nx=0.25, ny=0.52, d=5.0, depth=-18.0),
    dict(name='鼻翼阴影·左', type='band', nx=0.46, ny=0.61, rx=2.2, ry=7.0, depth=-12.0),
    dict(name='鼻翼阴影·右', type='band', nx=0.70, ny=0.61, rx=2.2, ry=7.0, depth=-12.0),
    dict(name='唇纹',       type='line', nx=0.54, ny=0.77, rw=18.0, rh=9.0,
         period=5.0, amp=8.0),
]

# 唇纹的能量统计窗口（归一化矩形）
LIP_WIN = (0.36, 0.72, 0.72, 0.82)


def build_delta():
    """生成每个缺陷的亮度增量图 delta(H,W)，以及中心坐标。"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    out = []
    for d in DEFECTS:
        cx, cy = P(d['nx'], d['ny'])
        if d['type'] == 'spot':
            sigma = d['d'] / 2.355
            g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2)))
            delta = d['depth'] * g
        elif d['type'] == 'band':
            g = np.exp(-(((xx - cx) ** 2) / (2 * d['rx'] ** 2)
                         + ((yy - cy) ** 2) / (2 * d['ry'] ** 2)))
            delta = d['depth'] * g
        elif d['type'] == 'line':
            win = np.exp(-(((xx - cx) ** 2) / (2 * d['rw'] ** 2)
                           + ((yy - cy) ** 2) / (2 * d['rh'] ** 2)))
            delta = d['amp'] * np.sin(2 * np.pi * (xx - cx) / d['period']) * win
        else:
            raise ValueError(d['type'])
        out.append((d['name'], d['type'], cx, cy, delta))
    return out


def synth(src):
    """src: uint8 (H,W,4) RGBA → 叠加缺陷后的同形状数组"""
    img = src[:, :, :3].astype(np.float64)
    for name, typ, cx, cy, delta in build_delta():
        # 痘印偏红棕：R 少降、B 多降；条纹（唇纹）保持中性，避免引入假色偏
        if typ == 'line':
            kr, kg, kb = 1.0, 1.0, 1.0
        else:
            kr, kg, kb = 0.80, 1.00, 1.20
        img[:, :, 0] += delta * kr
        img[:, :, 1] += delta * kg
        img[:, :, 2] += delta * kb
    out = src.copy()
    out[:, :, :3] = np.clip(img, 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------- 度量
def diff_luma(syn, src):
    """两张 RGBA 图相减后的亮度差图（float）。这就是「缺陷还剩多少」。"""
    d = syn[:, :, :3].astype(np.float64) - src[:, :, :3].astype(np.float64)
    return 0.299 * d[:, :, 0] + 0.587 * d[:, :, 1] + 0.114 * d[:, :, 2]


def spot_strength(syn, src, cx, cy, r_in=1, r_lo=6, r_hi=11):
    """差值图上，中心 3×3 与环形(6~11 px)的亮度差。负值 = 仍是暗斑。"""
    y = diff_luma(syn, src)
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.hypot(xx - cx, yy - cy)
    core = y[int(cy) - r_in:int(cy) + r_in + 1,
             int(cx) - r_in:int(cx) + r_in + 1].mean()
    ring = y[(dist >= r_lo) & (dist <= r_hi)].mean()
    return float(core - ring)


def box_mean(a, r):
    h, w = a.shape
    k = 2 * r + 1
    p = np.pad(a, ((0, 0), (r, r)), mode='edge')
    c = np.cumsum(p, axis=1, dtype=np.float64)
    c = np.concatenate([np.zeros((h, 1)), c], axis=1)
    h1 = (c[:, k:] - c[:, :-k]) / k
    p2 = np.pad(h1, ((r, r), (0, 0)), mode='edge')
    c2 = np.cumsum(p2, axis=0, dtype=np.float64)
    c2 = np.concatenate([np.zeros((1, w)), c2], axis=0)
    return (c2[k:, :] - c2[:-k, :]) / k


def lip_strength(syn, src):
    """唇窗内 std(Y − box21)：条状纹理的强度。"""
    y = diff_luma(syn, src)
    x0, y0, x1, y1 = [int(v) for v in
                      (BX + LIP_WIN[0] * BW, BY + LIP_WIN[1] * BH,
                       BX + LIP_WIN[2] * BW, BY + LIP_WIN[3] * BH)]
    w = y[y0:y1, x0:x1]
    return float((w - box_mean(w, 10)).std())


def measure(syn, src):
    res = {}
    for name, typ, cx, cy, _ in build_delta():
        if typ == 'line':
            res[name] = lip_strength(syn, src)
        else:
            res[name] = spot_strength(syn, src, cx, cy)
    return res


# ---------------------------------------------------------------- 引擎
def run_sdk(in_raw, blur, delspot=0.0):
    d = ctypes.WinDLL(SDK_DLL)
    d.RefGoldenRun.argtypes = [ctypes.c_char_p] * 3 + [
        ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double),
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    out = os.path.join(L.OUT, '_spot_sdk.raw')
    arr = (ctypes.c_double * P_COUNT)(*[0.0] * P_COUNT)
    arr[P_BLUR] = blur
    arr[P_DELSPOT] = delspot
    msg = ctypes.create_string_buffer(512)
    rc = d.RefGoldenRun(ENGINE_DIR.encode(), in_raw.encode(), out.encode(),
                         W, H, arr, P_COUNT, 1, 1, 0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('sdk rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
    return L.load(out, W, H)


def run_core(in_raw, blur, delspot=0.0):
    dll = ctypes.WinDLL(L.DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    for n in ('BeautyCoreSetTone', 'BeautyCoreSetDetail'):
        getattr(dll, n).argtypes = [ctypes.c_double, ctypes.c_double]
    dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    dll.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]
    dll.BeautyCoreSetTone(0.0, 0.0)
    dll.BeautyCoreSetDetail(0.0, 0.0)
    dll.BeautyCoreSetClarityPanel(0.0)
    for i in range(5):
        # 索引 4 = 祛斑痘（P_DELSPOT）。区域项顺序见 beauty_core.h 的 RegionIdx。
        dll.BeautyCoreSetRegion(i, delspot if i == 4 else 0.0)
    out = os.path.join(L.OUT, '_spot_core.raw')
    msg = ctypes.create_string_buffer(512)
    for _ in range(3):
        dll.BeautyCoreRun(in_raw.encode(), out.encode(), W, H, blur, 0,
                          0.0, 0.0, 1, msg, 512)
    m = re.search(r'ms=([0-9.]+)', msg.value.decode('ascii', 'replace'))
    return L.load(out, W, H), (float(m.group(1)) if m else -1.0)


# ---------------------------------------------------------------- 主流程
def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    src = L.load(os.path.join(L.RES, '640x394.raw'), W, H)
    made = synth(src)

    if arg == 'synth':
        made.tofile(SYNTH_RAW)
        Image.fromarray(made[:, :, :3]).save(SYNTH_PNG)
        meta = [dict(name=d['name'], type=d['type'],
                     cx=round(P(d['nx'], d['ny'])[0], 1),
                     cy=round(P(d['nx'], d['ny'])[1], 1)) for d in DEFECTS]
        with open(DEFECT_JSON, 'w', encoding='utf-8') as fp:
            json.dump(meta, fp, ensure_ascii=False, indent=1)
        print('合成图已写出：\n  %s\n  %s\n  %s' % (SYNTH_RAW, SYNTH_PNG, DEFECT_JSON))
        print('\n缺陷位置（绝对像素）：')
        for m in meta:
            print('  %-12s (%6.1f, %6.1f)' % (m['name'], m['cx'], m['cy']))
        print('\n磨皮前的缺陷强度（合成图 − 原图）：')
        a, b = measure(src, src), measure(made, src)
        for k in b:
            print('  %-12s %8.2f' % (k, b[k]))
        return

    # 用法：spot_test.py [磨皮档位...] [--delspot N]
    args = sys.argv[1:]
    dspot = 0.0
    if '--delspot' in args:
        i = args.index('--delspot')
        dspot = float(args[i + 1])
        args = args[:i] + args[i + 2:]
    blurs = [float(x) for x in args] or [50.0]
    made.tofile(SYNTH_RAW)
    Image.fromarray(made[:, :, :3]).save(SYNTH_PNG)

    base = measure(made, src)
    names = [d['name'] for d in DEFECTS]
    print('磨皮前缺陷强度（合成图 − 原图，负=暗斑）  祛斑痘=%.0f' % dspot)
    for n in names:
        print('  %-12s %8.2f' % (n, base[n]))

    for blur in blurs:
        print('\n' + '=' * 68)
        print('磨皮 %.0f  祛斑痘 %.0f' % (blur, dspot))
        print('%-12s %9s %9s %9s %9s %9s %9s'
              % ('缺陷', 'SDK残留', 'SDK%', 'core残留', 'core%', '差pp', '倍数'))
        try:
            sdk_base = run_sdk(ORIG_RAW, blur, dspot)
            sdk_syn = run_sdk(SYNTH_RAW, blur, dspot)
            s = measure(sdk_syn, sdk_base)
        except Exception as e:
            print('  SDK 失败：%s' % e)
            s = None
        try:
            core_base, _ = run_core(ORIG_RAW, blur, dspot)
            core_syn, ms = run_core(SYNTH_RAW, blur, dspot)
            c = measure(core_syn, core_base)
        except Exception as e:
            print('  core 失败：%s' % e)
            c = None
        if s is None or c is None:
            continue
        for n in names:
            b0 = base[n]
            ps = 100.0 * s[n] / b0 if abs(b0) > 1e-9 else float('nan')
            pc = 100.0 * c[n] / b0 if abs(b0) > 1e-9 else float('nan')
            ratio = (abs(c[n]) / abs(s[n])) if abs(s[n]) > 1e-6 else float('nan')
            print('%-12s %9.2f %8.1f%% %9.2f %8.1f%% %8.1f %8.2fx'
                  % (n, abs(s[n]), ps, abs(c[n]), pc, pc - ps, ratio))
        print('  core 单帧 %.2f ms' % ms)


if __name__ == '__main__':
    main()
