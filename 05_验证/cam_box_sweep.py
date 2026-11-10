# -*- coding: utf-8 -*-
"""真机尺度下扫 (boxRadius, boxIters) 网格。

背景（C19）：
    真机帧 1920x1080 / 脸宽 532px 上，core 50 档只削掉 4.9% 细纹理，
    SDK 削掉 23.9% —— 差约 5 倍。根因是 σ≈2px 是写死常量，
    相对尺度 2/532 = 0.38%，而 face_src 上是 2/111 = 1.8%（差 4.8 倍）。

    盒式滤波是 O(1)/像素（前缀和滑动窗），**增大 r 不增加计算量，
    只有 iters 线性增加**。所以优先走「大 r + 小 iters」。

用法：
    python cam_box_sweep.py sweep            # 全网格
    python cam_box_sweep.py line             # iters=2 一条线（快）
    python cam_box_sweep.py sdk              # SDK 基准曲线
    python cam_box_sweep.py one <r> <iters> <lvls...>   # 单组合

worker 模式（内部用，独立子进程，因为 g_cfg 进程内只解析一次）：
    python cam_box_sweep.py worker <r> <iters> <lvl1> <lvl2> ...
"""
import ctypes
import json
import os
import re
import subprocess
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import low_path_test as L  # noqa: E402
import region_gap as RG    # noqa: E402
import cam_frame_ab as CF  # noqa: E402

DEFAULT_SRC = CF.DEFAULT_SRC
TMP = CF.TMP
NAMES = ['额头', '鼻翼', '脸颊', '眼区']

# (r, iters) —— σ = sqrt(iters * ((2r+1)^2 - 1) / 12)
LINE = [(2, 2), (4, 2), (6, 2), (8, 2), (10, 2), (12, 2), (14, 2), (16, 2)]
GRID = LINE + [(6, 3), (6, 4), (8, 3), (8, 4), (10, 3), (12, 3), (5, 9), (16, 2)]
LEVELS = [30.0, 50.0, 80.0, 100.0]


def sigma(r, iters):
    return (iters * ((2 * r + 1) ** 2 - 1) / 12.0) ** 0.5


def prep():
    import cv2
    img = cv2.imread(DEFAULT_SRC, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit('读不出来: %s' % DEFAULT_SRC)
    h, w = img.shape[:2]
    box, score = CF.detect_face(img)
    rms = CF.masks(w, h, box)
    src_raw = os.path.join(TMP, '_cambox_src.raw')
    base_img = CF.to_rgba_raw(img, src_raw)
    base = CF.levels(base_img, rms)
    return w, h, box, rms, src_raw, base


def run_core_env(r, iters, src_raw, w, h, lvl, out_path):
    os.environ['BEAUTY_BOX_R'] = str(r)
    os.environ['BEAUTY_BOX_ITERS'] = str(iters)
    return CF.run_core(src_raw, w, h, lvl, out_path)


def pct(d, base):
    """保留率%（相对原图）"""
    return {n: [100.0 * d[n][i] / base[n][i] for i in range(3)] for n in NAMES}


def avg_bands(p):
    return [sum(p[n][i] for n in NAMES) / len(NAMES) for i in range(3)]


def parse_env(s):
    """'K=V;K=V' -> 写入 os.environ（必须在 DLL 首次调用前执行）"""
    if not s or s == '-':
        return
    for kv in s.split(';'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            os.environ[k] = v


def worker(r, iters, lvls, env=None):
    parse_env(env)
    w, h, box, rms, src_raw, base = prep()
    out = {'w': w, 'h': h, 'face_w': float(box[2]), 'data': {}, 'ms': {}}
    for lvl in lvls:
        img, ms = run_core_env(r, iters, src_raw, w, h, lvl,
                               os.path.join(TMP, '_cambox_c_%g.raw' % lvl))
        out['data']['%g' % lvl] = CF.levels(img, rms)
        out['ms']['%g' % lvl] = ms
    print('JSON:' + json.dumps(out))
    return out


def worker_diag(r, iters, env, lvls):
    """独立子进程：额外回报「实际改动幅度」，用于定位强度衰减卡在哪一层。"""
    parse_env(env)
    w, h, box, rms, src_raw, base = prep()
    src = np.fromfile(src_raw, dtype=np.uint8).reshape((h, w, 4))
    a = src[:, :, :3].astype(np.float64)
    lsrc = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    x0, y0 = int(box[0]), int(box[1])
    x1, y1 = int(box[0] + box[2]), int(box[1] + box[3])
    fm = np.zeros((h, w), bool)
    fm[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True

    def lum(img):
        b = img[:, :, :3].astype(np.float64)
        return 0.299 * b[:, :, 0] + 0.587 * b[:, :, 1] + 0.114 * b[:, :, 2]

    out = {'data': {}, 'ms': {}, 'diff': {}, 'cover': {}}
    for lvl in lvls:
        img, ms = run_core_env(r, iters, src_raw, w, h, lvl,
                               os.path.join(TMP, '_cambox_c_%g.raw' % lvl))
        d = np.abs(lum(img) - lsrc)
        out['data']['%g' % lvl] = CF.levels(img, rms)
        out['ms']['%g' % lvl] = ms
        out['diff']['%g' % lvl] = float(d[fm].mean())
        out['cover']['%g' % lvl] = float(100.0 * (d[fm] > 1).mean())
    # SDK 参照（同进程内 SDK 不受 core 配置影响）
    sdk = CF.run_sdk(src_raw, w, h, lvls[-1],
                     os.path.join(TMP, '_cambox_s_%g.raw' % lvls[-1]))
    d = np.abs(lum(sdk) - lsrc)
    out['sdk'] = {'data': CF.levels(sdk, rms),
                  'diff': float(d[fm].mean()),
                  'cover': float(100.0 * (d[fm] > 1).mean())}
    print('JSON:' + json.dumps(out))
    return out


def worker_sdk(lvls):
    w, h, box, rms, src_raw, base = prep()
    out = {'w': w, 'h': h, 'face_w': float(box[2]), 'data': {}}
    for lvl in lvls:
        img = CF.run_sdk(src_raw, w, h, lvl,
                         os.path.join(TMP, '_cambox_s_%g.raw' % lvl))
        out['data']['%g' % lvl] = CF.levels(img, rms)
    print('JSON:' + json.dumps(out))
    return out


def spawn(args):
    p = subprocess.run([sys.executable, os.path.join(HERE, 'cam_box_sweep.py')] + args,
                       capture_output=True, cwd=HERE)
    txt = p.stdout.decode('utf-8', 'replace')
    for line in txt.splitlines():
        if line.startswith('JSON:'):
            return json.loads(line[5:])
    sys.stderr.write(txt[-1500:] + '\n')
    sys.stderr.write(p.stderr.decode('utf-8', 'replace')[-1500:] + '\n')
    raise RuntimeError('worker 失败: %s' % args)


def norm_combo(c):
    """(r,it) 或 (r,it,env) → (r,it,env)"""
    return (c[0], c[1], c[2] if len(c) > 2 else '-')


def report(combos, levels=LEVELS, title=''):
    w, h, box, rms, src_raw, base = prep()
    print('素材: %s  %dx%d  脸宽 %.0fpx' % (os.path.basename(DEFAULT_SRC), w, h, box[2]))
    print('目标：让 core 的「细/中/阴」保留率贴近 SDK' + ('  [%s]' % title if title else ''))
    print()
    tgt_raw = spawn(['sdk'] + ['%g' % x for x in levels])
    tgt = {l: pct(tgt_raw['data'][l], base) for l in tgt_raw['data']}
    print('SDK 基准（保留率%，越低=削得越多）：')
    for l in levels:
        k = '%g' % l
        v = avg_bands(tgt[k])
        print('  档%-4g 细 %6.1f  中 %6.1f  阴 %6.1f' % (l, v[0], v[1], v[2]))
    print()

    l50 = min(levels, key=lambda x: abs(x - 50.0))
    l100 = max(levels)
    print('%-22s %6s | %-26s | %-20s %7s'
          % ('r,iters env', 'σ(px)', '档%g 细/中/阴 差' % l50,
             '档%g 细/中/阴 差' % l100, 'ms'))
    best = None
    for c in combos:
        r, it, env = norm_combo(c)
        res = spawn(['worker', str(r), str(it), env] + ['%g' % x for x in levels])
        cur = {l: pct(res['data'][l], base) for l in res['data']}
        cells = {}
        for l in levels:
            k = '%g' % l
            cv_, sv_ = avg_bands(cur[k]), avg_bands(tgt[k])
            cells[l] = [cv_[i] - sv_[i] for i in range(3)]
        ms = res['ms'].get('%g' % l100, -1)
        d50 = cells[l50]
        d100 = cells[l100]
        tag = '%d,%d %s' % (r, it, '' if env == '-' else env)
        print('%-22s %6.2f | %+6.1f %+6.1f %+6.1f    | %+6.1f %+6.1f %+6.1f    %7.1f'
              % (tag, sigma(r, it),
                 d50[0], d50[1], d50[2], d100[0], d100[1], d100[2], ms))
        score = sum(abs(cells[l][i]) for l in levels for i in (0, 1))
        if best is None or score < best[0]:
            best = (score, r, it, env, sigma(r, it), cells)
    print()
    print('综合最优（4档 × 细/中 绝对差之和最小）：')
    print('  r=%d iters=%d %s  σ=%.2fpx  σ/脸宽=%.4f  误差=%.1fpp'
          % (best[1], best[2], '' if best[3] == '-' else best[3],
             best[4], best[4] / box[2], best[0]))
    print('  当前默认 r=2 iters=2 σ=%.2fpx σ/脸宽=%.4f'
          % (sigma(2, 2), sigma(2, 2) / box[2]))
    for l in levels:
        print('    档%-4g 差 细 %+6.1f  中 %+6.1f  阴 %+6.1f'
              % (l, best[5][l][0], best[5][l][1], best[5][l][2]))
    return best


def sweep_mag():
    """扫 magHi（真机素材上方向与 face_src 相反：需要抬高而不是压低）"""
    combos = []
    for hi in (60, 80, 100, 140, 200, 300):
        combos.append((2, 2, 'BEAUTY_FREQ_MAG=6,%d' % hi))
    for hi in (100, 140, 200, 300):
        combos.append((8, 2, 'BEAUTY_FREQ_MAG=6,%d' % hi))
        combos.append((12, 2, 'BEAUTY_FREQ_MAG=6,%d' % hi))
    report(combos, title='magHi 扫描')


def sweep_grain():
    """扫颗粒回填 grain（它直接保护 1px 尺度，是细频带削不动的头号嫌疑）"""
    combos = []
    for g in ('0.00', '0.05', '0.10', '0.20'):
        combos.append((2, 2, 'BEAUTY_FREQ_GRAIN=%s' % g))
        combos.append((8, 2, 'BEAUTY_FREQ_GRAIN=%s' % g))
    report(combos, title='grain 扫描')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'line'
    if mode == 'worker':
        worker(int(sys.argv[2]), int(sys.argv[3]),
               [float(x) for x in sys.argv[5:]], sys.argv[4])
        return
    if mode == 'sdk':
        worker_sdk([float(x) for x in sys.argv[2:]] or LEVELS)
        return
    if mode == 'env':
        # python cam_box_sweep.py env <r> <iters> "K=V;K=V" [lvls...]
        report([(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])],
               [float(x) for x in sys.argv[5:]] or LEVELS)
        return
    if mode == 'one':
        report([(int(sys.argv[2]), int(sys.argv[3]))],
               [float(x) for x in sys.argv[4:]] or LEVELS)
        return
    if mode == 'diag':
        worker_diag(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4],
                      [float(x) for x in sys.argv[5:]] or [100.0])
        return
    if mode == 'mag':
        sweep_mag()
        return
    if mode == 'grain':
        sweep_grain()
        return
    if mode == 'sweep':
        report([norm_combo(c) for c in GRID])
        return
    report([norm_combo(c) for c in LINE])


if __name__ == '__main__':
    main()
