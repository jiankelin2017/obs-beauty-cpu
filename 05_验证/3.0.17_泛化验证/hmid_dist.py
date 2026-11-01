# -*- coding: utf-8 -*-
"""量两素材脸内的 |h_mid|（3~7px 带）分布，验证「噪点素材把结构判据整体抬高」
的假设。kTexLo=0.75 级 / kTexHi=4.00 级 是绝对阈值，与素材噪声无关。"""
import numpy as np, struct, os

FL = r'C:\nama_e2e\flick'

def y_of(p, W, H):
    a = np.frombuffer(open(p, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return (a[:,:,0].astype(np.float32)*299 + a[:,:,1].astype(np.float32)*587 +
            a[:,:,2].astype(np.float32)*114) / 1000.0

def box(y, r):
    p = np.pad(y, r, mode='edge')
    ii = p.cumsum(0).cumsum(1); ii = np.pad(ii, ((1,0),(1,0)))
    k = 2*r+1
    return (ii[k:,k:] - ii[:-k,k:] - ii[k:,:-k] + ii[:-k,:-k]) / (k*k)

def face_of(tag, W, H):
    d = open(os.path.join(FL,'mask_%s.raw'%tag),'rb').read()
    mw, mh = struct.unpack_from('<ii', d, 0); n = mw*mh
    s = np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh,mw)
    yi=(np.arange(H)*mh//H).clip(0,mh-1); xi=(np.arange(W)*mw//W).clip(0,mw-1)
    return s[np.ix_(yi,xi)] >= 200

for name, tag, (W,H), frm in [('A 1074x604 干净', 'rc_m0', (1074,604), 'flick/nz_in/seq_000.raw'),
                              ('B 640x394 噪点', 'gx_m0', (640,394), 'ab_in/seq_000.raw'),
                              ('B2x 1280x788',   'ax_m0', (1280,788), 'ab2x/seq_000.raw')]:
    face = face_of(tag, W, H)
    y = y_of(frm, W, H)
    hm = np.abs(box(y,1) - box(y,3))[face]
    q = np.percentile(hm, [10,25,50,75,90,95])
    # 判据命中率：t>0.5 的比例（即被判为"结构"的部分）
    t = np.clip((hm - 0.75) / (4.0 - 0.75), 0, 1)
    print('%-16s 脸内 %6d px  |h_mid| P10/25/50/75/90/95 = %s'
          % (name, face.sum(), ' '.join('%.2f'%v for v in q)))
    print('%18s t=0 比例 %.1f%%   t>=0.5 比例 %.1f%%   t=1 比例 %.1f%%'
          % ('', 100.0*(t==0).mean(), 100.0*(t>=0.5).mean(), 100.0*(t>=1).mean()))
