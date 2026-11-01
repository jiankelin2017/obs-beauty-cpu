# -*- coding: utf-8 -*-
"""_ab_pool.py —— 持久线程池 vs 每次新建线程 的真实 A/B（单 DLL、单配置）

用法： python _ab_pool.py <dll> [blur] [n]
输出： 一行 JSON：{"dll":..,"blur":..,"min":..,"med":..,"p25":..,"n":..}
每次跑独立进程，避免两个 DLL 的全局状态互相干扰。
"""
import ctypes
import json
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = sys.argv[1]
if not os.path.isabs(DLL):
    DLL = os.path.join(HERE, DLL)
BLUR = float(sys.argv[2]) if len(sys.argv) > 2 else 95.0
REP = int(sys.argv[3]) if len(sys.argv) > 3 else 15

RAW = os.path.join(HERE, 'goldens', 'real', 'm00_in.raw')
TMP = os.path.join(HERE, '_ab_out_%d.raw' % os.getpid())
W, H = 1920, 1080

dll = ctypes.WinDLL(DLL)
dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_int, ctypes.c_double, ctypes.c_int,
                              ctypes.c_float, ctypes.c_float, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreRun.restype = ctypes.c_int
dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]

MSG = ctypes.create_string_buffer(512)
dll.BeautyCoreSetPerf(0, 1)          # 0 = 自动（8 线程上限）

for _ in range(6):                   # 预热：模型加载 + 缓冲分配 + 线程池建好
    dll.BeautyCoreRun(RAW.encode(), TMP.encode(), W, H, BLUR, 0,
                      0.0, 0.0, 1, MSG, 512)

vals = []
for _ in range(REP):
    dll.BeautyCoreRun(RAW.encode(), TMP.encode(), W, H, BLUR, 0,
                      0.0, 0.0, 1, MSG, 512)
    m = re.search(r'ms=([0-9.]+)', MSG.value.decode('ascii', 'replace'))
    if m:
        vals.append(float(m.group(1)))

os.remove(TMP) if os.path.exists(TMP) else None
vals.sort()
print(json.dumps({
    'dll': os.path.basename(DLL), 'blur': BLUR, 'n': len(vals),
    'min': round(vals[0], 2),
    'p25': round(vals[len(vals) // 4], 2),
    'med': round(statistics.median(vals), 2),
}))
