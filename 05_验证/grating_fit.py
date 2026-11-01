# -*- coding: utf-8 -*-
"""把 synth_grating.py 产出的 |H(f)| 曲线拟合成核宽，读各向异性与画幅缩放。

模型
----
端到端传递函数取「直通 + 一个高斯低通」的二项形式：

    H_eff(f) = a + b * exp(-2*pi^2 * sigma^2 * f^2)

a 是高频平台（管线里 0.3C 那一项的残余），b 是随频率衰减的那部分，
sigma 就是等效核在**像素**上的宽度。x / y 各自独立拟合，sigma_x / sigma_y
直接就是像素各向异性 —— 不需要任何 UV 假设。

对「核是否随画幅缩放」这个问题，sigma 随画幅的变化率就是答案：

    sigma ∝ W^0   -> 像素固定
    sigma ∝ W^1   -> UV 固定（核按 UV 半轴定义）

用法
----
    python grating_fit.py goldens/grating/*.json
"""
import glob
import json
import os
import sys

import numpy as np


def fit_curve(f, y):
    """三参数最小二乘：y = a + b*exp(-c*f^2)，c = 2*pi^2*sigma^2。

    用网格 + 线性最小二乘（给定 c，a/b 是线性的），避免依赖 scipy。
    """
    f = np.asarray(f, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    best = None
    for c in np.linspace(1.0, 3000.0, 3000):
        e = np.exp(-c * f * f)
        A = np.stack([np.ones_like(e), e], axis=1)
        # 最小二乘解 a + b*e
        sol, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ sol
        sse = float(((y - pred) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, c, sol[0], sol[1])
    sse, c, a, b = best
    sigma = np.sqrt(c / (2.0 * np.pi ** 2))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - sse / ss_tot if ss_tot > 0 else 0.0
    return {'a': a, 'b': b, 'sigma_px': float(sigma), 'r2': r2,
            'rmse': float(np.sqrt(sse / len(y)))}


def load_groups(paths):
    groups = []
    for p in paths:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        for g in d.get('groups', []):
            groups.append(g)
    return groups


def main():
    paths = sys.argv[1:]
    if not paths:
        paths = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       'goldens', 'grating', '*.json'))
    groups = load_groups(paths)
    if not groups:
        print('没有数据')
        return 1

    print('%-10s %-3s %-6s %8s %8s %8s %8s %7s'
          % ('画幅', 'bt', 'blur', 'σx(px)', 'σy(px)', 'σx/σy', 'R²(x)', '相位'))
    print('-' * 70)
    rows = []
    for g in groups:
        if 'size' not in g or 'rows' not in g:
            continue    # 早期版本 schema，跳过
        w, h = [int(x) for x in g['size'].split('x')]
        res = {}
        for o in ('x', 'y'):
            rs = sorted([r for r in g['rows'] if r['orient'] == o],
                        key=lambda r: r['f_px'])
            if len(rs) < 4:
                continue
            fit = fit_curve([r['f_px'] for r in rs], [r['mag'] for r in rs])
            res[o] = fit
        if 'x' not in res or 'y' not in res:
            continue
        sx, sy = res['x']['sigma_px'], res['y']['sigma_px']
        print('%-10s %-3d %-6d %8.2f %8.2f %8.3f %8.3f'
              % (g['size'], g['blur_type'], g['blur'],
                 sx, sy, sx / sy if sy else 0.0, res['x']['r2']))
        rows.append({'size': g['size'], 'w': w, 'h': h,
                     'blur_type': g['blur_type'], 'blur': g['blur'],
                     'sigma_x': sx, 'sigma_y': sy,
                     'aniso': sx / sy if sy else 0.0,
                     'r2_x': res['x']['r2'], 'r2_y': res['y']['r2'],
                     'a_x': res['x']['a'], 'b_x': res['x']['b']})

    if len(rows) > 1:
        print()
        print('画幅缩放律（同一 blur_type 下 σx 对 W 的幂指数）：')
        for bt in sorted(set(r['blur_type'] for r in rows)):
            sub = sorted([r for r in rows if r['blur_type'] == bt],
                         key=lambda r: r['w'])
            if len(sub) < 2:
                continue
            ws = np.array([r['w'] for r in sub], dtype=np.float64)
            ss = np.array([r['sigma_x'] for r in sub], dtype=np.float64)
            ok = ss > 0
            if ok.sum() < 2:
                continue
            k = float(np.polyfit(np.log(ws[ok]), np.log(ss[ok]), 1)[0])
            print('  bt=%d  %s  ->  σx ∝ W^%.2f   (0=像素固定, 1=UV 固定)'
                  % (bt, ', '.join('%dx%d:σ=%.2f' % (r['w'], r['h'],
                                                     r['sigma_x'])
                                   for r in sub), k))

    print()
    print('固定 UV 半轴的预测各向异性（σx/σy = (sx*W)/(sy*H)）：')
    for r in rows:
        pred = (0.002640845 * r['w']) / (0.0046875 * r['h'])
        print('  %-10s 预测 %.3f   实测 %.3f   %s'
              % (r['size'], pred, r['aniso'],
                 '一致' if abs(pred - r['aniso']) < 0.15 else '不一致'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
