# -*- coding: utf-8 -*-
"""用修好的掩码重算 B 640 的：改动像素占比 + 逐 |h_mid| 分箱变化。"""
import numpy as np, struct, os

W, H = 640, 394
IND = r'C:\nama_e2e\ab_in'
FL = r'C:\nama_e2e\flick'

def load_mask(tag):
    d = open(os.path.join(FL, 'mask_%s.raw' % tag), 'rb').read()
    mw, mh = struct.unpack_from('<ii', d, 0); n = mw*mh
    return mw, mh, np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh, mw)

def y_of(p):
    a = np.frombuffer(open(p,'rb').read(), dtype=np.uint8).reshape(H,W,4)
    return (a[:,:,0].astype(np.float32)*299 + a[:,:,1].astype(np.float32)*587 +
            a[:,:,2].astype(np.float32)*114)/1000.0

def box(y, r):
    p = np.pad(y, r, mode='edge'); ii = p.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1,0),(1,0))); k = 2*r+1
    return (ii[k:,k:] - ii[:-k,k:] - ii[k:,:-k] + ii[:-k,:-k])/(k*k)

mw, mh, soft = load_mask('bx_m0')
yi = (np.arange(H)*mh//H).clip(0, mh-1); xi = (np.arange(W)*mw//W).clip(0, mw-1)
m = soft[np.ix_(yi, xi)]
face = m >= 200
files = sorted(f for f in os.listdir(IND) if f.endswith('.raw'))[:10]

# 改动占比（帧0）
a = y_of(os.path.join(FL,'nz_bx_m0_out','seq_000.raw'))
b = y_of(os.path.join(FL,'nz_bx_m1_out','seq_000.raw'))
d = np.abs(a-b)
print('脸内 %d px; 脸内改动>0.04 %.2f%%; 脸内平均|Δ| %.3f 级' %
      (face.sum(), 100.0*(d[face]>0.04).mean(), d[face].mean()))
print('mv=255 区(%d px) 改动>0.04 %.2f%%' % ((m==255).sum(), 100.0*(d[m==255]>0.04).mean()))

hm = np.abs(box(y_of(os.path.join(IND, files[0])),1) - box(y_of(os.path.join(IND, files[0])),3))
BINS = [0,0.25,0.5,0.75,1.0,1.5,2.0,3.0,4.0,6.0,10.0,1e9]
res = {}
for tag in ('bx_m0','bx_m1'):
    dd = os.path.join(FL, 'nz_%s_out' % tag)
    acc = np.zeros(len(BINS)-1); cnt = np.zeros(len(BINS)-1)
    for f in files:
        out = y_of(os.path.join(dd,f)); hf = np.abs(out - box(out,1))
        for i in range(len(BINS)-1):
            mm = face & (hm>=BINS[i]) & (hm<BINS[i+1])
            if mm.any(): acc[i] += hf[mm].sum(); cnt[i] += mm.sum()
    res[tag] = acc/np.maximum(cnt,1)
print('%-14s %-7s %-9s %-9s %-8s' % ('hm 区间','像素','m0 细频','m1 细频','变化'))
for i in range(len(BINS)-1):
    mm = face & (hm>=BINS[i]) & (hm<BINS[i+1]); n = int(mm.sum())
    if n < 200: continue
    a2, b2 = res['bx_m0'][i], res['bx_m1'][i]
    print('%-14s %-7d %-9.4f %-9.4f %+7.2f%%' %
          ('%.2f~%s'%(BINS[i], 'inf' if BINS[i+1]>1e8 else '%.2f'%BINS[i+1]), n, a2, b2, (b2/a2-1)*100))
