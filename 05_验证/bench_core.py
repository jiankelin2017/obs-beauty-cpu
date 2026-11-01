# -*- coding: utf-8 -*-
"""bench_core.py —— CoreEngine 的 CPU 性能基线 / 优化后对比

测三档分辨率下 process() 的真实耗时，并区分「含检测帧」和「纯磨皮帧」：
掩码每 4 帧重算一次，两类帧的成本差一个数量级，混在一起算平均会看不出优化效果。

用法：
    python bench_core.py            # 跑基线
    python bench_core.py <tag>      # 跑并存成 bench_<tag>.json（用于前后对比）
"""

import ctypes
import json
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
SRC_PNG = os.path.join(HERE, 'goldens', 'src', 'face_src.png')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')

SIZES = [('640x394', 640, 394), ('720p', 1280, 720), ('1080p', 1920, 1080)]
REPEAT = 12


def ascii_path(p):
    """cv2 / ORT 读不了中文路径，这里只是给模型用的；raw 读写用 ACP 转换即可。"""
    return p


def prep():
    os.makedirs(RES, exist_ok=True)
    im = Image.open(SRC_PNG).convert('RGB')
    made = []
    for name, w, h in SIZES:
        raw = os.path.join(RES, name + '.raw')
        if os.path.exists(raw) and os.path.getsize(raw) == w * h * 4:
            made.append((name, w, h, raw))
            continue
        r = im.resize((w, h), Image.LANCZOS)
        rgba = np.dstack([np.asarray(r, np.uint8),
                          np.full((h, w, 1), 255, np.uint8)])
        rgba.tofile(raw)
        made.append((name, w, h, raw))
    return made


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else 'base'
    if not os.path.exists(DLL):
        print('[bench] missing %s (run build_core_test.bat)' % DLL)
        return 2
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int

    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, '_bench_out.raw')
    report = []

    for name, w, h, raw in prep():
        msg = ctypes.create_string_buffer(512)
        # 预热：让模型加载、内存分配、掩码初始化都完成
        for _ in range(3):
            dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                              w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        samples = []
        for _ in range(REPEAT):
            rc = dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                                   w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
            if rc != 0:
                print('[bench] rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
                return 3
            info = msg.value.decode('utf-8', 'replace')
            ms = float(info.split('ms=')[1].split()[0])
            faces = int(info.split('faces=')[1].split()[0])
            samples.append((ms, faces))

        vals = np.array([s[0] for s in samples])
        # 含检测的帧明显更慢：按 2 倍中位数切一刀，分开统计
        med = float(np.median(vals))
        det = [s[0] for s in samples if s[0] > med * 1.8]
        pure = [s[0] for s in samples if s[0] <= med * 1.8]
        row = {
            'res': name, 'w': w, 'h': h,
            'min': round(float(vals.min()), 2),
            'median': round(med, 2),
            'max': round(float(vals.max()), 2),
            'pure_med': round(float(np.median(pure)), 2) if pure else None,
            'detect_med': round(float(np.median(det)), 2) if det else None,
            'n_detect': len(det),
            'faces': samples[-1][1],
        }
        # 30fps 均摊：检测帧占 1/4（kMaskEvery=4）
        if row['pure_med'] is not None and row['detect_med'] is not None:
            row['amortized'] = round(row['pure_med'] * 0.75
                                     + row['detect_med'] * 0.25, 2)
        else:
            row['amortized'] = row['median']
        report.append(row)
        print('  %-8s 纯磨皮 %6s ms | 含检测 %6s ms | 30fps均摊 %6s ms | faces=%d'
              % (name, row['pure_med'], row['detect_med'],
                 row['amortized'], row['faces']))

    if os.path.exists(tmp):
        os.remove(tmp)

    md = ['# CoreEngine CPU 性能基线 —— %s\n' % tag,
          '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 磨皮 50 档，down=1（未降采样）\n',
          '| 分辨率 | 纯磨皮帧 | 含检测帧 | 30fps 均摊 | 预算余量(33ms) |',
          '|---|---|---|---|---|']
    for r in report:
        md.append('| %s | %s ms | %s ms | **%s ms** | %s |'
                  % (r['res'], r['pure_med'], r['detect_med'], r['amortized'],
                     '够' if r['amortized'] <= 33 else '超 %.1fx' % (r['amortized'] / 33.0)))
    md.append('')
    md.append('> 「纯磨皮帧」= 沿用上次掩码的帧；「含检测帧」= 重跑 YuNet 的帧'
              '（kMaskEvery=4，每 4 帧一次）。30fps 均摊按 3:1 加权。')

    out_md = os.path.join(OUT, 'bench_%s.md' % tag)
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    with open(os.path.join(OUT, 'bench_%s.json' % tag), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[bench] -> %s' % out_md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
