# -*- coding: utf-8 -*-
"""
方案 A 扫参：找出「档位 → 低通尺度」的映射曲线
================================================

背景
----
真机对拍（cam_shot_ab.py）显示一个矛盾：我们整体细纹理削得比 SDK 多（50 档
多削 3.8pp），痘印却留得更多（C16：86.8% vs 83.5%）。合理解释是**尺度错配**：
我们的盒式低通 σ 固定 2.7mm，能量全花在毛孔级细纹理，够不到 2~5mm 的痘印。

根因在代码里：档位只算混合系数 t（beauty_core.cpp:764），boxRadius / boxIters
是常量（:218-219），低通算子永远传全强度 100。所以**档位拉满 σ 也不变**。

本脚本要回答
------------
对每个档位，分别用哪个 (boxRadius, boxIters) 能让 core 的「五区域 × 三频带
保留率」贴住 SDK？答案是每个档位一个组合 —— 连起来就是要写的联动曲线。

为什么必须起子进程
------------------
BEAUTY_BOX_R / BEAUTY_BOX_ITERS 是 g_cfg 在 ensureReady 里读一次的环境变量，
同一进程内改环境变量无效，所以每个组合要单独 spawn。

用法
----
    python box_sweep.py sdk 30 50 80 100      # 目标曲线（只需跑一次）
    python box_sweep.py core 3 4 30 50 80 100 # 单个组合
    python box_sweep.py sweep                 # 全网格（耗时较长）
    python box_sweep.py sweep --quick         # 只跑代表性组合
"""

import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS = [30.0, 50.0, 80.0, 100.0]

# (boxRadius, boxIters)。注释里是等效 sigma（像素）：
#   sigma^2 = iters * ((2r+1)^2 - 1) / 12
COMBOS_FULL = [
    # 第一轮只扫到 (2,2)=2.7mm 就以为到底了，结果 gap 随 sigma 单调上升，
    # 趋势指向更小的一侧 —— 补上 r=1 这一档（sigma 0.8~1.6px）。
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 6),
    (2, 2), (2, 3), (3, 2), (2, 4),
    (2, 6), (4, 2), (3, 4), (4, 3),
    (3, 6), (4, 4), (3, 8), (4, 6),
]
COMBOS_QUICK = [(1, 2), (1, 4), (2, 2), (3, 2), (2, 6), (3, 4), (3, 6), (3, 8)]

# 主指标只用「皮肤相关」的格子：四个区域的细纹理 + 中频。
# 排除唇与阴影频带的原因见 C14 —— 唇是保护策略差异（SDK 89.3% vs 我们 100.5%），
# 不是磨皮能力差异；把它算进来会主导平均值，掩盖我们要看的信号。
METRIC_REGIONS = ('额头', '鼻翼', '脸颊', '眼区')
METRIC_BANDS = (0, 1)


def sigma_px(r, iters):
    return (iters * ((2 * r + 1) ** 2 - 1) / 12.0) ** 0.5


def sigma_mm(r, iters):
    # 脸框 111.3px ≈ 15cm  ⇒ 1px ≈ 1.35mm（与 C16 同一换算）
    return sigma_px(r, iters) * 1.35


# -------------------------- worker --------------------------

def worker_core(r, iters, levels):
    os.environ['BEAUTY_BOX_R'] = str(r)
    os.environ['BEAUTY_BOX_ITERS'] = str(iters)
    os.environ['BEAUTY_LOW_PATH'] = '3'
    sys.path.insert(0, HERE)
    import region_gap as RG

    src = RG.L.load(RG.RAW, RG.W, RG.H)
    sb = RG.bands(src)
    rms = RG.region_masks()
    data = {}
    for lvl in levels:
        cur, ms = RG.run_core(lvl)
        cb = RG.bands(cur)
        row = {}
        for name, m in rms:
            vals = []
            for i in range(3):
                a = float(sb[i][m].mean())
                b = float(cb[i][m].mean())
                vals.append(100.0 * b / a if a > 1e-9 else None)
            row[name] = vals
        data['%g' % lvl] = {'bands': row, 'ms': ms}
    sys.stdout.write('JSON:' + json.dumps({'combo': [r, iters], 'data': data}) + '\n')


def worker_c2(envstr, levels):
    """任意环境变量组合的 worker。第一轮扫尺度发现高档位 gap 不是尺度问题
    （细纹理已对齐、中频与阴影被削过头），所以第二轮改扫幅度门控。"""
    for kv in envstr.split(';'):
        if not kv:
            continue
        k, v = kv.split('=', 1)
        os.environ[k] = v
    sys.path.insert(0, HERE)
    import region_gap as RG

    src = RG.L.load(RG.RAW, RG.W, RG.H)
    sb = RG.bands(src)
    rms = RG.region_masks()
    data = {}
    for lvl in levels:
        cur, ms = RG.run_core(lvl)
        cb = RG.bands(cur)
        row = {}
        for name, m in rms:
            vals = []
            for i in range(3):
                a = float(sb[i][m].mean())
                b = float(cb[i][m].mean())
                vals.append(100.0 * b / a if a > 1e-9 else None)
            row[name] = vals
        data['%g' % lvl] = {'bands': row, 'ms': ms}
    sys.stdout.write('JSON:' + json.dumps({'env': envstr, 'data': data}) + '\n')


def worker_img(envstr, level, outpath):
    """只跑一档、把结果 raw 写到 outpath。用于生成真机验证的离线参照图。

    为什么不直接在本进程里跑：核参数（g_cfg）是**进程首次使用时解析一次**
    并缓存的，同一进程内改 os.environ 不生效，所以每个组合必须独立进程。
    """
    for kv in envstr.split(';'):
        if not kv:
            continue
        k, v = kv.split('=', 1)
        os.environ[k] = v
    sys.path.insert(0, HERE)
    import region_gap as RG

    if envstr.startswith('SDK'):
        img = RG.run_sdk(level)
        ms = -1.0
    else:
        img, ms = RG.run_core(level)
    img.tofile(outpath)
    sys.stdout.write('JSON:' + json.dumps({'out': outpath, 'ms': ms}) + '\n')


def worker_sdk(levels):
    sys.path.insert(0, HERE)
    import region_gap as RG

    src = RG.L.load(RG.RAW, RG.W, RG.H)
    sb = RG.bands(src)
    rms = RG.region_masks()
    data = {}
    for lvl in levels:
        cur = RG.run_sdk(lvl)
        cb = RG.bands(cur)
        row = {}
        for name, m in rms:
            vals = []
            for i in range(3):
                a = float(sb[i][m].mean())
                b = float(cb[i][m].mean())
                vals.append(100.0 * b / a if a > 1e-9 else None)
            row[name] = vals
        data['%g' % lvl] = {'bands': row, 'ms': -1.0}
    sys.stdout.write('JSON:' + json.dumps({'combo': None, 'data': data}) + '\n')


# -------------------------- 主流程 --------------------------

def spawn(args):
    p = subprocess.run([sys.executable, os.path.join(HERE, 'box_sweep.py')] + args,
                       capture_output=True, cwd=HERE)
    txt = p.stdout.decode('utf-8', 'replace')
    for line in txt.splitlines():
        if line.startswith('JSON:'):
            return json.loads(line[5:])
    sys.stderr.write(txt[-2000:] + '\n')
    sys.stderr.write(p.stderr.decode('utf-8', 'replace')[-2000:] + '\n')
    raise RuntimeError('worker 失败: %s' % args)


def metric_gap(cur_bands, tgt_bands):
    """与 SDK 的平均绝对差（pp），只算皮肤相关的格子。"""
    diffs = []
    for rg in METRIC_REGIONS:
        for bi in METRIC_BANDS:
            a = tgt_bands[rg][bi]
            b = cur_bands[rg][bi]
            if a is None or b is None:
                continue
            diffs.append(abs(b - a))
    return sum(diffs) / len(diffs) if diffs else float('nan')


def metric_gap_all(cur_bands, tgt_bands):
    diffs = []
    for rg in cur_bands:
        for bi in range(3):
            a = tgt_bands[rg][bi]
            b = cur_bands[rg][bi]
            if a is None or b is None:
                continue
            diffs.append(abs(b - a))
    return sum(diffs) / len(diffs) if diffs else float('nan')


def fmt_row(bands):
    parts = []
    for rg in ('额头', '鼻翼', '唇', '脸颊', '眼区'):
        parts.append('%s %.0f/%.0f' % (rg, bands[rg][0], bands[rg][1]))
    return '  '.join(parts)


def band_gap(cur_bands, tgt_bands, bi):
    """某个频带上的平均有符号差（正 = 我们削得不够，负 = 我们削过头）。"""
    ds = []
    for rg in METRIC_REGIONS:
        a = tgt_bands[rg][bi]
        b = cur_bands[rg][bi]
        if a is None or b is None:
            continue
        ds.append(b - a)
    return sum(ds) / len(ds) if ds else float('nan')


def sweep_mag():
    """第二轮：扫幅度门控 freqMagLo / freqMagHi（环境里是 BEAUTY_FREQ_MAG=lo,hi）。

    动机：第一轮扫尺度发现，100 档时细纹理已经对齐（core 35.4 vs SDK 35.5），
    但中频我们削到 56.3 而 SDK 只削到 67.0（-10.7pp 过头）、阴影 -3.5pp。
    所以高档位的差距是「削过头」而不是「削不动」，应当抬门控下限把中等幅度
    的结构（皮肤起伏）保护起来，而不是继续加大尺度（那只会削得更多）。
    """
    levels = LEVELS
    print('档位：%s' % '/'.join('%g' % x for x in levels))
    tgt = spawn(['sdk'] + ['%g' % x for x in levels])['data']

    combos = []
    for lo in (6, 10, 15, 20, 25):
        for hi in (40, 60, 80, 120):
            if lo >= hi:
                continue
            combos.append((lo, hi))

    print('组合数：%d（固定 boxRadius=2 boxIters=2）\n' % len(combos))
    print('%-12s %8s %8s %8s %8s | %s'
          % ('magLo,magHi', 'gap30', 'gap50', 'gap80', 'gap100', '100档 细/中/阴 有符号差'))

    results = []
    for lo, hi in combos:
        env = 'BEAUTY_FREQ_MAG=%g,%g' % (lo, hi)
        res = spawn(['c2', env] + ['%g' % x for x in levels])
        res['mag'] = (lo, hi)
        results.append(res)
        gaps = [metric_gap(res['data']['%g' % l]['bands'], tgt['%g' % l]['bands'])
                for l in levels]
        b100 = res['data']['%g' % levels[-1]]['bands']
        t100 = tgt['%g' % levels[-1]]['bands']
        s = [band_gap(b100, t100, i) for i in range(3)]
        print('%-12s %8.2f %8.2f %8.2f %8.2f | %+6.1f %+6.1f %+6.1f'
              % ('%g,%g' % (lo, hi), gaps[0], gaps[1], gaps[2], gaps[3],
                 s[0], s[1], s[2]))

    print('\n每个档位的最优门控：')
    print('%-6s %-14s %8s %10s' % ('档位', '最优(lo,hi)', 'gap', '默认6,60'))
    for li, lvl in enumerate(levels):
        key = '%g' % lvl
        cands = sorted(results,
                       key=lambda x: metric_gap(x['data'][key]['bands'], tgt[key]['bands']))
        top = cands[0]
        base = [x for x in results if x['mag'] == (6, 60)][0]
        print('%-6g %-14s %7.2fpp %9.2fpp'
              % (lvl, '(%g,%g)' % top['mag'],
                 metric_gap(top['data'][key]['bands'], tgt[key]['bands']),
                 metric_gap(base['data'][key]['bands'], tgt[key]['bands'])))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    mode = sys.argv[1]

    if mode == 'core':
        worker_core(int(sys.argv[2]), int(sys.argv[3]),
                    [float(x) for x in sys.argv[4:]])
        return
    if mode == 'sdk':
        worker_sdk([float(x) for x in sys.argv[2:]])
        return
    if mode == 'c2':
        worker_c2(sys.argv[2], [float(x) for x in sys.argv[3:]])
        return
    if mode == 'mag':
        return sweep_mag()
    if mode == 'img':
        worker_img(sys.argv[2], float(sys.argv[3]), sys.argv[4])
        return

    levels = LEVELS
    combos = COMBOS_QUICK if '--quick' in sys.argv else COMBOS_FULL

    print('档位：%s' % '/'.join('%g' % x for x in levels))
    print('组合数：%d' % len(combos))
    print()

    print('[1/3] 取 SDK 目标曲线 ...')
    tgt = spawn(['sdk'] + ['%g' % x for x in levels])['data']
    print('%-6s %s' % ('SDK', ''))
    for lvl in levels:
        print('  磨皮%-4g %s' % (lvl, fmt_row(tgt['%g' % lvl]['bands'])))

    print('\n[2/3] 扫 core 网格（每组合一个子进程）...')
    results = []
    for i, (r, it) in enumerate(combos):
        res = spawn(['core', str(r), str(it)] + ['%g' % x for x in levels])
        res['sig'] = sigma_mm(r, it)
        results.append(res)
        gaps = [metric_gap(res['data']['%g' % l]['bands'], tgt['%g' % l]['bands'])
                for l in levels]
        print('  [%2d/%2d] r=%d it=%2d  sigma=%.1fmm  gap=%s  平均%.2fpp  %.1fms'
              % (i + 1, len(combos), r, it, res['sig'],
                 ' '.join('%.1f' % g for g in gaps),
                 sum(gaps) / len(gaps),
                 res['data']['%g' % levels[-1]]['ms']))

    print('\n[3/3] 每个档位的最优组合：')
    print('%-6s %-14s %8s %10s %10s' % ('档位', '最优(r,iters)', 'sigma', 'gap', '当前gap'))
    cur = None
    for res in results:
        if tuple(res['combo']) == (2, 2):
            cur = res
    best = {}
    for li, lvl in enumerate(levels):
        key = '%g' % lvl
        cands = sorted(results, key=lambda x: metric_gap(x['data'][key]['bands'],
                                                         tgt[key]['bands']))
        top = cands[0]
        g = metric_gap(top['data'][key]['bands'], tgt[key]['bands'])
        gc = metric_gap(cur['data'][key]['bands'], tgt[key]['bands']) if cur else float('nan')
        best[lvl] = top['combo']
        print('%-6g %-14s %7.1fmm %9.2fpp %9.2fpp'
              % (lvl, '(%d,%d)' % tuple(top['combo']), top['sig'], g, gc))

    print('\n建议的档位 → 尺度联动（待人工确认后再落代码）：')
    for lvl in levels:
        r, it = best[lvl]
        print('  磨皮 %-4g  boxRadius=%d boxIters=%d   (sigma=%.1fmm)'
              % (lvl, r, it, sigma_mm(r, it)))

    print('\nSDK 目标 vs 最优组合 逐格对比（细/中/阴影）：')
    for lvl in levels:
        key = '%g' % lvl
        r, it = best[lvl]
        top = [x for x in results if x['combo'] == [r, it]][0]
        print('  磨皮%-4g' % lvl)
        for rg in ('额头', '鼻翼', '唇', '脸颊', '眼区'):
            t = tgt[key]['bands'][rg]
            c = top['data'][key]['bands'][rg]
            print('    %-5s SDK %6.1f %6.1f %6.1f   core %6.1f %6.1f %6.1f   差 %+5.1f %+5.1f %+5.1f'
                  % (rg, t[0], t[1], t[2], c[0], c[1], c[2],
                     c[0] - t[0], c[1] - t[1], c[2] - t[2]))


if __name__ == '__main__':
    main()
