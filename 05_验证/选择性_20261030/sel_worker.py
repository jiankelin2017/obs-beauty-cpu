# -*- coding: utf-8 -*-
"""单组参数的 100 档选择性评估（一个进程只测一组，因为 g_cfg 每进程只读一次 env）。

env：SEL_T / SEL_E / SEL_I / SEL_FA / SEL_F2
口径：5×5 局部标准差（与验收判据一致）flat σ<2 / tex σ>6
输出：末行 JSON
"""
import os
import sys
import json
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

T = float(os.environ.get('SEL_T', '8.3'))
E = float(os.environ.get('SEL_E', '0.70'))
I = float(os.environ.get('SEL_I', '0.976'))
G = float(os.environ.get('SEL_GWP', '2.0'))
FRAMES = sys.argv[1:] or ['m00', 'm02', 'm04']

tbl = '%g,%g,%g,%g,%g' % (I, I, I, I, I)
os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
os.environ['BEAUTY_S3_BAND'] = '1'
os.environ['BEAUTY_S3_TAP25'] = '0'
os.environ['BEAUTY_S3_HALF'] = '1'
os.environ['BEAUTY_S3_LV_TABLE'] = '1'
os.environ['BEAUTY_S3_LV_I'] = tbl
os.environ['BEAUTY_S3_LV_T'] = '%g,%g,%g,%g,%g' % (T, T, T, T, T)
os.environ['BEAUTY_S3_LV_E'] = '%g,%g,%g,%g,%g' % (E, E, E, E, E)
if os.environ.get('SEL_GWP'):
    os.environ['BEAUTY_S3_GWP'] = os.environ['SEL_GWP']

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
SCAN = r'C:\btwork\live_check\scan'


def local_std(gray, k=2):
    pad = np.pad(gray, k, mode='edge')
    return swv(pad, (2 * k + 1, 2 * k + 1)).std(axis=(-1, -2))


acc = {'flat': [], 'tex': [], 'mid': [], 'chg': [], 'rmse': [], 'corr': [], 'fa': [], 'ta': []}
for tag in FRAMES:
    raw_in = os.path.join(R.WORK, '%s_in.raw' % tag)
    gp = os.path.join(SCAN, 'gold_%s_100.raw' % tag)
    if not os.path.exists(gp):
        continue
    mask = R.upscale_mask(R.read_mask(os.path.join(R.WORK, '%s_fuai.mask' % tag)), W, H)
    src = R.load_raw(raw_in, W, H)
    gold = R.load_raw(gp, W, H)
    ours, _ = R.run_core(raw_in, os.path.join(SCAN, 'sel_o.raw'), W, H, 100.0)

    base = src[:, :, :3].astype(np.float32)
    gray = base.mean(axis=2)
    sd = local_std(gray, 2)
    flat = mask & (sd < 2.0)
    tex = mask & (sd > 6.0)
    mid = mask & (sd >= 2.0) & (sd <= 6.0)
    d = np.abs(ours[:, :, :3].astype(np.float32) - base).mean(axis=2)

    acc['flat'].append(float(d[flat].mean()))
    acc['tex'].append(float(d[tex].mean()))
    acc['mid'].append(float(d[mid].mean()))
    acc['fa'].append(100.0 * flat.sum() / mask.sum())
    acc['ta'].append(100.0 * tex.sum() / mask.sum())
    acc['chg'].append(R.change_in(src, ours, mask))
    acc['rmse'].append(R.rmse_in(ours, gold, mask))
    acc['corr'].append(R.spatial_corr(src, ours, gold, mask))

out = {k: round(float(np.mean(v)), 4) for k, v in acc.items()}
out['ratio'] = round(out['flat'] / out['tex'], 3)
out['T'] = T
out['e'] = E
out['I'] = I
out['gwp'] = G
print('T=%-5g e=%-5g I=%-5g g=%-4g | chg %6.3f  flat %5.3f  mid %5.3f  tex %5.3f  比 %5.2f | RMSE %5.3f 相关 %5.3f'
      % (T, E, I, G, out['chg'], out['flat'], out['mid'], out['tex'], out['ratio'], out['rmse'], out['corr']))
print('JSON ' + json.dumps(out))
