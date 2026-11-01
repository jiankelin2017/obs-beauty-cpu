# -*- coding: utf-8 -*-
"""磨皮模式 0~3 对比：分区域量化"干净度"与"立体感"。

指标（脸内拆成两个互斥子集，用与引擎相同的结构代理 hm = box3 - box7）：
  flat  区（hm <= 0.75 级）：皮肤平坦处 —— 越干净越好
      flatHi   = std(Y - box3)   平坦区残留高频（毛孔/噪点）↓ 好
      flatFlick= 帧间 mean|dY|   平坦区闪动 ↓ 好
  edge  区（hm >= 4.0 级）：五官边缘/睫毛 —— 越立体越好
      edgeC    = mean|Y - box3|  边缘对比幅度 ↑ 好
  all   区（整张脸）
      detail / flicker / clean  与既有脚本口径一致，便于和历史版本对齐
  bg：脸外 mean|out-src|，应≈0
"""
import os
import subprocess
import sys

import numpy as np

HERE = r'C:\legacy_e2e'
sys.path.insert(0, HERE)
import nz_probe_dlldir as nz  # noqa: E402

W, H = 1074, 604
PYEXE = sys.executable
DLL317 = os.path.join(HERE, 'legacy_engine_test_317.dll')
DLL316 = os.path.join(HERE, 'legacy_engine_test_316.dll')
META = os.path.join(HERE, 'flick', 'nz_in', 'meta.txt')
FRAMES = 10


def y_of(path):
    a = np.frombuffer(open(path, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return (a[:, :, 0].astype(np.float32) * 299 +
            a[:, :, 1].astype(np.float32) * 587 +
            a[:, :, 2].astype(np.float32) * 114) / 1000.0


def box(y, r):
    p = np.pad(y, r, mode='edge')
    ii = p.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return (ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]) / (k * k)


def run(tag, dll, panel, mode=None):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write('')
    env = dict(os.environ)
    env['BEAUTY_EXTRA_PARAMS_FILE'] = p
    if mode is not None:
        env['BEAUTY_SMOOTH_MODE'] = str(mode)
    else:
        env.pop('BEAUTY_SMOOTH_MODE', None)
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import nz_probe_dlldir as nz; nz.run(r'%s', '%s', '%s')"
            % (HERE, dll, tag, panel))
    r = subprocess.run([PYEXE, '-c', code], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0
    print('  %-10s %s' % (tag, 'OK' if ok else 'FAIL ' + r.stderr[-160:]))
    return ok


def measure(tag):
    d = os.path.join(HERE, 'flick', 'nz_%s_out' % tag)
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.endswith('.raw'))[:FRAMES]
    if not files:
        return None
    m = nz.load_mask(tag)
    if not m:
        return None
    mw, mh, soft = m
    soft = np.frombuffer(soft, dtype=np.uint8).reshape(mh, mw)
    yi = (np.arange(H) * mh // H).clip(0, mh - 1)
    xi = (np.arange(W) * mw // W).clip(0, mw - 1)
    mask = soft[np.ix_(yi, xi)]
    face = mask >= 200
    bgm = mask == 0

    src0 = y_of(os.path.join(HERE, 'flick', 'nz_in', files[0]))
    hm = np.abs(box(src0, 1) - box(src0, 3))
    flat = face & (hm <= 0.75)
    edge = face & (hm >= 4.0)

    flatHi, edgeC, detail, smooth, bg, clean = [], [], [], [], [], []
    prev = None
    flick, flatFlick = [], []
    for f in files:
        src = y_of(os.path.join(HERE, 'flick', 'nz_in', f))
        out = y_of(os.path.join(d, f))
        hf_s = src - box(src, 1)
        hf_o = out - box(out, 1)
        flatHi.append(float(np.std(hf_o[flat])))
        edgeC.append(float(np.mean(np.abs(hf_o[edge]))))
        detail.append(float(np.std(hf_o[face])))
        smooth.append(float(np.mean(np.abs(out[face] - src[face]))))
        bg.append(float(np.mean(np.abs(out[bgm] - src[bgm]))))
        e_s = float(np.mean(hf_s[face] ** 2))
        e_o = float(np.mean(hf_o[face] ** 2))
        clean.append(1.0 - (e_o / e_s if e_s > 1e-9 else 1.0))
        if prev is not None:
            flick.append(float(np.mean(np.abs(out[face] - prev[face]))))
            flatFlick.append(float(np.mean(np.abs(out[flat] - prev[flat]))))
        prev = out

    return dict(tag=tag, flatHi=np.mean(flatHi), edgeC=np.mean(edgeC),
                detail=np.mean(detail), smooth=np.mean(smooth),
                bg=np.mean(bg), clean=np.mean(clean) * 100,
                flick=np.mean(flick) if flick else 0.0,
                flatFlick=np.mean(flatFlick) if flatFlick else 0.0,
                nflat=int(flat.sum()), nedge=int(edge.sum()))


def main():
    open(META, 'w').write('5 %d' % FRAMES)
    groups = [
        ('md_old316', DLL316, '0:50,4:50', None),
        ('md_m0', DLL317, '0:50,4:50', 0),
        ('md_m1', DLL317, '0:50,4:50', 1),
        ('md_m2', DLL317, '0:50,4:50', 2),
        ('md_m3', DLL317, '0:50,4:50', 3),
    ]
    for g in groups:
        run(*g)

    rows = [r for r in (measure(g[0]) for g in groups) if r]
    hdr = ('%-10s %-8s %-8s %-8s %-8s %-8s %-8s %-8s'
           % ('组', '平坦高频', '边缘对比', '总细节', '干净度%', '闪动', '平坦闪动', '背景'))
    print('\n=== 指标（脸内 flat %d px / edge %d px）==='
          % (rows[0]['nflat'], rows[0]['nedge']))
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print('%-10s %-8.3f %-8.3f %-8.3f %-8.1f %-8.3f %-8.3f %-8.4f'
              % (r['tag'], r['flatHi'], r['edgeC'], r['detail'], r['clean'],
                 r['flick'], r['flatFlick'], r['bg']))

    # 逐位一致性校验：3.0.16 与模式 0 必须完全相同
    a = os.path.join(HERE, 'flick', 'nz_md_old316_out')
    b = os.path.join(HERE, 'flick', 'nz_md_m0_out')
    same = True
    for f in sorted(os.listdir(a)):
        if f.endswith('.raw'):
            if open(os.path.join(a, f), 'rb').read() != \
               open(os.path.join(b, f), 'rb').read():
                same = False
                break
    print('\n模式0 与 3.0.16 逐字节一致：%s' % ('是' if same else '否 <<<'))
    open(META, 'w').write('5 60')


if __name__ == '__main__':
    main()
