# -*- coding: utf-8 -*-
"""S2 磨皮核对拍 —— 拿 SDK 的平滑结果当目标，找自研保边平滑的参数。

思路：SDK 的磨皮档位 t 做的是 out = src + (S_sdk - src) * t（`bgraToRgbaBlend`）。
t=1 时 out 就等于 SDK 平滑核的完整输出 S_sdk —— 也就是
`goldens_legacy/flat/blur100_bt1/out.raw` 可以直接当**平滑核的真值**来比对。

于是对拍变得很干净：
    S_sdk  = 磨皮 100 档的输出（SDK 平滑核 + 它自己的皮肤区域限制）
    S_cand = 我们的保边平滑（引导滤波 / 表面模糊 / 双边）
    region = |S_sdk - src| > 4 的像素（SDK 真正动了的地方）
比较 region 内的 RMSE 与细节保留率，扫参数找最贴近的一组。

用法（系统 Python 3.12，需 numpy + cv2）：
    python smooth_compare.py           扫参数并出报告
"""

from __future__ import print_function

import json
import os
import time

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, 'goldens_legacy')      # 产品实际路径（region=off）
SRC = os.path.join(HERE, 'goldens', 'src')
OUT = os.path.join(HERE, 'goldens', 'masks')
W, H = 640, 394

SCENES = ['face_src', 'crop_c', 'crop_d', 'v_zoom15', 'v_zoom07', 'v_noise5',
          'v_dark', 'v_bright', 'v_skinbg']


# ---------------------------------------------------------------------------
# 保边平滑核
# ---------------------------------------------------------------------------
def box_blur(x, r):
    k = 2 * r + 1
    return cv2.boxFilter(x, -1, (k, k), normalize=True,
                         borderType=cv2.BORDER_REFLECT)


def guided_filter(rgb, r, eps):
    """引导滤波（Kaiming He 等，O(N) 与半径无关）。引导图用自身灰度。

    eps 是正则项：越小越贴合强边缘（保边越强），越大越接近普通均值模糊。
    返回与 rgb 同形状的 float32 平滑结果。
    """
    f = rgb.astype(np.float32) / 255.0
    I = (0.299 * f[:, :, 2] + 0.587 * f[:, :, 1] + 0.114 * f[:, :, 0])
    I = I.astype(np.float32)
    out = np.zeros_like(f)
    for c in range(3):
        p = f[:, :, c]
        mean_I = box_blur(I, r)
        mean_p = box_blur(p, r)
        corr_I = box_blur(I * I, r)
        corr_Ip = box_blur(I * p, r)
        var_I = corr_I - mean_I * mean_I
        cov_Ip = corr_Ip - mean_I * mean_p
        a = cov_Ip / (var_I + eps)
        b = mean_p - a * mean_I
        out[:, :, c] = box_blur(a, r) * I + box_blur(b, r)
    return np.clip(out * 255.0, 0, 255)


def surface_blur(rgb, r, thr):
    """Photoshop 式表面模糊：邻域内只平均「与中心亮度差小于 thr」的像素。

    纯 Python 实现用的是逐像素邻域筛选，640x394 会很慢（半径 5 → 约 2 秒/帧），
    只作参考实现，扫参数时用小半径。
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.int16)
    out = rgb.astype(np.float32).copy()
    h, w = gray.shape
    for y in range(0, h, 2):                      # 隔行采样加速（仅测量用）
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        for x in range(0, w, 2):
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            c = gray[y, x]
            nb = gray[y0:y1, x0:x1]
            m = np.abs(nb - c) <= thr
            if not m.any():
                continue
            out[y, x] = rgb[y0:y1, x0:x1][m].mean(axis=0)
    return out


def bilateral(rgb, d, sc, ss):
    return cv2.bilateralFilter(rgb, d, sc, ss)


# ---------------------------------------------------------------------------
# 指标
# ---------------------------------------------------------------------------
def detail(a):
    g = a.astype(np.float32)
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] \
        - g[1:-1, :-2] - g[1:-1, 2:]
    return float(np.abs(lap).mean()) / 3.0


def region_mask(src, sdk, thr=4):
    d = np.abs(src.astype(np.int16) - sdk.astype(np.int16)).max(axis=2)
    return d > thr


def compare_in(a, b, reg):
    """在 reg 区域内：RMSE、细节保留率（相对 a）。"""
    if reg.sum() == 0:
        return 0.0, 0.0, 0.0
    d = (a.astype(np.float32) - b.astype(np.float32))[reg]
    rmse = float(np.sqrt((d ** 2).mean()))
    da = detail(a[reg].reshape(-1, 1, 3)) if False else 0.0
    return rmse, 0.0, float(np.abs(d).mean())


def detail_in(img, reg):
    """区域内部的细节：只在 reg 像素上算 |Laplacian| 的均值。"""
    g = img.astype(np.float32)
    lap = np.zeros(g.shape[:2], np.float32)
    lap[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
                             - g[1:-1, :-2] - g[1:-1, 2:]).mean(axis=2) / 3.0
    return float(lap[reg].mean()) if reg.sum() > 0 else 0.0


# ---------------------------------------------------------------------------
def _load(p):
    return np.fromfile(p, np.uint8).reshape((H, W, 4))[:, :, :3].copy()


def cmd_curve(_a=None):
    """档位曲线匹配：SDK 的 0/25/50/75/100 五档 vs 候选核线性混合的同一组档位。

    「同档位观感一致」的判据不是某一档的 RMSE，而是**整条响应曲线**重合 ——
    用户拖滑块时看到的是曲线，不是单点。
    """
    src = _load(os.path.join(SRC, 'face_src.raw'))
    sdk100 = _load(os.path.join(GOLD, 'flat', 'blur100_bt1', 'out.raw'))
    reg = region_mask(src, sdk100)
    levels = [0, 25, 50, 75, 100]

    sdk_curve = []
    for d in levels:
        p = os.path.join(GOLD, 'flat', 'blur%03d_bt1' % d, 'out.raw')
        sdk_curve.append(detail_in(_load(p), reg) if os.path.exists(p) else float('nan'))
    d_src = detail_in(src, reg)
    sdk_keep = [100.0 * v / d_src for v in sdk_curve]
    print('[curve] SDK 区域细节保留%%: ' +
          '  '.join('%d档=%.1f' % (lv, k) for lv, k in zip(levels, sdk_keep)))

    cands = []
    for r in (2, 3, 4, 6, 8):
        for eps in (0.005, 0.01, 0.02, 0.04, 0.08):
            cands.append(('guided', 'r=%d eps=%s' % (r, eps),
                          guided_filter(src, r, eps)))
    for d in (5, 9, 12, 15, 18, 21):
        for sc in (25, 30, 35, 40, 45, 50):
            cands.append(('bilateral', 'd=%d sc=%d' % (d, sc),
                          bilateral(src, d, sc, d * 1.5).astype(np.float32)))

    best = None
    rows = []
    srcf = src.astype(np.float32)
    for kind, label, S in cands:
        Sf = S.astype(np.float32)
        keep = []
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            mix = np.clip(srcf + (Sf - srcf) * t, 0, 255).astype(np.uint8)
            keep.append(100.0 * detail_in(mix, reg) / d_src)
        err = float(np.sqrt(np.mean([(a - b) ** 2 for a, b in zip(keep, sdk_keep)])))
        rows.append({'kind': kind, 'label': label, 'keep': keep, 'err': err})
        if best is None or err < best['err']:
            best = rows[-1]
    rows.sort(key=lambda r: r['err'])

    md = ['# S2 档位曲线匹配：候选磨皮核 vs SDK\n',
          '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 素材 face_src，比较区域 = SDK 磨皮 100 档改动的像素（%.2f%%）'
          % (100.0 * reg.mean()),
          '',
          '| 档位 | SDK 保留% | 最佳候选保留% | 差 |',
          '|---|---|---|---|']
    for lv, k, c in zip(levels, sdk_keep, best['keep']):
        md.append('| %d | %.1f | %.1f | %+.1f |' % (lv, k, c, c - k))
    md.append('')
    md.append('最佳组合：**%s %s**，整条曲线的 RMSE = **%.2f 个百分点**\n'
              % (best['kind'], best['label'], best['err']))
    md.append('| 排名 | 算法 | 参数 | 曲线RMSE(百分点) |')
    md.append('|---|---|---|---|')
    for i, r in enumerate(rows[:12], 1):
        md.append('| %d | %s | %s | %.2f |' % (i, r['kind'], r['label'], r['err']))
    md.append('')
    md.append('> 判据：曲线 RMSE 越小，用户拖滑块时每一档看到的平滑程度越接近 SDK。'
              '小于约 2 个百分点基本看不出差别。')

    out = os.path.join(OUT, 'smooth_curve.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('\n'.join(md[5:]))
    print('[curve] -> %s' % out)


def main():
    os.makedirs(OUT, exist_ok=True)
    src_path = os.path.join(SRC, 'face_src.raw')
    sdk_path = os.path.join(GOLD, 'flat', 'blur100_bt1', 'out.raw')
    if not (os.path.exists(src_path) and os.path.exists(sdk_path)):
        print('[smooth] missing: %s or %s' % (src_path, sdk_path))
        return 2
    src = np.fromfile(src_path, np.uint8).reshape((H, W, 4))
    sdk = np.fromfile(sdk_path, np.uint8).reshape((H, W, 4))
    src_rgb = src[:, :, :3].copy()
    sdk_rgb = sdk[:, :, :3].copy()
    reg = region_mask(src_rgb, sdk_rgb)
    print('[smooth] SDK 改动区域 %.2f%%' % (100.0 * reg.mean()))
    d_src, d_sdk = detail_in(src_rgb, reg), detail_in(sdk_rgb, reg)
    print('[smooth] 区域细节  src=%.3f  sdk=%.3f  保留率=%.1f%%'
          % (d_src, d_sdk, 100.0 * d_sdk / max(d_src, 1e-6)))

    rows = []
    # 引导滤波：扫半径与 eps
    for r in (2, 3, 4, 6, 8):
        for eps in (0.01, 0.02, 0.04, 0.08, 0.16):
            t0 = time.time()
            cand = guided_filter(src_rgb, r, eps)
            ms = (time.time() - t0) * 1000
            rmse, _, mad = compare_in(cand, sdk_rgb, reg)
            dc = detail_in(cand, reg)
            rows.append({'kind': 'guided', 'r': r, 'eps': eps, 'rmse': rmse,
                         'mad': mad, 'detail': dc,
                         'keep': 100.0 * dc / max(d_src, 1e-6), 'ms': ms})
    # 双边滤波（cv2）
    for d in (5, 9, 15):
        for sc in (20, 40, 75):
            t0 = time.time()
            cand = bilateral(src_rgb, d, sc, d * 1.5)
            ms = (time.time() - t0) * 1000
            rmse, _, mad = compare_in(cand, sdk_rgb, reg)
            dc = detail_in(cand, reg)
            rows.append({'kind': 'bilateral', 'r': d, 'eps': sc, 'rmse': rmse,
                         'mad': mad, 'detail': dc,
                         'keep': 100.0 * dc / max(d_src, 1e-6), 'ms': ms})

    rows.sort(key=lambda x: x['rmse'])
    md = ['# S2 磨皮核对拍：自研保边平滑 vs SDK\n',
          '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 素材：face_src（640x394）　真值：SDK 磨皮 100 档输出（t=1 → 等于 SDK 平滑核）',
          '> 比较区域：SDK 真正改动的像素（|Δ|>4），占比 %.2f%%' % (100.0 * reg.mean()),
          '',
          '| 排名 | 算法 | 参数 | RMSE↓ | MAD | 区域细节 | 细节保留% | 耗时ms |',
          '|---|---|---|---|---|---|---|---|']
    for i, r in enumerate(rows[:20], 1):
        md.append('| %d | %s | r=%s eps=%s | %.3f | %.3f | %.3f | %.1f | %.1f |'
                  % (i, r['kind'], r['r'], r['eps'], r['rmse'], r['mad'],
                     r['detail'], r['keep'], r['ms']))
    md.append('')
    md.append('参考线：**SDK 自身** RMSE=0.000、区域细节 %.3f、保留率 %.1f%%。\n'
              % (d_sdk, 100.0 * d_sdk / max(d_src, 1e-6)))
    best = rows[0]
    md.append('最接近的是 **%s r=%s eps=%s**：RMSE %.3f、细节保留 %.1f%%（SDK 是 %.1f%%）。'
              % (best['kind'], best['r'], best['eps'], best['rmse'],
                 best['keep'], 100.0 * d_sdk / max(d_src, 1e-6)))
    md.append('')
    md.append('> 口径：RMSE / MAD 只在 SDK 改动区域内算（掩码外两边都是原图，'
              '算进去会把数字稀释）。细节保留率 = 区域内 |Laplacian| 相对原图的比例。')

    out = os.path.join(OUT, 'smooth_compare.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('\n'.join(md[6:]))
    print('[smooth] -> %s' % out)
    with open(os.path.join(OUT, 'smooth_compare.json'), 'w', encoding='utf-8') as f:
        json.dump({'sdk_detail': d_sdk, 'src_detail': d_src,
                   'region_pct': 100.0 * reg.mean(), 'rows': rows},
                  f, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'curve':
        sys.exit(cmd_curve() or 0)
    sys.exit(main())
