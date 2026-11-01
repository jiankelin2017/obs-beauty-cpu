# -*- coding: utf-8 -*-
"""看 B 素材第 10 帧（bx_m1 运行末帧）的掩码是否还是窄条 —— 排除"首帧未收敛"。"""
import numpy as np, struct, os
from PIL import Image
W, H = 640, 394
def load(p):
    d = open(p,'rb').read(); mw, mh = struct.unpack_from('<ii', d, 0); n = mw*mh
    return mw, mh, np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh,mw)
mw, mh, s = load('mask_dump_010.raw')
print('末帧掩码覆盖 %.1f%%' % (100.0*(s>=200).mean()))
a = np.frombuffer(open(r'C:\nama_e2e\ab_in\seq_009.raw','rb').read(), dtype=np.uint8).reshape(H,W,4)
bgr = a[:,:,:3].copy()
yi=(np.arange(H)*mh//H).clip(0,mh-1); xi=(np.arange(W)*mw//W).clip(0,mw-1)
f = s[np.ix_(yi,xi)]; si=f.astype(np.int16)
e = np.zeros((H,W),bool)
e[:-1] |= np.abs(np.diff(si,axis=0))>60
e[:,:-1] |= np.abs(np.diff(si,axis=1))>60
bgr[e]=[0,255,0]
Image.fromarray(bgr[:,:,::-1]).save('chk_mask_B_frame10.png')
ys,xs=np.nonzero(f>=200)
print('bbox x %d..%d y %d..%d' % (xs.min(),xs.max(),ys.min(),ys.max()))
