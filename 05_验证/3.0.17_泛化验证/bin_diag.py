# -*- coding: utf-8 -*-
"""逐 bin 诊断：按输入结构强度 hm 分箱，看 m0/m1 的细频带能量变化。
结论口径：
  低 hm 箱（平坦皮肤）  mean|hf| 应该 m1 < m0
  高 hm 箱（轮廓/睫毛） mean|hf| 应该 m1 > m0
若成立说明调制机制有效，分区域汇总的 "+4%" 只是分类口径问题。
"""
import numpy as np, struct, os, sys

W, H = 640, 394
IND = r'C:\nama_e2e\ab_in'
FL = r'C:\nama_e2e\flick'

def load_mask(tag):
    p = os.path.join(FL, 'mask_%s.raw' % tag)
    d = open(p, 'rb').read()
    mw, mh = struct.unpack_from('<ii', d, 0); n = mw * mh
    return mw, mh, np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh, mw)

def y_of(p):
    a = np.frombuffer(open(p, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return (a[:, :, 0].astype(np.float32) * 299 + a[:, :, 1].astype(np.float32) * 587 +
            a[:, :, 2].astype(np.float32) * 114) / 1000.0

def box(y, r):
    p = np.pad(y, r, mode='edge')
    ii = p.cumsum(0).cumsum(1); ii = np.pad(ii, ((1, 0), (1, 0)))
    k = 2*r+1
    return (ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]) / (k*k)

mw, mh, soft = load_mask(sys.argv[1] if len(sys.argv) > 1 else 'gx_m0')
yi = (np.arange(H)*mh//H).clip(0, mh-1); xi = (np.arange(W)*mw//W).clip(0, mw-1)
face = np.repeat(np.repeat(soft, 1, 0), 1, 1)[np.ix_(yi, xi)] >= 200

files = sorted(f for f in os.listdir(IND) if f.endswith('.raw'))[:12]
s0 = y_of(os.path.join(IND, files[0]))
hm = np.abs(box(s0, 1) - box(s0, 3))

# 分箱边界（灰度级）
BINS = [0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 10.0, 1e9]
res = {}
for tag in ('gx_m0', 'gx_m1'):
    d = os.path.join(FL, 'nz_%s_out' % tag)
    acc = np.zeros(len(BINS)-1); cnt = np.zeros(len(BINS)-1)
    for f in files:
        out = y_of(os.path.join(d, f))
        hf = np.abs(out - box(out, 1))
        for i in range(len(BINS)-1):
            m = face & (hm >= BINS[i]) & (hm < BINS[i+1])
            if m.any():
                acc[i] += hf[m].sum(); cnt[i] += m.sum()
    res[tag] = acc / np.maximum(cnt, 1)

tot = face.sum()
print('face px %d (%.1f%% of frame), 12 帧平均' % (tot, 100.0*tot/(W*H)))
print('%-14s %-8s %-9s %-9s %-8s' % ('hm 区间', '像素', 'm0 细频', 'm1 细频', '变化'))
for i in range(len(BINS)-1):
    m = face & (hm >= BINS[i]) & (hm < BINS[i+1])
    n = int(m.sum())
    if n < 200:
        continue
    a, b = res['gx_m0'][i], res['gx_m1'][i]
    print('%-14s %-8d %-9.4f %-9.4f %+7.2f%%  %s'
          % ('%.2f~%s' % (BINS[i], 'inf' if BINS[i+1] > 1e8 else '%.2f' % BINS[i+1]),
             n, a, b, (b/a-1)*100, '  ' if abs(n/tot) < 0.05 else ''))
