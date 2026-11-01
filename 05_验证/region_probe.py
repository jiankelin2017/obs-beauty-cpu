# -*- coding: utf-8 -*-
"""region_probe —— 摸清 SDK 那 5 个人脸局部项到底做什么。

为什么要先做这一步：core 引擎剩下的 5 项（五官立体 / 亮眼 / 去黑眼圈 /
去法令纹 / 祛斑痘）在 `goldens/` 里**没有任何基线**（78 组只覆盖磨皮、
美白、红润、锐化、清晰）。没有参照就实现，等于凭想象写算法，
"不降低画质"这条底线无从验证。

所以先用还能跑的 SDK（ref_golden.dll）现场采一遍：固定磨皮 50，
逐个把参数拉到 50 / 100，跟"同一档磨皮但该项为 0"的输出相减 ——
差值图就是这一项的真实作用域与作用方向。

输出：每项的变化像素数、包围盒、亮度变化均值/极值、变亮与变暗像素比例。
用法：
    python region_probe.py            # 全 5 项
    python region_probe.py 7 100      # 只跑某一项某一档
"""

from __future__ import print_function

import ctypes
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

W, H = 640, 394
P_BLUR, P_CLARITY, P_WHITEN, P_RED, P_SHARPEN, P_GLOBAL_SHARP, \
    P_THREED, P_EYEBRIGHT, P_POUCH, P_NASOLABIAL, P_DELSPOT = range(11)
P_COUNT = 11

NAMES = {
    P_THREED: '五官立体 face_threed',
    P_EYEBRIGHT: '亮眼 eye_bright',
    P_POUCH: '去黑眼圈 remove_pouch',
    P_NASOLABIAL: '去法令纹 nasolabial',
    P_DELSPOT: '祛斑痘 delspot',
}

DLL = os.path.join(HERE, 'ref_golden.dll')
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')
SRC = os.path.join(HERE, 'goldens', 'src')
TMP = os.path.join(HERE, 'goldens', '_probe')
RAW = os.path.join(HERE, 'goldens', 'res', '640x394.raw')


def load_dll():
    d = ctypes.WinDLL(DLL)
    d.RefGoldenRun.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(ctypes.c_double), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    return d


def load(path):
    a = np.fromfile(path, dtype=np.uint8)
    if a.size != W * H * 4:
        raise IOError('%s: %d bytes' % (path, a.size))
    return a.reshape((H, W, 4))


def panel(**kw):
    p = [0.0] * P_COUNT
    p[P_BLUR] = kw.get('blur', 50.0)
    for k, v in kw.items():
        if k == 'blur':
            continue
        p[{'threed': P_THREED, 'eye': P_EYEBRIGHT, 'pouch': P_POUCH,
           'naso': P_NASOLABIAL, 'spot': P_DELSPOT}[k]] = v
    return p


def run(dll, p, tag, warm=3):
    out = os.path.join(TMP, tag + '.raw')
    arr = (ctypes.c_double * P_COUNT)(*p)
    msg = ctypes.create_string_buffer(512)
    rc = 0
    for i in range(warm):
        rc = dll.RefGoldenRun(ENGINE_DIR.encode(), RAW.encode(), out.encode(),
                               W, H, arr, P_COUNT, 1, 1, 0, 1, msg, 512)
        if rc != 0:
            return None, 'rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace'))
    return load(out), msg.value.decode('utf-8', 'replace')


def Y(a):
    a = a[:, :, :3].astype(np.float32)
    return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]


def report(base, cur, label):
    db = cur[:, :, :3].astype(np.int16) - base[:, :, :3].astype(np.int16)
    mag = np.abs(db).max(axis=2)
    ch = mag > 2
    n = int(ch.sum())
    if n == 0:
        print('%-28s 无变化（该参数在该档位不生效）' % label)
        return
    ys, xs = np.where(ch)
    yb, yc = Y(base), Y(cur)
    dy = (yc - yb)[ch]
    print('%-28s 改动 %6d px (%.2f%%)  bbox x[%d,%d] y[%d,%d]  '
          'dY 均值 %+.2f  p5 %+.1f p95 %+.1f  变亮 %.0f%% 变暗 %.0f%%'
          % (label, n, 100.0 * n / (W * H), xs.min(), xs.max(), ys.min(), ys.max(),
             float(dy.mean()), float(np.percentile(dy, 5)),
             float(np.percentile(dy, 95)),
             100.0 * float((dy > 0).mean()), 100.0 * float((dy < 0).mean())))


def main():
    if not os.path.isdir(TMP):
        os.makedirs(TMP)
    dll = load_dll()

    base, msg = run(dll, panel(), 'base')
    if base is None:
        print('[probe] SDK 不可用：%s' % msg)
        return 2
    print('[probe] SDK OK  %s' % msg[:90])
    print('[probe] 基准 = 磨皮50，其余全 0；下表均为「该项单独开启」相对基准的差值')
    print()

    if len(sys.argv) >= 3:
        items = [(int(sys.argv[1]), float(sys.argv[2]))]
    else:
        items = [(k, v) for k in (P_THREED, P_EYEBRIGHT, P_POUCH,
                                  P_NASOLABIAL, P_DELSPOT) for v in (50.0, 100.0)]

    kw = {P_THREED: 'threed', P_EYEBRIGHT: 'eye', P_POUCH: 'pouch',
          P_NASOLABIAL: 'naso', P_DELSPOT: 'spot'}
    rows = []
    for idx, val in items:
        cur, m = run(dll, panel(**{kw[idx]: val}), '%d_%03d' % (idx, val))
        label = '%s=%g' % (NAMES[idx], val)
        if cur is None:
            print('%-28s 失败 %s' % (label, m[:60]))
            continue
        report(base, cur, label)
        rows.append((idx, val, m))

    # 交叉验证：五项同时拉满，看是否互相覆盖（用来判断能否共存）
    both, m = run(dll, panel(threed=100, eye=100, pouch=100, naso=100, spot=100),
                  'all100')
    if both is not None:
        print()
        report(base, both, '五项同时=100')

    with open(os.path.join(TMP, 'probe.json'), 'w', encoding='utf-8') as f:
        json.dump({'base_msg': msg, 'rows': [(a, b, c) for a, b, c in rows]},
                  f, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
