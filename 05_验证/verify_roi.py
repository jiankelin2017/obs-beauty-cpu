# -*- coding: utf-8 -*-
"""verify_roi.py —— 验证 ROI 裁剪与多线程不改变任何像素

必须成立的三条等价：
    (ROI 关, 1 线程) == (ROI 开, 1 线程)    ROI 裁剪不改结果
    (ROI 开, n 线程) == (ROI 开, 1 线程)    多线程不改结果

不成立就说明优化是靠画质换的，必须回退。
"""

import ctypes
import hashlib
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
SRC_PNG = os.path.join(HERE, 'goldens', 'src', 'face_src.png')
OUT = os.path.join(HERE, 'goldens', 'masks')

SIZES = [('640x394', 640, 394), ('720p', 1280, 720), ('1080p', 1920, 1080)]


def prep():
    os.makedirs(RES, exist_ok=True)
    im = Image.open(SRC_PNG).convert('RGB')
    out = []
    for name, w, h in SIZES:
        raw = os.path.join(RES, name + '.raw')
        if not (os.path.exists(raw) and os.path.getsize(raw) == w * h * 4):
            r = im.resize((w, h), Image.LANCZOS)
            rgba = np.dstack([np.asarray(r, np.uint8),
                              np.full((h, w, 1), 255, np.uint8)])
            rgba.tofile(raw)
        out.append((name, w, h, raw))
    return out


def main():
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]
    dll.BeautyCoreSetPerf.restype = None

    os.makedirs(OUT, exist_ok=True)
    cases = [('full_1t', 1, 0), ('roi_1t', 1, 1), ('roi_auto', 0, 1)]
    all_pass = True

    for name, w, h, raw in prep():
        hashes = {}
        bufs = {}
        for tag, threads, use_roi in cases:
            dll.BeautyCoreSetPerf(threads, use_roi)
            outp = os.path.join(OUT, '_verify_%s.raw' % name)
            msg = ctypes.create_string_buffer(512)
            # 预热 5 次让掩码稳定（每 4 帧重算一次，序列必须一致）
            for _ in range(5):
                dll.BeautyCoreRun(raw.encode('utf-8'), outp.encode('utf-8'),
                                  w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
            rc = dll.BeautyCoreRun(raw.encode('utf-8'), outp.encode('utf-8'),
                                   w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
            if rc != 0:
                print('[verify] %s %s rc=%d' % (name, tag, rc))
                return 3
            data = np.fromfile(outp, np.uint8)
            hashes[tag] = hashlib.sha256(data.tobytes()).hexdigest()[:16]
            bufs[tag] = data
            os.remove(outp)

        base = bufs['full_1t'].astype(np.int16)
        ok_roi = np.array_equal(bufs['roi_1t'], bufs['full_1t'])
        ok_mt = np.array_equal(bufs['roi_auto'], bufs['roi_1t'])
        diff_roi = int(np.abs(bufs['roi_1t'].astype(np.int16) - base).max()) if not ok_roi else 0
        diff_mt = int(np.abs(bufs['roi_auto'].astype(np.int16) - base).max()) if not ok_mt else 0
        print('  %-8s ROI %s (maxdiff=%d) | 多线程 %s (maxdiff=%d) | %s'
              % (name, 'PASS' if ok_roi else 'FAIL', diff_roi,
                 'PASS' if ok_mt else 'FAIL', diff_mt,
                 hashes['full_1t']))
        if not (ok_roi and ok_mt):
            all_pass = False

    print('[verify] %s' % ('ALL PASS' if all_pass else 'FAILED'))
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
