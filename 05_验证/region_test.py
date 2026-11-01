# -*- coding: utf-8 -*-
"""region_test —— 人脸局部五项（五官立体 / 亮眼 / 去黑眼圈 / 去法令纹 / 祛斑痘）
的自研实现与 SDK 对拍。

为什么这么测：这五项没有历史 golden，唯一参照是"还能跑的 SDK"。所以判据不是
"好不好看"，而是**作用域是否落在同一个解剖位置、方向是否一致、量级是否同档**：
  1. 改动像素数（脸框内）—— 量级
  2. 归一化 bbox / 连通域中心 —— 作用在哪个解剖点
  3. dY 的 p5 / p95 —— 方向与幅度
  4. 掩码外改动像素数 —— 必须是 0（产品承诺：背景不许被改）

计时只认引擎自报的 `ms=`。wall clock 会被 8MB 的 raw 读写污染约 15ms，
比被测函数本身还大（这条坑在 C10 里踩过）。

前置：region_probe.py 必须先跑过（产出 goldens/_probe/base.raw 与各 `<idx>_100.raw`）。
用法：
    python region_test.py
"""

from __future__ import print_function

import ctypes
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import low_path_test as L  # noqa: E402  （复用 DLL 路径 / load / TMP 约定）

W, H = 640, 394
P_BLUR, P_CLARITY, P_WHITEN, P_RED, P_SHARPEN, P_GLOBAL_SHARP, \
    P_THREED, P_EYEBRIGHT, P_POUCH, P_NASOLABIAL, P_DELSPOT = range(11)

# 人脸框与 5 个关键点（cv2 FaceDetectorYN 在 640x394 上实测，见 C12）
BX, BY, BW, BH = 276.4, 84.8, 111.3, 140.8
KPS = [(317.0, 139.0), (366.6, 143.3), (344.2, 172.2),
       (316.0, 190.4), (355.2, 194.2)]

ITEMS = [
    (P_THREED, 'threed', '五官立体'),
    (P_EYEBRIGHT, 'eye', '亮眼'),
    (P_POUCH, 'pouch', '去黑眼圈'),
    (P_NASOLABIAL, 'naso', '去法令纹'),
    (P_DELSPOT, 'spot', '祛斑痘'),
]

PROBE = os.path.join(HERE, 'goldens', '_probe')
OUT = os.path.join(HERE, 'goldens', '_region_core')


def Y(a):
    a = a[:, :, :3].astype(np.float32)
    return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]


def face_region_mask():
    m = np.zeros((H, W), bool)
    m[int(BY):int(BY + BH), int(BX):int(BX + BW)] = True
    return m


def norm_pt(x, y):
    return (x - BX) / BW, (y - BY) / BH


def stats(base, cur, mask):
    """返回（脸框内改动像素数, 归一化bbox, dY均值/p5/p95, 变亮占比）"""
    dy = Y(cur) - Y(base)
    ch = np.abs(dy) > 0.8
    inside = ch & mask
    n = int(inside.sum())
    if n == 0:
        return dict(n=0)
    ys, xs = np.where(inside)
    x0, x1 = norm_pt(xs.min(), ys.min())
    x2, x3 = norm_pt(xs.max(), ys.max())
    d = dy[inside]
    return dict(
        n=n,
        bbox=(x0, x1, x2, x3),
        mean=float(d.mean()),
        p5=float(np.percentile(d, 5)),
        p95=float(np.percentile(d, 95)),
        up=float((d > 0).mean()),
        peak=float(np.abs(d).max()),
        cxcy=norm_pt(xs.mean(), ys.mean()),
    )


def core_run(dll, raw, tmp, blur, idx, val, mask_path, warm=3, rep=5):
    dll.BeautyCoreSetRegion(0, 0.0)
    dll.BeautyCoreSetRegion(1, 0.0)
    dll.BeautyCoreSetRegion(2, 0.0)
    dll.BeautyCoreSetRegion(3, 0.0)
    dll.BeautyCoreSetRegion(4, 0.0)
    if idx >= 0:
        dll.BeautyCoreSetRegion(idx, val)
    msg = ctypes.create_string_buffer(512)
    for _ in range(warm):
        dll.BeautyCoreRun(raw.encode(), tmp.encode(), W, H, blur, 0,
                          0.0, 0.0, 1, msg, 512)
    best = None
    mtxt = msg.value.decode('ascii', 'replace')
    for _ in range(rep):
        dll.BeautyCoreRun(raw.encode(), tmp.encode(), W, H, blur, 0,
                          0.0, 0.0, 1, msg, 512)
        mtxt = msg.value.decode('ascii', 'replace')
        mm = re.search(r'ms=([0-9.]+)', mtxt)
        if mm:
            v = float(mm.group(1))
            best = v if best is None else min(best, v)
    return L.load(tmp, W, H), (best if best is not None else -1.0), mtxt


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    # 掩码：core 这一帧的肤色掩码，用来验证"脸外零改动"
    dll = ctypes.WinDLL(L.DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_char_p,
                                   ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]

    raw = os.path.join(L.RES, '640x394.raw')
    mpath = os.path.join(OUT, 'core.mask')
    msg = ctypes.create_string_buffer(512)
    rc = dll.BeautyCoreMask(raw.encode(), W, H, mpath.encode(), msg, 512)
    if rc != 0:
        print('[region] 掩码失败 %s' % msg.value.decode('ascii', 'replace'))
        return 2
    import struct
    with open(mpath, 'rb') as f:
        _mw, _mh = struct.unpack('<ii', f.read(8))
        mk = np.frombuffer(f.read(_mw * _mh), dtype=np.uint8).reshape((_mh, _mw))
    outside = (mk == 0)

    fm = face_region_mask()
    tmp = os.path.join(OUT, 'core.raw')

    print('[region] 基准：磨皮 50，其余 0；每项单独拉到 100 与「基准」相减')
    print('[region] 脸框 x=%.1f y=%.1f w=%.1f h=%.1f；掩码覆盖 %.2f%%'
          % (BX, BY, BW, BH, 100.0 * (~outside).mean()))
    print()

    base_c, ms_c, mtxt = core_run(dll, raw, tmp, 50.0, -1, 0.0, mpath)
    print('[core] 基准 %s' % mtxt[:80])
    sdk_base = L.load(os.path.join(PROBE, 'base.raw'), W, H)
    # core 与 SDK 的磨皮本就不同，这里不比绝对值，只比"该项带来的增量"

    print()
    print('%-10s %-7s %8s %8s %9s %9s %9s %8s'
          % ('项', '引擎', '脸内px', '脸外px', 'dY均值', 'p5', 'p95', 'ms'))
    rows = []
    for idx, kw, name in ITEMS:
        cur_c, ms, mtxt = core_run(dll, raw, tmp, 50.0,
                                   ITEMS.index((idx, kw, name)), 100.0, mpath)
        sc = stats(base_c, cur_c, fm)
        bg = int((np.abs(Y(cur_c) - Y(base_c)) > 0.8)[outside].sum())
        p = os.path.join(PROBE, '%d_100.raw' % idx)
        if os.path.exists(p):
            ss = stats(sdk_base, L.load(p, W, H), fm)
        else:
            ss = None
        for tag, st, msx in (('SDK', ss, None), ('core', sc, ms)):
            if st is None or st.get('n', 0) == 0:
                print('%-10s %-7s %8s %8s %9s %9s %9s %8s'
                      % (name, tag, '-', '-', '-', '-', '-', '-'))
                continue
            print('%-10s %-7s %8d %8s %+9.2f %+9.2f %+9.2f %8s'
                  % (name, tag, st['n'], (bg if tag == 'core' else '-'),
                     st['mean'], st['p5'], st['p95'],
                     ('%.2f' % msx) if msx is not None else '-'))
            rows.append((name, tag, st, bg if tag == 'core' else None))
        # 位置：连通域中心 + bbox（归一化到脸框）
        if ss and ss.get('n', 0) and sc.get('n', 0):
            print('           位置 SDK  bbox x[%.2f,%.2f] y[%.2f,%.2f]  质心(%.2f,%.2f)' %
                  (ss['bbox'][0], ss['bbox'][2], ss['bbox'][1], ss['bbox'][3],
                   ss['cxcy'][0], ss['cxcy'][1]))
            print('           位置 core bbox x[%.2f,%.2f] y[%.2f,%.2f]  质心(%.2f,%.2f)' %
                  (sc['bbox'][0], sc['bbox'][2], sc['bbox'][1], sc['bbox'][3],
                   sc['cxcy'][0], sc['cxcy'][1]))
        print()

    # 五项同时拉满：看是否互相覆盖
    for i in range(5):
        dll.BeautyCoreSetRegion(i, 100.0)
    msg = ctypes.create_string_buffer(512)
    dll.BeautyCoreRun(raw.encode(), tmp.encode(), W, H, 50.0, 0,
                      0.0, 0.0, 1, msg, 512)
    all_c = L.load(tmp, W, H)
    st = stats(base_c, all_c, fm)
    bg = int((np.abs(Y(all_c) - Y(base_c)) > 0.8)[outside].sum())
    sdk_all = os.path.join(PROBE, 'all100.raw')
    if os.path.exists(sdk_all):
        ss = stats(sdk_base, L.load(sdk_all, W, H), fm)
        print('五项同时=100  SDK 脸内 %d px  dY %+.2f / core 脸内 %d px  dY %+.2f  脸外改动 %d'
              % (ss.get('n', 0), ss.get('mean', 0), st.get('n', 0),
                 st.get('mean', 0), bg))

    # 写 markdown
    md = ['# 人脸局部五项 —— core vs SDK 对拍\n',
          '> 自动生成：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 素材 640x394（face_src），基准磨皮 50，该项单独拉到 100',
          '> 位置坐标归一化到人脸框（0=框左/上边，1=框右/下边）',
          '> 耗时是引擎自报 `ms=`，不含文件 I/O', '',
          '| 项 | 引擎 | 脸内改动px | 脸外改动px | dY均值 | p5 | p95 | ms |',
          '|---|---|---|---|---|---|---|---|']
    for name, tag, st, bg in rows:
        md.append('| %s | %s | %d | %s | %+.2f | %+.2f | %+.2f | %s |'
                  % (name, tag, st['n'], ('%d' % bg) if bg is not None else '-',
                     st['mean'], st['p5'], st['p95'], '-'))
    with open(os.path.join(HERE, 'goldens', 'masks', 'region.md'), 'w',
              encoding='utf-8') as f:
        f.write('\n'.join(md) + '\n')
    print('\n[region] 已写 goldens/masks/region.md')
    return 0


if __name__ == '__main__':
    sys.exit(main())
