# -*- coding: utf-8 -*-
"""T 扫描 worker：一个进程固定一个 T，跑 0/25/50/75/100 五档。

为什么要拆进程序：beauty_core 的 g_cfg 只在首次 BeautyCoreRun 前读 env，
之后整进程缓存 —— 同进程换 T 无效。但档位是 BeautyCoreRun 的入参，
所以「一个 T = 一个进程 = 五个档位」是成本最优的切法。

用法：python scan_T_worker.py <T> [frames...]
输出：JSON 一行到 stdout
"""
import os
import sys
import json
import numpy as np

T = float(sys.argv[1])
FRAMES = sys.argv[2:] or ['m00', 'm02', 'm04']

os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
os.environ['BEAUTY_S3_BAND'] = '1'
os.environ['BEAUTY_S3_TAP25'] = '0'
os.environ['BEAUTY_S3_HALF'] = '1'
os.environ['BEAUTY_S3_BT'] = str(T)

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
LEVELS = [0, 25, 50, 75, 100]
WORK = R.WORK

res = {'T': T, 'frames': FRAMES, 'levels': {}}
for tag in FRAMES:
    raw_in = os.path.join(WORK, '%s_in.raw' % tag)
    if not os.path.exists(raw_in):
        continue
    mask = R.upscale_mask(R.read_mask(os.path.join(WORK, '%s_fuai.mask' % tag)), W, H)
    src = R.load_raw(raw_in, W, H)
    base = src[:, :, :3].astype(np.float32)
    for lv in LEVELS:
        ours, _ = R.run_core(raw_in, os.path.join(r'C:\btwork\live_check\scan', 'o.raw'),
                             W, H, float(lv))
        d = np.abs(ours[:, :, :3].astype(np.float32) - base).mean(axis=2)
        g = ours[:, :, :3].astype(np.float32).mean(axis=2)
        sg = src[:, :, :3].astype(np.float32).mean(axis=2)
        # 局部纹理强度分级（3x3 梯度的 σ 代理），用于平坦/纹理拆分
        lap = np.abs(4.0 * sg[1:-1, 1:-1] - sg[:-2, 1:-1] - sg[2:, 1:-1]
                     - sg[1:-1, :-2] - sg[1:-1, 2:])
        sel = mask[1:-1, 1:-1]
        flat = sel & (lap < 2.0)
        tex = sel & (lap > 6.0)
        e = res['levels'].setdefault(lv, {'chg': [], 'flat': [], 'tex': [], 'luma': []})
        e['chg'].append(float(d[mask].mean()))
        e['flat'].append(float(d[1:-1, 1:-1][flat].mean()) if flat.sum() > 500 else None)
        e['tex'].append(float(d[1:-1, 1:-1][tex].mean()) if tex.sum() > 500 else None)
        e['luma'].append(float(g[mask].mean() - sg[mask].mean()))

for lv, e in res['levels'].items():
    for k in ('chg', 'flat', 'tex', 'luma'):
        v = [x for x in e[k] if x is not None]
        e[k] = round(float(np.mean(v)), 4) if v else None
print(json.dumps(res, ensure_ascii=False))
