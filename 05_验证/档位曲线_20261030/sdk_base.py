# -*- coding: utf-8 -*-
"""产品（加密 bundle，bt=-1）三帧五档基准：改动量 + 平坦/纹理拆分。

与 scan_T_worker.py 用同一套度量口径（掩码内 |Δ| 均值、3x3 拉普拉斯
σ 代理分档 σ<2 / σ>6），保证两边数字可直接对比。
"""
import os
import sys
import json
import numpy as np

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
LEVELS = [0, 25, 50, 75, 100]
FRAMES = sys.argv[1:] or ['m00', 'm02', 'm04']
OUT = r'C:\btwork\live_check\scan'
os.makedirs(OUT, exist_ok=True)

gd = R.load_gold_dll()
res = {'levels': {}}
for tag in FRAMES:
    raw_in = os.path.join(R.WORK, '%s_in.raw' % tag)
    mask = R.upscale_mask(R.read_mask(os.path.join(R.WORK, '%s_fuai.mask' % tag)), W, H)
    src = R.load_raw(raw_in, W, H)
    base = src[:, :, :3].astype(np.float32)
    sg = base.mean(axis=2)
    lap = np.abs(4.0 * sg[1:-1, 1:-1] - sg[:-2, 1:-1] - sg[2:, 1:-1]
                 - sg[1:-1, :-2] - sg[1:-1, 2:])
    sel = mask[1:-1, 1:-1]
    flat = sel & (lap < 2.0)
    tex = sel & (lap > 6.0)
    for lv in LEVELS:
        go = os.path.join(OUT, 'gold_%s_%03d.raw' % (tag, lv))
        rc, txt = R.run_gold(gd, raw_in, go, W, H, float(lv), -1)
        if rc != 0:
            print('gold fail', tag, lv, txt)
            continue
        g = R.load_raw(go, W, H)
        d = np.abs(g[:, :, :3].astype(np.float32) - base).mean(axis=2)
        e = res['levels'].setdefault(lv, {'chg': [], 'flat': [], 'tex': []})
        e['chg'].append(float(d[mask].mean()))
        e['flat'].append(float(d[1:-1, 1:-1][flat].mean()))
        e['tex'].append(float(d[1:-1, 1:-1][tex].mean()))

for lv, e in res['levels'].items():
    for k in ('chg', 'flat', 'tex'):
        e[k] = round(float(np.mean(e[k])), 4)
    e['ratio'] = round(e['flat'] / e['tex'], 3) if e['tex'] else None
    print('SDK %3d档  chg %6.3f  flat %6.3f  tex %6.3f  flat/tex %s'
          % (lv, e['chg'], e['flat'], e['tex'],
             ('%.2f' % e['ratio']) if e['ratio'] is not None else '-'))
json.dump(res, open(os.path.join(OUT, 'sdk_base.json'), 'w'), indent=1)
print('->', os.path.join(OUT, 'sdk_base.json'))
