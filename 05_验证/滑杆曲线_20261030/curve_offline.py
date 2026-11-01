# -*- coding: utf-8 -*-
"""离线滑杆曲线：同一张真机原始帧，分别跑 产品SDK（加密 bundle, 不下发 blur_type）
与我们 CoreEngine（surface3 + band + T=8.3），档位 0/25/50/75/100。

为什么不在截图上比：现场自动曝光会漂移（实测 luma 单次扫描内跳 20 级），
用户贴的又是 JPEG（磨皮改内容→量化表分配变化→整帧细节都跟着动），
两种污染都会盖掉 5% 量级的曲线差异。离线同一张帧、同一进程，才可比。
"""
import os
import sys
import numpy as np

os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
os.environ['BEAUTY_S3_BAND'] = '1'
os.environ['BEAUTY_S3_BT'] = '8.3'
os.environ['BEAUTY_S3_HALF'] = '1'
os.environ['BEAUTY_S3_TAP25'] = '0'

HERE = r'D:\插件\OBS美颜\06_离线验证'
sys.path.insert(0, HERE)
import real_frame_eval as R

W, H = 1920, 1080
TAG = sys.argv[1] if len(sys.argv) > 1 else 'm00'
LEVELS = [0, 25, 50, 75, 100]
OUTDIR = r'C:\btwork\live_check\curve_off'
os.makedirs(OUTDIR, exist_ok=True)

raw_in = os.path.join(R.WORK, '%s_in.raw' % TAG)
mask_p = os.path.join(R.WORK, '%s_fuai.mask' % TAG)
src = R.load_raw(raw_in, W, H)
mask = R.upscale_mask(R.read_mask(mask_p), W, H)


def det(a, m):
    g = a[:, :, :3].astype(np.float32).mean(axis=2)
    # |Laplacian| 均值（3x3）
    lap = np.abs(g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
                 - 4.0 * g[1:-1, 1:-1])
    sel = m[1:-1, 1:-1]
    return float(lap[sel].mean())


def chg(a, b, m):
    d = np.abs(b[:, :, :3].astype(np.float32) - a[:, :, :3].astype(np.float32)).mean(axis=2)
    return float(d[m].mean())


gd = R.load_gold_dll()
rows = []
for lv in LEVELS:
    go = os.path.join(OUTDIR, 'sdk_%03d.raw' % lv)
    rc, txt = R.run_gold(gd, raw_in, go, W, H, float(lv), -1)
    if rc != 0:
        print('gold fail', lv, txt)
        continue
    gold = R.load_raw(go, W, H)
    co = os.path.join(OUTDIR, 'our_%03d.raw' % lv)
    ours, msg = R.run_core(raw_in, co, W, H, float(lv))
    rows.append(dict(lv=lv,
                     sdk_det=det(gold, mask), our_det=det(ours, mask),
                     sdk_chg=chg(src, gold, mask), our_chg=chg(src, ours, mask),
                     rmse=float(np.sqrt(((ours[:, :, :3].astype(np.float32)
                                          - gold[:, :, :3].astype(np.float32)) ** 2)[mask].mean()))))
    print('  level %3d  sdk det %.3f chg %.3f | our det %.3f chg %.3f | rmse %.3f'
          % (lv, rows[-1]['sdk_det'], rows[-1]['sdk_chg'],
             rows[-1]['our_det'], rows[-1]['our_chg'], rows[-1]['rmse']))

print('\n源图 detail = %.3f（无滤镜，掩码内）' % det(src, mask))
s0 = rows[0]['sdk_det']
o0 = rows[0]['our_det']
print('\n%-6s %10s %10s %10s %10s %8s' %
      ('level', 'SDK保留', '我们保留', 'SDK改动', '我们改动', 'RMSE'))
for r in rows:
    print('%-6d %10.3f %10.3f %10.3f %10.3f %8.3f' %
          (r['lv'], r['sdk_det'] / s0, r['our_det'] / o0, r['sdk_chg'], r['our_chg'], r['rmse']))

import json
json.dump(rows, open(os.path.join(OUTDIR, 'curve_%s.json' % TAG), 'w'), indent=1)
print('\n->', OUTDIR)
