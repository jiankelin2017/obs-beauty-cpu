# -*- coding: utf-8 -*-
"""档位曲线评估：给定 LV_I / LV_T 表，跑五档并与产品金标对比。

用法：python lv_eval.py "0,0.005,0.205,0.574,0.975" "8.3,8.3,8.3,8.3,8.3" [frames...]
输出：每档 chg / flat / tex / RMSE / 空间相关，最后一行 JSON。
"""
import os
import sys
import json
import numpy as np

TBL_I = sys.argv[1]
TBL_T = sys.argv[2]
FRAMES = sys.argv[3:] or ['m00', 'm02', 'm04']

os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
os.environ['BEAUTY_S3_BAND'] = '1'
os.environ['BEAUTY_S3_TAP25'] = '0'
os.environ['BEAUTY_S3_HALF'] = '1'
os.environ['BEAUTY_S3_LV_TABLE'] = os.environ.get('LV_TABLE', '1')
os.environ['BEAUTY_S3_LV_I'] = TBL_I
os.environ['BEAUTY_S3_LV_T'] = TBL_T
if os.environ.get('EFIX'):
    os.environ['BEAUTY_S3_E_FIX'] = os.environ['EFIX']

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
LEVELS = [0, 25, 50, 75, 100]
WORK = R.WORK
SCAN = r'C:\btwork\live_check\scan'

acc = {lv: {'chg': [], 'flat': [], 'tex': [], 'rmse': [], 'corr': []} for lv in LEVELS}
for tag in FRAMES:
    raw_in = os.path.join(WORK, '%s_in.raw' % tag)
    mask = R.upscale_mask(R.read_mask(os.path.join(WORK, '%s_fuai.mask' % tag)), W, H)
    src = R.load_raw(raw_in, W, H)
    base = src[:, :, :3].astype(np.float32)
    sg = base.mean(axis=2)
    lap = np.abs(4.0 * sg[1:-1, 1:-1] - sg[:-2, 1:-1] - sg[2:, 1:-1]
                 - sg[1:-1, :-2] - sg[1:-1, 2:])
    sel = mask[1:-1, 1:-1]
    flat = sel & (lap < 2.0)
    tex = sel & (lap > 6.0)
    for lv in LEVELS:
        ours, _ = R.run_core(raw_in, os.path.join(SCAN, 'lv_o.raw'), W, H, float(lv))
        gp = os.path.join(SCAN, 'gold_%s_%03d.raw' % (tag, lv))
        gold = R.load_raw(gp, W, H) if os.path.exists(gp) else None
        d = np.abs(ours[:, :, :3].astype(np.float32) - base).mean(axis=2)
        a = acc[lv]
        a['chg'].append(R.change_in(src, ours, mask))
        a['flat'].append(float(d[1:-1, 1:-1][flat].mean()) if flat.sum() > 500 else None)
        a['tex'].append(float(d[1:-1, 1:-1][tex].mean()) if tex.sum() > 500 else None)
        if gold is not None:
            a['rmse'].append(R.rmse_in(ours, gold, mask))
            a['corr'].append(R.spatial_corr(src, ours, gold, mask))

out = {}
for lv, a in acc.items():
    out[lv] = {}
    for k, v in a.items():
        vv = [x for x in v if x is not None]
        out[lv][k] = round(float(np.mean(vv)), 4) if vv else None
    out[lv]['ratio'] = (round(out[lv]['flat'] / out[lv]['tex'], 3)
                        if out[lv]['tex'] else None)

print('%-5s %7s %7s %7s %6s %6s %6s' % ('档位', 'chg', 'flat', 'tex', '比值', 'RMSE', '相关'))
for lv in LEVELS:
    e = out[lv]
    print('%-5d %7.3f %7.3f %7.3f %6s %6s %6s'
          % (lv, e['chg'], e['flat'] or 0, e['tex'] or 0,
             ('%.2f' % e['ratio']) if e['ratio'] else '-',
             ('%.3f' % e['rmse']) if e['rmse'] is not None else '-',
             ('%.3f' % e['corr']) if e['corr'] is not None else '-'))
print('JSON ' + json.dumps({'I': TBL_I, 'T': TBL_T, 'out': out}, ensure_ascii=False))
