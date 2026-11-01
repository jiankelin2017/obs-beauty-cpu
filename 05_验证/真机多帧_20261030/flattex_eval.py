# -*- coding: utf-8 -*-
"""flattex_eval.py —— 真机多帧上的「平坦区 / 纹理区」改动量拆分。

定义（本脚本显式声明，便于复算）：
  在肤色掩码内，对**源图**灰度算 5x5 局部标准差 σ_local：
    flat  = σ_local < 2.0   （额头、脸颊这类没有结构的区域）
    tex   = σ_local > 6.0   （鼻翼、唇边、毛孔、发丝交界这类有结构的区域）
中间灰色地带不计入任何一类。
改动量 = mean(|out-src|)（三通道均值），与 real_frame_eval.change_in 同口径。
"""
import os, sys, glob
import numpy as np

# 环境变量必须在 beauty_core 首次 ensureReady 之前设好（g_cfg 只读一次），
# 否则拿到的是 DLL 内建默认（legacy / band=0 / T=14），不是 3.1.17 的配置。
os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
os.environ['BEAUTY_S3_BAND'] = '1'
os.environ['BEAUTY_S3_BT'] = '8.3'
os.environ['BEAUTY_S3_HALF'] = '1'
os.environ['BEAUTY_S3_TAP25'] = '0'

HERE = r'D:\插件\OBS美颜\06_离线验证'
sys.path.insert(0, HERE)
import real_frame_eval as R  # noqa

W, H, BLUR = 1920, 1080, 100.0


def local_std(gray, k=2):
    p = np.pad(gray.astype(np.float32), k, mode='edge')
    win = np.lib.stride_tricks.sliding_window_view(p, (2 * k + 1, 2 * k + 1))
    return win.std(axis=(-1, -2))


def change(a, b, reg):
    d = np.abs(b[:, :, :3].astype(np.float32) - a[:, :, :3].astype(np.float32)).mean(axis=2)
    return float(d[reg].mean())


def main():
    tags = sorted(glob.glob(os.path.join(R.WORK, 'm*_in.raw')))
    rows = []
    for p in tags:
        tag = os.path.basename(p).split('_in')[0]
        src = R.load_raw(p, W, H)
        gold = R.load_raw(R.gold_path(tag, -1), W, H)
        mask = R.upscale_mask(R.read_mask(os.path.join(R.WORK, '%s_fuai.mask' % tag)), W, H)
        tmp = os.path.join(R.WORK, '_ft_%s.raw' % tag)
        out, msg = R.run_core(p, tmp, W, H, BLUR)
        gray = src[:, :, :3].astype(np.float32).mean(axis=2)
        sd = local_std(gray, 2)
        flat = mask & (sd < 2.0)
        tex = mask & (sd > 6.0)
        r = dict(tag=tag,
                 flat_pct=100.0 * flat.sum() / max(mask.sum(), 1),
                 tex_pct=100.0 * tex.sum() / max(mask.sum(), 1),
                 sdk_flat=change(src, gold, flat), our_flat=change(src, out, flat),
                 sdk_tex=change(src, gold, tex), our_tex=change(src, out, tex))
        r['flat_ratio'] = r['our_flat'] / r['sdk_flat'] if r['sdk_flat'] else float('nan')
        r['tex_ratio'] = r['our_tex'] / r['sdk_tex'] if r['sdk_tex'] else float('nan')
        rows.append(r)
        print('%-4s 平坦 %.3f/%.3f (比 %.3f)  纹理 %.3f/%.3f (比 %.3f)  平坦占比 %.0f%%'
              % (tag, r['our_flat'], r['sdk_flat'], r['flat_ratio'],
                 r['our_tex'], r['sdk_tex'], r['tex_ratio'], r['flat_pct']))
    if rows:
        n = len(rows)
        print('\n均值：平坦 我们 %.3f / SDK %.3f (比 %.3f) | 纹理 我们 %.3f / SDK %.3f (比 %.3f)'
              % (np.mean([r['our_flat'] for r in rows]), np.mean([r['sdk_flat'] for r in rows]),
                 np.mean([r['flat_ratio'] for r in rows]),
                 np.mean([r['our_tex'] for r in rows]), np.mean([r['sdk_tex'] for r in rows]),
                 np.mean([r['tex_ratio'] for r in rows])))
        print('帧数 %d' % n)


if __name__ == '__main__':
    main()
