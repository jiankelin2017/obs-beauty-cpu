# -*- coding: utf-8 -*-
"""在 A 素材（掩码已确认对齐）上只加噪声，单独检验「绝对阈值是否被噪声击穿」。
素材 A 的 nz_in 本来就是 ±5 均匀噪声版；这里再生成 ±15 / ±30 两档。
"""
import os, random, struct, subprocess, sys
import numpy as np
from PIL import Image

HERE = r'C:\nama_e2e'
DLL = os.path.join(HERE, 'nama_engine_test_317.dll')
W, H = 1074, 604
BASE = os.path.join(HERE, 'out', 'frame_0.png')
COUNT = 10
PANEL = '0:50,4:50'

ADD = []
for a in range(256):
    row = bytearray(256)
    for b in range(256):
        v = a + b - 128
        row[b] = 0 if v < 0 else (255 if v > 255 else v)
    ADD.append(bytes(row))


def gen(noise):
    d = os.path.join(HERE, 'nz%02d' % noise)
    os.makedirs(d, exist_ok=True)
    im = Image.open(BASE).convert('RGBA')
    assert im.size == (W, H), im.size
    rgba = im.tobytes()
    rnd = random.Random(20261026 + noise)
    lo, hi = 128 - noise, 128 + noise
    SCALE = bytes(lo + (b * (2 * noise + 1)) // 256 for b in range(256))
    n = len(rgba)
    for k in range(COUNT):
        nz = rnd.randbytes(n).translate(SCALE)
        out = bytearray(n)
        for i in range(n):
            out[i] = ADD[rgba[i]][nz[i]]
        for i in range(3, n, 4):
            out[i] = rgba[i]
        open(os.path.join(d, 'seq_%03d.raw' % k), 'wb').write(bytes(out))
    open(os.path.join(d, 'meta.txt'), 'w').write('%d %d' % (noise, COUNT))
    return d


def run(tag, mode, indir):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write('')
    env = dict(os.environ)
    env['NAMA_EXTRA_PARAMS_FILE'] = p
    env['NAMA_SMOOTH_MODE'] = str(mode)
    code = ("import sys; sys.path.insert(0, r'%s'); import nz_probe_dlldir as nz; "
            "nz.INDIR = r'%s'; nz.MARK = r'%s'; nz.run(r'%s', '%s', '%s')"
            % (HERE, indir, os.path.join(indir, 'meta.txt'), DLL, tag, PANEL))
    r = subprocess.run([sys.executable, '-c', code], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=900)
    ok = r.returncode == 0
    print('   %-10s rc=%d' % (tag, r.returncode))
    return ok


def y_of(p):
    a = np.frombuffer(open(p, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return (a[:,:,0].astype(np.float32)*299 + a[:,:,1].astype(np.float32)*587 +
            a[:,:,2].astype(np.float32)*114)/1000.0


def box(y, r):
    p = np.pad(y, r, mode='edge'); ii = p.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1,0),(1,0))); k = 2*r+1
    return (ii[k:,k:] - ii[:-k,k:] - ii[k:,:-k] + ii[:-k,:-k])/(k*k)


def measure(tag, indir):
    d = os.path.join(HERE, 'flick', 'nz_%s_out' % tag)
    files = sorted(f for f in os.listdir(d) if f.endswith('.raw'))[:COUNT]
    md = open(os.path.join(HERE, 'flick', 'mask_%s.raw' % tag), 'rb').read()
    mw, mh = struct.unpack_from('<ii', md, 0); n = mw*mh
    soft = np.frombuffer(md[8+n:8+2*n], dtype=np.uint8).reshape(mh, mw)
    yi = (np.arange(H)*mh//H).clip(0, mh-1); xi = (np.arange(W)*mw//W).clip(0, mw-1)
    face = soft[np.ix_(yi, xi)] >= 200
    src0 = y_of(os.path.join(indir, files[0]))
    hm = np.abs(box(src0,1) - box(src0,3))
    flat = face & (hm <= 0.75); edge = face & (hm >= 4.0)
    fh, ec, dt, fl = [], [], [], []
    prev = None
    for f in files:
        out = y_of(os.path.join(d, f)); hf = out - box(out, 1)
        fh.append(float(np.std(hf[flat]))); ec.append(float(np.mean(np.abs(hf[edge]))))
        dt.append(float(np.std(out[face])))
        if prev is not None: fl.append(float(np.mean(np.abs(out[face]-prev[face]))))
        prev = out
    return dict(flatHi=np.mean(fh), edgeC=np.mean(ec), detail=np.mean(dt),
                flick=np.mean(fl), face=int(face.sum()), nflat=int(flat.sum()))


print('=== 加噪实验（素材 A，1074x604，10 帧，磨皮50/锐化50）===')
for noise in (15, 30):
    d = gen(noise)
    print(' noise ±%d' % noise)
    run('n%02d_m0' % noise, 0, d)
    run('n%02d_m1' % noise, 1, d)
    b = measure('n%02d_m0' % noise, d); c = measure('n%02d_m1' % noise, d)
    print('   m0 平坦 %.3f 边缘 %.3f 细节 %.3f 闪动 %.3f (脸内 %d, flat %d)'
          % (b['flatHi'], b['edgeC'], b['detail'], b['flick'], b['face'], b['nflat']))
    print('   m1 平坦 %.3f 边缘 %.3f 细节 %.3f 闪动 %.3f'
          % (c['flatHi'], c['edgeC'], c['detail'], c['flick']))
    print('   变化 平坦 %+.2f%%  边缘 %+.2f%%  细节 %+.2f%%  闪动 %+.2f%%'
          % ((c['flatHi']/b['flatHi']-1)*100, (c['edgeC']/b['edgeC']-1)*100,
             (c['detail']/b['detail']-1)*100, (c['flick']/b['flick']-1)*100))
