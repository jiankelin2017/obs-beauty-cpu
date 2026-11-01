# -*- coding: utf-8 -*-
import numpy as np, struct, os
from PIL import Image

def load(p):
    d = open(p, 'rb').read()
    mw, mh = struct.unpack_from('<ii', d, 0); n = mw * mh
    soft = np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh, mw)
    raw = np.frombuffer(d[8:8+n], dtype=np.uint8).reshape(mh, mw)
    return mw, mh, soft, raw

for tag, W, H, frm in [('gx_m0', 640, 394, 'ab_in/seq_000.raw'),
                       ('m0', 1074, 604, 'flick/nz_in/seq_000.raw')]:
    p = 'flick/mask_%s.raw' % tag
    if not os.path.exists(p):
        print('skip', tag); continue
    mw, mh, soft, raw = load(p)
    a = np.frombuffer(open(frm, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    bgr = a[:, :, :3].copy()
    yi = (np.arange(H) * mh // H).clip(0, mh - 1)
    xi = (np.arange(W) * mw // W).clip(0, mw - 1)
    s = soft[np.ix_(yi, xi)]
    si = s.astype(np.int16)
    edge = np.zeros((H, W), bool)
    edge[:-1] |= np.abs(np.diff(si, axis=0)) > 60
    edge[:, :-1] |= np.abs(np.diff(si, axis=1)) > 60
    bgr[edge] = [0, 255, 0]
    Image.fromarray(bgr[:, :, ::-1]).save('chk_mask_%s.png' % tag)
    ys, xs = np.nonzero(s >= 200)
    print(tag, 'mask', mw, 'x', mh, 'face bbox x', xs.min(), xs.max(),
          'y', ys.min(), ys.max(), 'ratio %.2f' % ((xs.max()-xs.min()+1)/(ys.max()-ys.min()+1)))
