# -*- coding: utf-8 -*-
"""bench_threads.py —— 1080p 真机帧：分项成本 + 线程数敏感度

回答两个问题：
  Q1 用户实际档位（磨皮95/美白55/红润55）下，引擎每帧到底多少毫秒？
  Q2 把线程数从 8 降到 4/2/1，成本怎么变？有没有「线程创建开销吃掉并行收益」？

口径：只认引擎自报 ms=（BeautyCoreRun 的 msg 里 ms=xx），wall clock 只作旁证。
      每档先预热 3 次（含模型加载与缓冲分配），再取 7 次最小值。

用法：
    python bench_threads.py
"""

import ctypes
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)          # 06_离线验证
DLL = os.path.join(EVAL, 'beauty_core_test.dll')
RAW = os.path.join(EVAL, 'goldens', 'real', 'm00_in.raw')
TMP = os.path.join(HERE, '_bench_out.raw')
W, H = 1920, 1080

dll = ctypes.WinDLL(DLL)
dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_int, ctypes.c_double, ctypes.c_int,
                              ctypes.c_float, ctypes.c_float, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreRun.restype = ctypes.c_int
dll.BeautyCoreSetTone.argtypes = [ctypes.c_double, ctypes.c_double]
dll.BeautyCoreSetDetail.argtypes = [ctypes.c_double, ctypes.c_double]
dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
dll.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]
dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]

MSG = ctypes.create_string_buffer(512)


def setup(threads, clarity=0.0, whiten=0.0, red=0.0, sharpen=0.0,
          gsharpen=0.0, regions=None):
    dll.BeautyCoreSetPerf(threads, 1)
    dll.BeautyCoreSetClarityPanel(clarity)
    dll.BeautyCoreSetTone(whiten, red)
    dll.BeautyCoreSetDetail(sharpen, gsharpen)
    for i, v in enumerate(regions or [0.0] * 5):
        dll.BeautyCoreSetRegion(i, v)


def run(blur, threads, **kw):
    setup(threads, **kw)
    for _ in range(3):
        dll.BeautyCoreRun(RAW.encode(), TMP.encode(), W, H, blur, 0,
                          0.0, 0.0, 1, MSG, 512)
    best, wbest = 1e9, 1e9
    for _ in range(7):
        t = time.perf_counter()
        dll.BeautyCoreRun(RAW.encode(), TMP.encode(), W, H, blur, 0,
                          0.0, 0.0, 1, MSG, 512)
        wall = (time.perf_counter() - t) * 1000.0
        m = re.search(r'ms=([0-9.]+)', MSG.value.decode('ascii', 'replace'))
        if m:
            best = min(best, float(m.group(1)))
        wbest = min(wbest, wall)
    return best, wbest


CASES = [
    ('磨皮 0（空面板透传）',      0.0,  dict()),
    ('磨皮 95（用户当前）',       95.0, dict()),
    ('磨皮 95 + 美白55/红润55',   95.0, dict(whiten=55.0, red=55.0)),
    ('磨皮 95 + 清晰 100',        95.0, dict(clarity=100.0)),
    ('磨皮 95 + 锐化 100',        95.0, dict(sharpen=100.0)),
    ('磨皮 95 + 全局锐化 100',    95.0, dict(gsharpen=100.0)),
    ('磨皮 95 + 五项区域 100',    95.0, dict(regions=[100.0] * 5)),
    ('11 项全 100（最坏情况）',   95.0, dict(clarity=100.0, whiten=100.0,
                                          red=100.0, sharpen=100.0,
                                          gsharpen=100.0, regions=[100.0] * 5)),
]
THREADS = [8, 4, 2, 1]


def main():
    if not os.path.exists(RAW):
        print('缺素材：%s' % RAW)
        return 1
    print('素材 %s (%dx%d)  面板下限=0 上限=100' % (os.path.basename(RAW), W, H))
    head = '%-28s' % '配置' + ''.join('%14s' % ('线程 %d' % t) for t in THREADS)
    print(head)
    print('-' * len(head))
    table = []
    for name, blur, kw in CASES:
        cells = []
        for th in THREADS:
            ms, wall = run(blur, th, **kw)
            cells.append((ms, wall))
        table.append((name, cells))
        print('%-28s' % name +
              ''.join('%6.2f/%5.2f' % (c[0], c[1]) for c in cells))

    print()
    print('读法：每格 = 引擎自报 ms / wall clock ms。')
    print('若 8 线程不比 2 线程快多少，说明线程创建+调度开销吃掉了并行收益。')

    md = ['# 1080p 分项成本 × 线程数（%s）\n' % time.strftime('%Y-%m-%d %H:%M'),
          '> 素材 goldens/real/m00_in.raw（1920×1080 真机帧）',
          '> 每格 = 引擎自报 ms / wall clock ms，各取 7 次最小值（预热 3 次）',
          '',
          '| 配置 | ' + ' | '.join('线程 %d' % t for t in THREADS) + ' |',
          '|---' * (len(THREADS) + 1) + '|']
    for name, cells in table:
        md.append('| %s | ' % name +
                  ' | '.join('%.2f / %.2f' % c for c in cells) + ' |')
    open(os.path.join(HERE, 'bench_threads.md'), 'w', encoding='utf-8').write(
        '\n'.join(md) + '\n')
    print('\n写出 %s' % os.path.join(HERE, 'bench_threads.md'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
