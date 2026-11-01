# -*- coding: utf-8 -*-
"""扫 (T, e, gwp) 三维网格。T 缩放总量、e 补细节回填、gwp 定选择性。"""
import os
import json
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.environ.get('SEL_FRAMES', 'm00 m02 m04').split()
IV = os.environ.get('SEL_I', '0.976')
TS = [float(x) for x in os.environ.get('SEL_TS', '8.3').split(',')]
ES = [float(x) for x in os.environ.get('SEL_ES', '0.90,1.00').split(',')]
GS = [float(x) for x in os.environ.get('SEL_GS', '2.2,2.4,2.6').split(',')]

rows = []
print('%-6s %-5s %-5s %7s %7s %7s %6s %7s %7s' %
      ('T', 'e', 'gwp', 'chg', 'flat', 'tex', '比', 'RMSE', '相关'))
for T in TS:
    for E in ES:
        for G in GS:
            env = dict(os.environ)
            env.update({'SEL_T': str(T), 'SEL_E': str(E), 'SEL_I': str(IV),
                        'SEL_GWP': str(G), 'PYTHONIOENCODING': 'utf-8'})
            r = subprocess.run([sys.executable, os.path.join(HERE, 'sel_worker.py')] + FRAMES,
                               capture_output=True, text=True, env=env, encoding='utf-8',
                               errors='replace')
            line = [x for x in (r.stdout or '').splitlines() if x.startswith('JSON ')]
            if not line:
                print('T=%s e=%s g=%s 失败: %s' % (T, E, G, (r.stderr or '')[-200:]))
                continue
            d = json.loads(line[0][5:])
            d['gwp'] = G
            rows.append(d)
            print('%-6g %-5g %-5g %7.3f %7.3f %7.3f %6.2f %7.3f %7.3f'
                  % (d['T'], d['e'], G, d['chg'], d['flat'], d['tex'],
                     d['ratio'], d['rmse'], d['corr']))

json.dump(rows, open(os.path.join(HERE, 'scan', 'sel_grid3.json'), 'w'), indent=1)
print('\n目标（产品 3 帧同口径）：chg 1.908  flat 2.040  tex 1.472  比 1.39')
