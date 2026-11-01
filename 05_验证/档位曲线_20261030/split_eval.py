# -*- coding: utf-8 -*-
"""用「5×5 局部标准差」分类器（旧 flattex_eval 口径）复算产品与新版，
判定「产品只磨平坦区」这条结论到底成不成立。"""
import os
import sys
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
os.environ['BEAUTY_S3_BAND'] = '1'
os.environ['BEAUTY_S3_TAP25'] = '0'
os.environ['BEAUTY_S3_HALF'] = '1'
os.environ['BEAUTY_S3_LV_TABLE'] = os.environ.get('LV_TABLE', '1')

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
FRAMES = sys.argv[1:] or ['m00', 'm01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07']
SCAN = r'C:\btwork\live_check\scan'


def local_std(gray, k=2):
    pad = np.pad(gray, k, mode='edge')
    win = swv(pad, (2 * k + 1, 2 * k + 1))
    return win.std(axis=(-1, -2))


def change(a, b, reg):
    return float(np.abs(b[:, :, :3].astype(np.int16)
                        - a[:, :, :3].astype(np.int16))[reg].mean())


acc = {}
for tag in FRAMES:
    raw_in = os.path.join(R.WORK, '%s_in.raw' % tag)
    mask = R.upscale_mask(R.read_mask(os.path.join(R.WORK, '%s_fuai.mask' % tag)), W, H)
    src = R.load_raw(raw_in, W, H)
    gray = src[:, :, :3].astype(np.float32).mean(axis=2)
    sd = local_std(gray, 2)
    flat = mask & (sd < 2.0)
    tex = mask & (sd > 6.0)
    for lv in (25, 50, 75, 100):
        gp = os.path.join(SCAN, 'gold_%s_%03d.raw' % (tag, lv))
        if not os.path.exists(gp):
            continue
        gold = R.load_raw(gp, W, H)
        ours, _ = R.run_core(raw_in, os.path.join(SCAN, 'sp_o.raw'), W, H, float(lv))
        e = acc.setdefault(lv, {'sdk_f': [], 'our_f': [], 'sdk_t': [], 'our_t': [],
                                'fpct': [], 'tpct': []})
        e['sdk_f'].append(change(src, gold, flat))
        e['our_f'].append(change(src, ours, flat))
        e['sdk_t'].append(change(src, gold, tex))
        e['our_t'].append(change(src, ours, tex))
        e['fpct'].append(100.0 * flat.sum() / mask.sum())
        e['tpct'].append(100.0 * tex.sum() / mask.sum())

print('分类器：5x5 局部标准差  flat: σ<2   tex: σ>6   （8 帧均值）')
print('%-5s %8s %8s %7s | %8s %8s %7s' %
      ('档位', 'SDK平', '我平', '比', 'SDK纹', '我纹', '比'))
for lv in sorted(acc):
    e = acc[lv]
    sf, of = np.mean(e['sdk_f']), np.mean(e['our_f'])
    st, ot = np.mean(e['sdk_t']), np.mean(e['our_t'])
    print('%-5d %8.3f %8.3f %7.2f | %8.3f %8.3f %7.2f'
          % (lv, sf, of, of / sf, st, ot, ot / st))
    print('       SDK 平坦/纹理 %.2f   我方 %.2f   （面积占比 平 %.1f%% / 纹 %.1f%%）'
          % (sf / st, of / ot, np.mean(e['fpct']), np.mean(e['tpct'])))
