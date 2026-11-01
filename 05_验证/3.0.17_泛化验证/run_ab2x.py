# -*- coding: utf-8 -*-
"""在 1280x788 的放大素材上跑模式 0/1 并同口径测量。"""
import os
import struct
import subprocess
import sys

import numpy as np

HERE = r'C:\nama_e2e'
IND = os.path.join(HERE, 'ab2x')
DLL = os.path.join(HERE, 'nama_engine_test_317.dll')
W, H = 1280, 788
PANEL = '0:50,4:50'


def run(tag, mode):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write('')
    env = dict(os.environ)
    env['NAMA_EXTRA_PARAMS_FILE'] = p
    env['NAMA_SMOOTH_MODE'] = str(mode)
    code = ("import sys; sys.path.insert(0, r'%s'); import nz_probe_dlldir as nz; "
            "nz.W, nz.H = %d, %d; nz.INDIR = r'%s'; "
            "nz.MARK = r'%s'; nz.run(r'%s', '%s', '%s')"
            % (HERE, W, H, IND, os.path.join(IND, 'meta.txt'), DLL, tag, PANEL))
    r = subprocess.run([sys.executable, '-c', code], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=900)
    print('  %-8s rc=%d %s' % (tag, r.returncode, r.stdout.strip()[:90]))
    return r.returncode == 0


def load_mask(tag):
    d = open(os.path.join(HERE, 'flick', 'mask_%s.raw' % tag), 'rb').read()
    mw, mh = struct.unpack_from('<ii', d, 0)
    n = mw * mh
    return mw, mh, np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh, mw)


def y_of(p):
    a = np.frombuffer(open(p, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return (a[:, :, 0].astype(np.float32) * 299 + a[:, :, 1].astype(np.float32) * 587 +
            a[:, :, 2].astype(np.float32) * 114) / 1000.0


def box(y, r):
    p = np.pad(y, r, mode='edge')
    ii = p.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1, 0), (1, 0)))
    k = 2*r+1
    return (ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]) / (k*k)


def measure(tag):
    d = os.path.join(HERE, 'flick', 'nz_%s_out' % tag)
    files = sorted(f for f in os.listdir(d) if f.endswith('.raw'))[:10]
    mw, mh, soft = load_mask(tag)
    yi = (np.arange(H) * mh // H).clip(0, mh-1)
    xi = (np.arange(W) * mw // W).clip(0, mw-1)
    mask = soft[np.ix_(yi, xi)]
    face = mask >= 200
    src0 = y_of(os.path.join(IND, files[0]))
    hm = np.abs(box(src0, 1) - box(src0, 3))
    flat = face & (hm <= 0.75)
    edge = face & (hm >= 4.0)
    fh, ec, dt, fl = [], [], [], []
    prev = None
    for f in files:
        out = y_of(os.path.join(d, f))
        hf = out - box(out, 1)
        fh.append(float(np.std(hf[flat])))
        ec.append(float(np.mean(np.abs(hf[edge]))))
        dt.append(float(np.std(out[face])))
        if prev is not None:
            fl.append(float(np.mean(np.abs(out[face] - prev[face]))))
        prev = out
    return dict(tag=tag, mw=mw, mh=mh, flatHi=np.mean(fh), edgeC=np.mean(ec),
                detail=np.mean(dt), flick=np.mean(fl),
                nflat=int(flat.sum()), nface=int(face.sum()))


def main():
    for tag, mode in (('ax_m0', 0), ('ax_m1', 1)):
        run(tag, mode)
    b = measure('ax_m0')
    c = measure('ax_m1')
    print('\nmask %dx%d, 脸内 %d px (%.1f%%), flat %d / edge-set %d'
          % (b['mw'], b['mh'], b['nface'], 100.0*b['nface']/(W*H),
             b['nflat'], int((b['nface']-b['nflat']))))
    print('%-6s %-9s %-9s %-9s %-9s' % ('组', '平坦高频', '边缘对比', '总细节', '闪动'))
    for m in (b, c):
        print('%-6s %-9.3f %-9.3f %-9.3f %-9.3f'
              % (m['tag'], m['flatHi'], m['edgeC'], m['detail'], m['flick']))
    print('变化  平坦 %+.2f%%  边缘 %+.2f%%  细节 %+.2f%%  闪动 %+.2f%%'
          % ((c['flatHi']/b['flatHi']-1)*100, (c['edgeC']/b['edgeC']-1)*100,
             (c['detail']/b['detail']-1)*100, (c['flick']/b['flick']-1)*100))


if __name__ == '__main__':
    main()
