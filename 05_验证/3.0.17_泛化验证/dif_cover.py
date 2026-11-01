# -*- coding: utf-8 -*-
"""检查：模式1相对模式0的改动，是否覆盖了「掩码脸内」的全部像素。
若大素材覆盖率~100% 而 B 素材只有 20%，说明 B 的掩码读取/几何有问题。"""
import numpy as np, struct, os, sys
FL = r'C:\nama_e2e\flick'
def y_of(p, W, H):
    a = np.frombuffer(open(p,'rb').read(), dtype=np.uint8).reshape(H,W,4)
    return (a[:,:,0].astype(np.float32)*299+a[:,:,1].astype(np.float32)*587+a[:,:,2].astype(np.float32)*114)/1000.0
def mask(tag, W, H):
    d = open(os.path.join(FL,'mask_%s.raw'%tag),'rb').read()
    mw, mh = struct.unpack_from('<ii', d, 0); n = mw*mh
    s = np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh,mw)
    yi=(np.arange(H)*mh//H).clip(0,mh-1); xi=(np.arange(W)*mw//W).clip(0,mw-1)
    return s[np.ix_(yi,xi)]
for name, (W,H), a_tag, b_tag in [('大素材 1074x604', (1074,604), 'rc_m0', 'rc_m1'),
                                  ('B 素材 640x394', (640,394), 'gx_m0', 'gx_m1'),
                                  ('B素材2x 1280x788', (1280,788), 'ax_m0', 'ax_m1')]:
    m = mask(a_tag, W, H)
    face = m >= 200
    for th, lab in [(255,'mv=255'), (200,'mv>=200'), (1,'mv>=1')]:
        pass
    a = y_of(os.path.join(FL,'nz_%s_out'%a_tag,'seq_000.raw'), W, H)
    b = y_of(os.path.join(FL,'nz_%s_out'%b_tag,'seq_000.raw'), W, H)
    d = np.abs(a-b)
    print('%-18s 掩码分布: =255 %.1f%%  200..254 %.1f%%  <200 %.1f%%'
          % (name, 100.0*(m==255).mean(), 100.0*((m>=200)&(m<255)).mean(), 100.0*(m<200).mean()))
    print('   脸内改动>0.04 的比例: %6.2f%%   脸内平均|Δ| %.3f 级'
          % (100.0*(d[face]>0.04).mean(), d[face].mean()))
    m255 = m == 255
    if m255.any():
        print('   mv=255 区改动>0.04 的比例: %6.2f%%  平均|Δ| %.3f 级'
              % (100.0*(d[m255]>0.04).mean(), d[m255].mean()))
