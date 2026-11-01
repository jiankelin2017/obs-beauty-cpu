# -*- coding: utf-8 -*-
"""把 A 素材自己的掩码叠回 A 素材画面，核对对齐情况。"""
import numpy as np, struct, os
from PIL import Image
W, H = 1074, 604
FL = r'C:\nama_e2e\flick'
d = open(os.path.join(FL,'mask_rc_m0.raw'),'rb').read()
mw, mh = struct.unpack_from('<ii', d, 0); n = mw*mh
s = np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh,mw)
a = np.frombuffer(open('flick/nz_in/seq_000.raw','rb').read(), dtype=np.uint8).reshape(H,W,4)
bgr = a[:,:,:3].copy()
yi=(np.arange(H)*mh//H).clip(0,mh-1); xi=(np.arange(W)*mw//W).clip(0,mw-1)
f = s[np.ix_(yi,xi)]; si = f.astype(np.int16)
e = np.zeros((H,W),bool)
e[:-1] |= np.abs(np.diff(si,axis=0))>60
e[:,:-1] |= np.abs(np.diff(si,axis=1))>60
bgr[e] = [0,255,0]
Image.fromarray(bgr[:,:,::-1]).save('chk_mask_A.png')
ys,xs=np.nonzero(f>=200)
print('A 掩码 bbox x %d..%d (%.2f..%.2f) y %d..%d (%.2f..%.2f) 覆盖 %.1f%%'
      % (xs.min(),xs.max(),xs.min()/W,xs.max()/W,ys.min(),ys.max(),ys.min()/H,ys.max()/H,100.0*(f>=200).mean()))
# 掩码网格本身的长宽比 vs 帧长宽比
print('掩码网格 %dx%d (宽高比 %.2f)  帧 %dx%d (%.2f)' % (mw,mh,mw/mh,W,H,W/H))
