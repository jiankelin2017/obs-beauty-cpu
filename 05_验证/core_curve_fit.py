# -*- coding: utf-8 -*-
"""档位映射反解：探索「曲线形状差异」是核的问题还是映射的问题。

## 状态：假设，不是结论（2026-10-28）

本脚本用的是 **Laplacian |L| 均值**当细节指标。项目此前验证过的口径是
**16×16 块内 3×3 高通 std、取第 25 百分位（噪声地板）**
（见 `07_历史文档/COMPARE_3.0.19_vs_第三方.md` §3.7/§3.8）。

两种指标对「边缘」和「平坦区噪声」的权重完全不同：
- Laplacian 均值被强边缘主导 → SDK 保边强，曲线在高档位看起来"饱和"；
- 噪声地板只看平坦区 → 产品侧实测是**接近线性**的（50→86.1、75→76.7、100→68.6）。

所以本文里「SDK 档位映射是非线性的」**很可能只是换指标造成的假象**，
不能当结论用。要判定它，必须回到噪声地板口径重测一遍。

保留这个脚本的价值：它证明「同一份 S 换不同的 t 序列可以贴合任意一条目标曲线」——
也就是说单看 Laplacian 曲线无法区分「核弱」和「映射非线性」，指标本身分辨不了。

用法（系统 Python 3.12，需 numpy）：
    python core_curve_fit.py
"""

from __future__ import print_function

import ctypes
import json
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LEGACY = os.path.join(HERE, 'goldens_legacy')
SRC = os.path.join(HERE, 'goldens', 'src')
MASK_DIR = os.path.join(HERE, 'goldens', 'masks')
OUT = os.path.join(HERE, 'goldens', 'masks')
DLL = os.path.join(HERE, 'beauty_core_test.dll')
W, H = 640, 394
LEVELS = [0, 25, 50, 75, 100]
SCENE = 'face_src'

# 候选核：在皮肤区里扫出来的几组。半径固定 4 附近 ——
# σc=40 时半径越大反而越轻（双边本身的性质，cv2 复现同样现象）。
KERNELS = [
    (2, 7.0, 40.0),
    (4, 13.5, 55.0),
    (4, 13.5, 69.0),
    (4, 13.5, 80.0),
    (3, 10.0, 69.0),
    (5, 17.0, 69.0),
]


def load(p):
    return np.fromfile(p, np.uint8).reshape((H, W, 4))


def read_mask(p):
    raw = open(p, 'rb').read()
    mw, mh = np.frombuffer(raw[:8], np.int32)
    return np.frombuffer(raw[8:], np.uint8).reshape((mh, mw))


def upscale_mask(m):
    if m.shape == (H, W):
        return m > 127
    ys = (np.arange(H) * m.shape[0]) // H
    xs = (np.arange(W) * m.shape[1]) // W
    return m[ys][:, xs] > 127


def detail(img):
    g = img.astype(np.float32)
    lap = np.zeros(g.shape[:2], np.float32)
    lap[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
                             - g[1:-1, :-2] - g[1:-1, 2:]).mean(axis=2) / 3.0
    return lap


def run_core(dll, raw_in, raw_out, blur, radius, ss, sc, down=1):
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    msg = ctypes.create_string_buffer(512)
    return dll.BeautyCoreRun(raw_in.encode('utf-8'), raw_out.encode('utf-8'),
                             W, H, float(blur), int(radius), float(ss), float(sc),
                             int(down), msg, 512)


def main():
    if not os.path.exists(DLL):
        print('[fit] missing %s' % DLL)
        return 2
    dll = ctypes.WinDLL(DLL)
    os.makedirs(OUT, exist_ok=True)

    src_p = os.path.join(SRC, SCENE + '.raw')
    src = load(src_p)
    srcf = src[:, :, :3].astype(np.float32)

    # 区域：SDK 肤色掩码 ∩ 自研掩码。只用两边都认为该磨的地方，
    # 否则「自研没覆盖的那部分」会把保留率抬上去。
    fuai = upscale_mask(read_mask(os.path.join(MASK_DIR, SCENE + '_fuai.mask')))
    core_mask = upscale_mask(read_mask(os.path.join(MASK_DIR, SCENE + '_core.mask')))
    reg = fuai & core_mask
    d_src = float(detail(src[:, :, :3])[reg].mean())
    print('[fit] 区域 = fuai ∩ 自研掩码  %.2f%%' % (100.0 * reg.mean()))

    sdk = []
    for lv in LEVELS:
        s = load(os.path.join(LEGACY, 'flat', 'blur%03d_bt1' % lv, 'out.raw'))
        # float() 是必须的：numpy 2.x 里 float32 * python float 仍是 float32，
        # 直接进 json.dump 会报 not JSON serializable。
        sdk.append(float(100.0 * detail(s[:, :, :3])[reg].mean() / d_src))
    print('[fit] SDK   ' + ' '.join('%5.1f' % v for v in sdk))

    tgrid = np.arange(0.0, 1.0001, 0.01)
    rows = []
    for r, ss, sc in KERNELS:
        tmp = os.path.join(OUT, '_fit_s.raw')
        if run_core(dll, src_p, tmp, 100, r, ss, sc) != 0:
            print('[fit] r%d/ss%g/sc%g 跑不通' % (r, ss, sc))
            continue
        S = load(tmp)[:, :, :3].astype(np.float32)
        os.remove(tmp)

        # t → 保留率 对照表
        lut = []
        for t in tgrid:
            mix = np.clip(srcf + (S - srcf) * t, 0, 255).astype(np.uint8)
            lut.append(100.0 * detail(mix)[reg].mean() / d_src)
        lut = np.array(lut)

        # 反解每档的 t
        ts = []
        for target in sdk:
            ts.append(float(tgrid[int(np.argmin(np.abs(lut - target)))]))
        # 用反解出的 t 重算曲线（直接从 lut 取，避免重复混合）
        fit = [float(lut[int(np.argmin(np.abs(tgrid - t)))]) for t in ts]
        err_linear = float(np.sqrt(np.mean(
            [(lut[LEVELS[i]] - sdk[i]) ** 2 for i in range(len(LEVELS))])))
        err_fit = float(np.sqrt(np.mean([(a - b) ** 2 for a, b in zip(fit, sdk)])))
        rows.append({'r': r, 'ss': ss, 'sc': sc, 't': ts,
                     'fit': [round(v, 1) for v in fit],
                     'err_linear': round(err_linear, 2),
                     'err_fit': round(err_fit, 2)})
        print('  r%d/ss%-5g/sc%-3g  t=%s  拟合后=%s  RMSE 线性%.2f → 拟合%.2f'
              % (r, ss, sc, '/'.join('%.2f' % t for t in ts),
                 '/'.join('%.1f' % v for v in fit), err_linear, err_fit))

    rows.sort(key=lambda x: x['err_fit'])
    md = ['# 档位映射反解（**假设，未确认**）\n',
          '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 素材 %s %d×%d；区域 = SDK 肤色掩码 ∩ 自研掩码（%.2f%%）'
          % (SCENE, W, H, 100.0 * reg.mean()),
          '',
          '> ⚠️ 本表的指标是 **Laplacian |L| 均值**，不是项目验证过的**噪声地板**'
          '（16×16 块 · 3×3 高通 std · 第 25 百分位，见 COMPARE §3.7/§3.8）。',
          '> 两种指标对边缘/平坦区的权重不同，产品侧用噪声地板测出来是**接近线性**的'
          '（50→86.1、75→76.7、100→68.6）。',
          '> 所以下表的「反解 t」只能说明「换一组 t 也能贴合这条 Laplacian 曲线」，'
          '**不能推出 SDK 的档位映射是非线性的**。要判定必须用噪声地板口径重测。',
          '',
          '## SDK 基准曲线（区域细节保留 %）\n',
          '| 档位 | ' + ' | '.join(str(v) for v in LEVELS) + ' |',
          '|---|' + '---|' * len(LEVELS),
          '| SDK | ' + ' | '.join('%.1f' % v for v in sdk) + ' |',
          '',
          '## 反解结果（按拟合后 RMSE 排序）\n',
          '| 核 | 反解 t（0/25/50/75/100） | 拟合后曲线 | RMSE 线性 | RMSE 拟合 |',
          '|---|---|---|---|---|']
    for x in rows:
        md.append('| r%d / σs%g / σc%g | %s | %s | %.2f | **%.2f** |'
                  % (x['r'], x['ss'], x['sc'],
                     '/'.join('%.2f' % t for t in x['t']),
                     '/'.join('%.1f' % v for v in x['fit']),
                     x['err_linear'], x['err_fit']))
    md.append('')
    if rows:
        best = rows[0]
        md.append('**在这个指标下最贴合的是 r%d / σs%g / σc%g，反解 t = %s，'
                  'RMSE = %.2f 个百分点 —— 仅说明「存在一组 t 能贴合」，不代表 t 应该这么改。**'
                  % (best['r'], best['ss'], best['sc'],
                     ' / '.join('%.2f' % t for t in best['t']), best['err_fit']))
    md.append('')
    md.append('> 读法：「RMSE 线性」= 现在代码里的 t=档位/100；「RMSE 拟合」= 换成反解出的 t。')
    md.append('> 两者差得多，说明这个指标分辨不出「核强度」和「档位映射」两件事。')
    md.append('')
    md.append('> 局限：单素材 face_src、单帧；fuai 掩码本身是 192×256 放大来的，边界偏粗。')

    out = os.path.join(OUT, 'core_curve_fit.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('[fit] -> %s' % out)
    with open(os.path.join(OUT, 'core_curve_fit.json'), 'w', encoding='utf-8') as f:
        json.dump({'sdk': [round(v, 2) for v in sdk],
                   'region_pct': round(100.0 * reg.mean(), 2),
                   'rows': rows}, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
