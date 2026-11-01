# -*- coding: utf-8 -*-
"""把 ab_in 的 640x394 素材 2x 双线性放大到 1280x788，用于验证「脸太小时
细频带装的是压缩噪声」这一假设：放大后脸宽 ~344px，接近 1074x604 素材。"""
import os
import numpy as np
from PIL import Image

SRC = r'C:\nama_e2e\ab_in'
DST = r'C:\nama_e2e\ab2x'
W, H = 640, 394
W2, H2 = 1280, 788
os.makedirs(DST, exist_ok=True)
files = sorted(f for f in os.listdir(SRC) if f.endswith('.raw'))[:10]
for f in files:
    a = np.frombuffer(open(os.path.join(SRC, f), 'rb').read(), dtype=np.uint8)
    a = a.reshape(H, W, 4)
    out = np.zeros((H2, W2, 4), np.uint8)
    for c in range(4):
        im = Image.fromarray(a[:, :, c]).resize((W2, H2), Image.BILINEAR)
        out[:, :, c] = np.asarray(im)
    open(os.path.join(DST, f), 'wb').write(out.tobytes())
open(os.path.join(DST, 'meta.txt'), 'w').write('5 %d' % len(files))
print('wrote %d frames %dx%d' % (len(files), W2, H2))
