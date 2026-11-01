# -*- coding: utf-8 -*-
"""T 扫描 driver：串行调 worker，汇总成 CSV + JSON。"""
import json
import os
import subprocess
import sys

TS = [0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.2, 3.2, 4.5, 6.0, 8.3, 11.0, 16.0]
FRAMES = ['m00', 'm02', 'm04']
OUT = r'C:\btwork\live_check\scan'
os.makedirs(OUT, exist_ok=True)
rows = []
for t in TS:
    p = subprocess.run([sys.executable, r'C:\btwork\live_check\scan_T_worker.py',
                        str(t)] + FRAMES,
                       capture_output=True, text=True, encoding='utf-8')
    line = (p.stdout or '').strip().splitlines()
    if not line:
        print('FAIL T=%s  %s' % (t, (p.stderr or '')[-300:]))
        continue
    d = json.loads(line[-1])
    rows.append(d)
    lv = d['levels']
    print('T=%-5s  25:%7.3f 50:%7.3f 75:%7.3f 100:%7.3f | flat100 %6.3f tex100 %6.3f'
          % (t, lv['25']['chg'], lv['50']['chg'], lv['75']['chg'], lv['100']['chg'],
             lv['100']['flat'] or 0, lv['100']['tex'] or 0))
json.dump(rows, open(os.path.join(OUT, 'scan_T.json'), 'w'), indent=1)
print('\n->', os.path.join(OUT, 'scan_T.json'))
