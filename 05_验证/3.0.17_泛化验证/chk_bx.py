# -*- coding: utf-8 -*-
"""用修好的（B 素材自己的）掩码做目视核对：掩码到底落在画面的哪里。"""
import numpy as np, struct, os
from PIL import Image
W, H = 640, 394
FL = r'C:\nama_e2e\flick'
def load(tag):
    d = open(os.path.join(FL,'mask_%s.raw'%tag),'rb').read()
    mw, mh = struct.unpack_from('<ii', d, 0); n = mw*mh
    return mw, mh, np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh,mw)
mw, mh, s = load('bx_m0')
a = np.frombuffer(open(r'C:\nama_e2e\ab_in\seq_000.raw','rb').read(), dtype=np.uint8).reshape(H,W,4)
bgr = a[:,:,:3].copy()
yi=(np.arange(H)*mh//H).clip(0,mh-1); xi=(np.arange(W)*mw//W).clip(0,mw-1)
f = s[np.ix_(yi,xi)]
si = f.astype(np.int16)
e = np.zeros((H,W),bool)
e[:-1] |= np.abs(np.diff(si,axis=0))>60
e[:,:-1] |= np.abs(np.diff(si,axis=1))>60
bgr[e] = [0,255,0]
Image.fromarray(bgr[:,:,::-1]).save('chk_mask_bx.png')
ys,xs=np.nonzero(f>=200)
print('B 掩码 bbox x %d..%d y %d..%d' % (xs.min(),xs.max(),ys.min(),ys.max()))
# 同时把改动图也画出来
def y_of(p):
    q = np.frombuffer(open(p,'rb').read(), dtype=np.uint8).reshape(H,W,4)
    return (q[:,:,0].astype(np.float32)*299+q[:,:,1].astype(np.float32)*587+q[:,:,2].astype(np.float32)*114)/1000.0
d = np.abs(y_of(os.path.join(FL,'nz_bx_m0_out','seq_000.raw')) - y_of(os.path.join(FL,'nz_bx_m1_out','seq_000.raw')))
img = np.clip(d*30,0,255).astype(np.uint8)
rgb = np.dstack([bgr[:,:,::-1], img]).astype(np.uint8)
Image.fromarray(rgb).save('chk_bx_dif.png')
print('改动>0.5 级的像素 x %d..%d y %d..%d' % tuple([0,0,0,0]))
