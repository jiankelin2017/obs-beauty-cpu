# -*- coding: utf-8 -*-
"""bench_tone_fusion.py —— 同二进制测 BEAUTY_TONE_FUSION=0/1 的引擎耗时。

为什么不用 bench_core.py：它调 BeautyCoreRun 时面板色调三项全为 0，
toneColor 会直接早退，融合路径根本不会激活，测出来的两个 tag 必然同价。
本脚本显式下发非零色调（美白 45 / 红润 20 / 清晰 30），让两条路径都真正
跑满，再比 lastCoreMs()（引擎内部计时，不含读写 raw 的文件 IO）。

两点严谨性：
  1. 静态局部开关只在进程启动时读环境变量，所以 fusion 0/1 各起一个子进程；
     同时下发 BEAUTY_FUSION_DEBUG=1，用融合路径打印的一次标记反证开关生效。
  2. 同步路径每 5 帧有一次检测帧（约 +10ms 且与分辨率无关），会淹没差异，
     所以只统计「沿用帧」；再做 3 轮独立子进程，取差值中位数抵消系统噪声。
"""

import ctypes
import json
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks', '_fusion')

SIZES = [('640x394', 640, 394), ('720p', 1280, 720), ('1080p', 1920, 1080)]
WARM = 8
TOTAL = 60
CYCLE = 5
ROUNDS = 3


def child(fusion, rnd):
    os.makedirs(OUT, exist_ok=True)
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]
    dll.BeautyCoreSetTone.argtypes = [ctypes.c_double, ctypes.c_double]
    dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]

    dll.BeautyCoreSetTone(45.0, 20.0)
    dll.BeautyCoreSetClarityPanel(30.0)
    dll.BeautyCoreSetPerf(0, 1)          # 自动线程 + ROI，贴近生产

    msg = ctypes.create_string_buffer(512)
    result = {}
    for name, w, h in SIZES:
        raw = os.path.join(RES, name + '.raw')
        tmp = os.path.join(OUT, '_bench_f%d_r%d_%s.raw' % (fusion, rnd, name))
        for _ in range(WARM):
            dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                              w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        vals = []
        for k in range(TOTAL):
            j = WARM + k
            rc = dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                                   w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
            info = msg.value.decode('utf-8', 'replace')
            if rc != 0 or 'ms=' not in info:
                raise RuntimeError('run failed rc=%d msg=%s' % (rc, info))
            vals.append(dict(j=j, detect=(j % CYCLE == 0),
                             ms=float(info.split('ms=')[1].split()[0])))
        result[name] = vals
    with open(os.path.join(OUT, 'bench_f%d_r%d.json' % (fusion, rnd)), 'w') as f:
        json.dump(result, f)


def steady(vals):
    """只保留沿用帧（非检测帧）的均值与中位数。"""
    a = [v['ms'] for v in vals if not v['detect']]
    return (statistics.mean(a), statistics.median(a), len(a)) if a else (0, 0, 0)


def parent():
    marker = {0: False, 1: False}
    rounds = []
    for rnd in range(ROUNDS):
        data = {}
        for fusion in (0, 1):
            env = os.environ.copy()
            env['BEAUTY_TONE_FUSION'] = str(fusion)
            env['BEAUTY_ASYNC_DETECT'] = '0'
            env['BEAUTY_NO_PREWARM'] = '1'
            env['BEAUTY_FUSION_DEBUG'] = '1'
            r = subprocess.run([sys.executable, os.path.abspath(__file__),
                                '--child', str(fusion), str(rnd)],
                               env=env, capture_output=True, text=True,
                               timeout=900)
            if r.returncode != 0:
                print('[bench] child f=%d r=%d failed rc=%d' %
                      (fusion, rnd, r.returncode))
                print((r.stdout or '')[-800:])
                print((r.stderr or '')[-1200:])
                return 2
            marker[fusion] |= ('[WB_FUSION_ACTIVE]' in (r.stderr or ''))
            with open(os.path.join(OUT, 'bench_f%d_r%d.json' % (fusion, rnd))) as f:
                data[fusion] = json.load(f)
        rounds.append(data)

    print('FUSION_MARKER  f0=%s  f1=%s  (f0 should be False, f1 should be True)' %
          (marker[0], marker[1]))
    print('%-10s %9s %9s %14s %10s' %
          ('size', 'off_ms', 'on_ms', 'delta_by_round', 'median'))
    for name, _, _ in SIZES:
        offs, ons, deltas = [], [], []
        for d in rounds:
            a, _, na = steady(d[0][name])
            b, _, nb = steady(d[1][name])
            offs.append(a); ons.append(b); deltas.append(a - b)
        med = statistics.median(deltas)
        print('%-10s %9.2f %9.2f %14s %+9.2f ms (%+.1f%%)  n=%d/round' %
              (name, statistics.median(offs), statistics.median(ons),
               '/'.join('%+.2f' % x for x in deltas),
               med, 100.0 * med / statistics.median(offs),
               steady(rounds[0][0][name])[2]))
    return 0


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--child':
        child(int(sys.argv[2]), int(sys.argv[3]))
    else:
        sys.exit(parent())
