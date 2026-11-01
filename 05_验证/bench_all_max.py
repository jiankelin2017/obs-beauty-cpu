# -*- coding: utf-8 -*-
"""
全参数负载基准（对应真机 20:24 那次「引擎 48ms」的复现尝试）
=============================================================

背景
----
2026-10-28 20:24 的真机日志里，720p 的「引擎」耗时从 13.88ms 一路爬到
48ms 并稳定成平台。用户确认是自己把「锐化 / 全局锐化 / 五项区域效果」
全部拉高所致。本脚本回答两个问题：

  Q1 离线能不能复现这个量级？（能 → 可以离线定位优化；不能 → 差异来自
     真机环境，必须加真机分项埋点）
  Q2 如果能，48ms 里哪几项是主要贡献者？

口径
----
只认引擎自报的 `ms=`。**不用 wall clock** —— 8MB 的 raw 读写会稳定污染
15ms 以上，历史上据此得出过「异步反而更慢」的错误结论（见 C10）。

用法
----
    python bench_all_max.py                # 默认 720p
    python bench_all_max.py 1080p          # 换素材

输出同时写入 `goldens/masks/bench_all_max.md`。
"""

import ctypes
import os
import re
import sys
import time

import numpy as np

import low_path_test as L

W_H = {'640x394': (640, 394), '720p': (1280, 720), '1080p': (1920, 1080)}
TAG = sys.argv[1] if len(sys.argv) > 1 else '720p'
W, H = W_H[TAG]

dll = ctypes.WinDLL(L.DLL)
dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_int, ctypes.c_double, ctypes.c_int,
                              ctypes.c_float, ctypes.c_float, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_int]
dll.BeautyCoreSetTone.argtypes = [ctypes.c_double, ctypes.c_double]
dll.BeautyCoreSetDetail.argtypes = [ctypes.c_double, ctypes.c_double]
dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
dll.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]

RAW = os.path.join(L.RES, '%s.raw' % TAG)
TMP = os.path.join(L.OUT, '_bench_all.raw')
MSG = ctypes.create_string_buffer(512)


def setup(blur, clarity=0.0, whiten=0.0, red=0.0,
          sharpen=0.0, gsharpen=0.0, regions=None):
    dll.BeautyCoreSetClarityPanel(clarity)
    dll.BeautyCoreSetTone(whiten, red)
    dll.BeautyCoreSetDetail(sharpen, gsharpen)
    r = regions or [0.0] * 5
    for i, v in enumerate(r):
        dll.BeautyCoreSetRegion(i, v)
    return blur


def run(blur, **kw):
    b = setup(blur, **kw)
    # 预热 3 次：第一次含模型加载与缓冲分配，不计入
    for _ in range(3):
        dll.BeautyCoreRun(RAW.encode(), TMP.encode(), W, H, b, 0,
                          0.0, 0.0, 1, MSG, 512)
    best = 1e9
    for _ in range(7):
        dll.BeautyCoreRun(RAW.encode(), TMP.encode(), W, H, b, 0,
                          0.0, 0.0, 1, MSG, 512)
        m = re.search(r'ms=([0-9.]+)', MSG.value.decode('ascii', 'replace'))
        if m:
            best = min(best, float(m.group(1)))
    return best


R5 = [100.0] * 5
# 逐层叠加：每加一层，增量就是那一层的成本
LAYERS = [
    ('磨皮 50（基线）',            dict()),
    ('+ 清晰 100',                 dict(clarity=100.0)),
    ('+ 美白/红润 100',            dict(clarity=100.0, whiten=100.0, red=100.0)),
    ('+ 锐化 100',                 dict(clarity=100.0, whiten=100.0, red=100.0,
                                        sharpen=100.0)),
    ('+ 全局锐化 100',             dict(clarity=100.0, whiten=100.0, red=100.0,
                                        sharpen=100.0, gsharpen=100.0)),
    ('+ 五项区域 100（全部拉满）', dict(clarity=100.0, whiten=100.0, red=100.0,
                                        sharpen=100.0, gsharpen=100.0,
                                        regions=R5)),
]

print()
print('素材 %s (%dx%d)' % (TAG, W, H))
print('%-30s %9s %9s' % ('配置', '引擎 ms', '增量'))
print('-' * 52)

rows = []
prev = None
for name, kw in LAYERS:
    ms = run(50.0, **kw)
    delta = '' if prev is None else '%+7.2f' % (ms - prev)
    rows.append((name, ms, delta))
    print('%-30s %9.2f %9s' % (name, ms, delta))
    prev = ms

# 单独看「磨皮 0 + 全特效」：磨皮关掉时 ROI 是否还成立，成本会不会塌
ms_noblur = run(0.0, clarity=100.0, whiten=100.0, red=100.0,
                sharpen=100.0, gsharpen=100.0, regions=R5)
print('%-30s %9.2f' % ('磨皮 0 + 全特效', ms_noblur))
rows.append(('磨皮 0 + 全特效', ms_noblur, ''))

FULL = rows[-2][1]
print()
print('结论口径：真机 720p 实测平台 48.05ms；离线全部拉满 %.2fms' % FULL)
print('离线/真机 = %.2f  —— 接近 1 说明可离线定位；远小于 1 说明差异来自'
      '真机环境（每帧检测 / 线程争用 / ROI 更大）' % (FULL / 48.05))

md = ['# 全参数负载基准（真机 48ms 复现尝试）\n',
      '> 自动生成：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
      '> 素材：goldens/res/%s.raw（%dx%d），磨皮固定 50 档，逐层叠加' % (TAG, W, H),
      '> 口径：引擎自报 `ms=`，取 7 次最小值；不用 wall clock（8MB I/O 会污染 15ms+）',
      '',
      '| 配置 | 引擎 ms | 增量 |',
      '|---|---|---|']
for name, ms, d in rows:
    md.append('| %s | %.2f | %s |' % (name, ms, d))
md += ['',
       '真机 20:24 日志（720p，参数拉满）引擎耗时平台 **48.05 ms**。',
       '离线全部拉满 **%.2f ms**，比值 **%.2f**。' % (FULL, FULL / 48.05),
       '',
       '比值接近 1 → 可离线定位优化；远小于 1 → 差异来自真机环境，'
       '需给真机加分项埋点（检测 / 磨皮 / 区域 / 锐化 各多少 ms）。']
out = os.path.join(L.OUT, 'bench_all_max.md')
with open(out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(md) + '\n')
print('\n写入 %s' % out)
