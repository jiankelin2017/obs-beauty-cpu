# -*- coding: utf-8 -*-
"""mouth_delta.py —— 量化「删嘴巴保护椭圆」对 legacy 输出的影响

背景：3.1.14 删掉了自创的嘴部保护椭圆。已实测确认它是**唯一**改动 legacy 输出的
改动（恢复它之后 legacy 哈希精确回到 b7fb312e / 4fb7a20e / 7e0fb6c7）。
本脚本把"删之前/删之后"两份输出存盘并逐像素对比，给出可判断的幅度。

用法：
    python mouth_delta.py on      # 嘴巴椭圆存在时跑一次
    python mouth_delta.py off     # 删掉之后跑一次
    python mouth_delta.py diff    # 对比两份
"""
import ctypes
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
SRC_PNG = os.path.join(HERE, 'goldens', 'src', 'face_src.png')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')

SIZES = [('640x394', 640, 394), ('720p', 1280, 720), ('1080p', 1920, 1080)]
BLUR = 50.0


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


def run(tag):
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]
    dll.BeautyCoreSetPerf.restype = None
    dll.BeautyCoreSetPerf(1, 0)          # 单线程、ROI 关，排除调度差异

    os.makedirs(OUT, exist_ok=True)
    for name, w, h, raw in prep():
        outp = os.path.join(OUT, '_mouth_%s_%s.raw' % (tag, name))
        msg = ctypes.create_string_buffer(512)
        for _ in range(5):               # 预热让掩码稳定
            dll.BeautyCoreRun(raw.encode('utf-8'), outp.encode('utf-8'),
                              w, h, BLUR, 0, 0.0, 0.0, 1, msg, 512)
        rc = dll.BeautyCoreRun(raw.encode('utf-8'), outp.encode('utf-8'),
                               w, h, BLUR, 0, 0.0, 0.0, 1, msg, 512)
        if rc != 0:
            print('[mouth] %s rc=%d msg=%s' % (name, rc, msg.value.decode('utf-8', 'ignore')))
            return 2
        print('  %-8s -> _mouth_%s_%s.raw' % (name, tag, name))
    print('[mouth] %s done' % tag)
    return 0


def diff():
    print('%-8s %-9s %-9s %-11s %-11s %-9s' %
          ('尺寸', '改动像素%', '最大差', '平均|Δ|', '>2 灰阶%', '>8 灰阶%'))
    for name, w, h in SIZES:
        a = np.fromfile(os.path.join(OUT, '_mouth_on_%s.raw' % name), np.uint8)
        b = np.fromfile(os.path.join(OUT, '_mouth_off_%s.raw' % name), np.uint8)
        a = a.reshape(h, w, 4)[..., :3].astype(np.int16)
        b = b.reshape(h, w, 4)[..., :3].astype(np.int16)
        d = np.abs(a - b)
        dm = d.max(axis=2)
        n = dm.size
        print('%-8s %-9.3f %-9d %-11.4f %-11.3f %-9.3f' %
              (name,
               (dm > 0).sum() / n * 100.0,
               int(dm.max()),
               d.mean(),
               (dm > 2).sum() / n * 100.0,
               (dm > 8).sum() / n * 100.0))
    print()
    print('说明：>2 灰阶 = 肉眼可能察觉；>8 灰阶 = 明显。')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1].lower()
    sys.exit(diff() if cmd == 'diff' else run(cmd))
