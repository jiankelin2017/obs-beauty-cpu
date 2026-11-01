# -*- coding: utf-8 -*-
"""模式0 与 3.0.16 的逐字节差异定位。"""
import os

import numpy as np

HERE = r'C:\legacy_e2e'
A = os.path.join(HERE, 'flick', 'nz_md_old316_out')
B = os.path.join(HERE, 'flick', 'nz_md_m0_out')

fa = sorted(f for f in os.listdir(A) if f.endswith('.raw'))
fb = sorted(f for f in os.listdir(B) if f.endswith('.raw'))
print('帧数 %d vs %d' % (len(fa), len(fb)))
tot = 0
for f in fa:
    pa, pb = os.path.join(A, f), os.path.join(B, f)
    if not os.path.exists(pb):
        print(f, 'MISSING in B')
        continue
    da = open(pa, 'rb').read()
    db = open(pb, 'rb').read()
    if len(da) != len(db):
        print(f, 'len differ', len(da), len(db))
        continue
    a = np.frombuffer(da, dtype=np.uint8)
    b = np.frombuffer(db, dtype=np.uint8)
    n = int((a != b).sum())
    if n:
        d = np.abs(a.astype(np.int16) - b.astype(np.int16))
        print('%-14s 差异字节 %7d (%.4f%%) 最大差 %d 总和 %d'
              % (f, n, 100.0 * n / a.size, d.max(), int(d.sum())))
        tot += n
print('合计差异字节', tot)
