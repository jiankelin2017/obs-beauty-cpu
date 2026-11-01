# -*- coding: utf-8 -*-
"""泛化验证：在另一段素材（ab_in，640x394，不同人/不同光线）上复测磨皮模式。

做法：把探针模块的 W/H/INDIR 换成新素材与分辨率，其余逻辑完全不变，
保证与 1074x604 那组指标同口径。
"""
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = r'C:\nama_e2e'
sys.path.insert(0, HERE)
import nz_probe_dlldir as nz   # noqa: E402
import sweep_mode as sm        # noqa: E402

W2, H2 = 640, 394
INDIR = os.path.join(HERE, 'ab_in')
DLL = os.path.join(HERE, 'nama_engine_test_317.dll')
FRAMES = 12
RESULT = os.path.join(HERE, 'gen_result.txt')


def run(tag, panel, mode):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write('')
    env = dict(os.environ)
    env['NAMA_EXTRA_PARAMS_FILE'] = p
    env['NAMA_SMOOTH_MODE'] = str(mode)
    code = (
        "import sys; sys.path.insert(0, r'%s'); "
        "import nz_probe_dlldir as nz; "
        "nz.W, nz.H = %d, %d; "
        "nz.INDIR = r'%s'; "
        "nz.run(r'%s', '%s', '%s')"
        % (HERE, W2, H2, INDIR, DLL, tag, panel))
    r = subprocess.run([sys.executable, '-c', code], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=600)
    ok = r.returncode == 0
    if not ok:
        print('  FAIL', tag, r.stderr[-200:])
    return ok


def measure(tag):
    """与 sweep_mode.measure 同口径，但输入目录/分辨率可换。"""
    d = os.path.join(HERE, 'flick', 'nz_%s_out' % tag)
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.endswith('.raw'))[:sm.FRAMES]
    if not files:
        return None
    m = nz.load_mask(tag)
    if not m:
        return None
    mw, mh, soft = m
    soft = np.frombuffer(soft, dtype=np.uint8).reshape(mh, mw)
    yi = (np.arange(H2) * mh // H2).clip(0, mh - 1)
    xi = (np.arange(W2) * mw // W2).clip(0, mw - 1)
    mask = soft[np.ix_(yi, xi)]
    face = mask >= 200
    bgm = mask == 0

    def y_of(p):
        a = np.frombuffer(open(p, 'rb').read(), dtype=np.uint8)
        a = a.reshape(H2, W2, 4)
        return (a[:, :, 0].astype(np.float32) * 299 +
                a[:, :, 1].astype(np.float32) * 587 +
                a[:, :, 2].astype(np.float32) * 114) / 1000.0

    def box(y, r):
        p = np.pad(y, r, mode='edge')
        ii = p.cumsum(0).cumsum(1)
        ii = np.pad(ii, ((1, 0), (1, 0)))
        k = 2 * r + 1
        return (ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]) / (k * k)

    src0 = y_of(os.path.join(INDIR, files[0]))
    hm = np.abs(box(src0, 1) - box(src0, 3))
    flat = face & (hm <= 0.75)
    edge = face & (hm >= 4.0)

    flatHi, edgeC, detail, flick = [], [], [], []
    prev = None
    for f in files:
        src = y_of(os.path.join(INDIR, f))
        out = y_of(os.path.join(d, f))
        flatHi.append(float(np.std((out - box(out, 1))[flat])))
        edgeC.append(float(np.mean(np.abs((out - box(out, 1))[edge]))))
        detail.append(float(np.std(out[face])))
        if prev is not None:
            flick.append(float(np.mean(np.abs(out[face] - prev[face]))))
        prev = out
    return dict(tag=tag, flatHi=np.mean(flatHi), edgeC=np.mean(edgeC),
                detail=np.mean(detail), flick=np.mean(flick) if flick else 0.0,
                nflat=int(flat.sum()), nedge=int(edge.sum()))



def main():
    groups = [('gx_m0', '0:50,4:50', 0), ('gx_m1', '0:50,4:50', 1),
              ('gx_m2', '0:50,4:50', 2), ('gx_m3', '0:50,4:50', 3)]
    for tag, panel, mode in groups:
        ok = run(tag, panel, mode)
        print('  %-8s %s' % (tag, 'OK' if ok else 'FAIL'))
    base = measure('gx_m0')
    if not base:
        print('基线缺失（可能素材太小人脸检测失败）')
        return 1
    print('\n=== 另一素材（640x394，%d 帧）===' % FRAMES)
    print('%-8s %-9s %-9s %-9s %-9s' % ('组', '平坦高频', '边缘对比', '总细节', '闪动'))
    rows = []
    for tag, _, _ in groups:
        m = measure(tag)
        if not m:
            continue
        rows.append((tag, m))
        print('%-8s %-9.3f %-9.3f %-9.3f %-9.3f'
              % (tag, m['flatHi'], m['edgeC'], m['detail'], m['flick']))
    print('\n=== 相对人像磨皮的变化 ===')
    for tag, m in rows[1:]:
        print('%-8s 平坦 %+6.2f%%  边缘 %+6.2f%%  细节 %+6.2f%%  闪动 %+6.2f%%'
              % (tag,
                 (m['flatHi'] / base['flatHi'] - 1) * 100,
                 (m['edgeC'] / base['edgeC'] - 1) * 100,
                 (m['detail'] / base['detail'] - 1) * 100,
                 (m['flick'] / base['flick'] - 1) * 100))
    return 0


if __name__ == '__main__':
    sys.exit(main())
