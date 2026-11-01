# -*- coding: utf-8 -*-
"""结构自适应回填的参数网格搜索。

在 base=256（细频带整体不变）下扫 flat × edge，看"平坦高频下降"与
"边缘对比上升"能不能同时拿到，以及代价（总细节、闪动）。

输出：flatHi（平坦区残留高频，↓好）、edgeC（边缘对比，↑好）、
      detail（总细节）、flick（闪动）、bg（背景改动，应≈0）
"""
import os
import subprocess
import sys

import numpy as np

HERE = r'C:\legacy_e2e'
sys.path.insert(0, HERE)
import nz_probe_dlldir as nz  # noqa: E402
import sweep_mode as sm      # noqa: E402

DLL = os.path.join(HERE, 'legacy_engine_test_317.dll')
PANEL = '0:50,4:50'


def run(tag, env_extra):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write('')
    env = dict(os.environ)
    env['BEAUTY_EXTRA_PARAMS_FILE'] = p
    env.pop('BEAUTY_SMOOTH_MODE', None)
    env.update({k: str(v) for k, v in env_extra.items()})
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import nz_probe_dlldir as nz; nz.run(r'%s', '%s', '%s')"
            % (HERE, DLL, tag, PANEL))
    r = subprocess.run([sys.executable, '-c', code], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print('  FAIL', tag, r.stderr[-200:])
        return False
    return True


def main():
    open(os.path.join(HERE, 'flick', 'nz_in', 'meta.txt'), 'w').write('5 10')
    grid = []
    for flat in (0, 90, 140, 190, 240):
        for edge in (0, 110, 200, 300):
            if flat == 0 and edge == 0:
                continue
            grid.append((flat, edge))
    tags = {}
    for flat, edge in grid:
        tag = 'g_f%03d_e%03d' % (flat, edge)
        if run(tag, {'BEAUTY_TEX_BASE': 256, 'BEAUTY_TEX_FLAT': flat,
                     'BEAUTY_TEX_EDGE': edge}):
            tags[tag] = (flat, edge)
            print('  %-16s flat=%-4d edge=%-4d' % (tag, flat, edge))

    base = sm.measure('md_m0')
    rows = []
    for tag, (flat, edge) in tags.items():
        m = sm.measure(tag)
        if m:
            rows.append((flat, edge, m))
    if not base:
        print('基线缺失')
        return

    hdr = ('%-5s %-5s %-9s %-9s %-9s %-9s %-9s'
           % ('flat', 'edge', '平坦高频', '边缘对比', '总细节', '闪动', '背景'))
    print('\n=== 基线（模式0）: 平坦高频 %.3f  边缘对比 %.3f  总细节 %.3f  闪动 %.3f'
          % (base['flatHi'], base['edgeC'], base['detail'], base['flick']))
    print(hdr)
    print('-' * len(hdr))
    for flat, edge, m in sorted(rows, key=lambda r: (r[0], r[1])):
        print('%-5d %-5d %-9.3f %-9.3f %-9.3f %-9.3f %-9.4f'
              % (flat, edge, m['flatHi'], m['edgeC'], m['detail'],
                 m['flick'], m['bg']))

    # 评分：平坦高频降幅 + 边缘对比升幅 - 闪动升幅权重
    print('\n=== 相对基线的变化率（%）===')
    best = []
    for flat, edge, m in sorted(rows, key=lambda r: (r[0], r[1])):
        d_flat = (m['flatHi'] / base['flatHi'] - 1) * 100
        d_edge = (m['edgeC'] / base['edgeC'] - 1) * 100
        d_fl = (m['flick'] / base['flick'] - 1) * 100
        print('flat=%-4d edge=%-4d  平坦 %+6.2f%%  边缘 %+6.2f%%  闪动 %+6.2f%%'
              % (flat, edge, d_flat, d_edge, d_fl))
        best.append((-d_flat + d_edge - max(0.0, d_fl), flat, edge))
    best.sort(reverse=True)
    print('\n综合最优（-平坦 + 边缘 - 闪动）：flat=%d edge=%d  得分 %.2f'
          % (best[0][1], best[0][2], best[0][0]))
    open(os.path.join(HERE, 'flick', 'nz_in', 'meta.txt'), 'w').write('5 60')


if __name__ == '__main__':
    main()
