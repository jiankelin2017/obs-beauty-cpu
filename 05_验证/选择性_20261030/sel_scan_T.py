# -*- coding: utf-8 -*-
"""扫 T 对选择性（flat/tex 比）与总量的影响。一个 T 一个子进程。"""
import os
import json
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.environ.get('SEL_FRAMES', 'm00 m02 m04').split()
E = os.environ.get('SEL_E', '0.70')
IV = os.environ.get('SEL_I', '0.976')
TS = [float(x) for x in (sys.argv[1:] or ['5.0', '5.5', '6.0', '6.5', '7.0', '7.5', '8.3'])]

rows = []
for T in TS:
    env = dict(os.environ)
    env.update({'SEL_T': str(T), 'SEL_E': str(E), 'SEL_I': str(IV),
                'PYTHONIOENCODING': 'utf-8'})
    r = subprocess.run([sys.executable, os.path.join(HERE, 'sel_worker.py')] + FRAMES,
                       capture_output=True, text=True, env=env, encoding='utf-8',
                       errors='replace')
    line = [x for x in (r.stdout or '').splitlines() if x.startswith('JSON ')]
    if not line:
        print('T=%s 失败: %s' % (T, (r.stderr or '')[-300:]))
        continue
    d = json.loads(line[0][5:])
    rows.append(d)
    print('T=%-5g chg %6.3f  flat %6.3f  tex %6.3f  比 %5.2f  RMSE %5.3f  相关 %5.3f'
          % (d['T'], d['chg'], d['flat'], d['tex'], d['ratio'], d['rmse'], d['corr']))

json.dump(rows, open(os.path.join(HERE, 'scan', 'sel_T.json'), 'w'), indent=1)
print('\n目标（产品 3 帧同口径）：chg 1.908  flat 2.040  tex 1.472  比 1.39')
