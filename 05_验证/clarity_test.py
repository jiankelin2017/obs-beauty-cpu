# clarity_test.py —— 清晰（clarity）的验收测量
#
# 验收指标写死在 04_文档/D1_我们自己的技术线路.md §5.3：
#   中幅度(6~30) 96.8% → 100~106%（有增强但不夸张）
#   大幅度(>30)  ≥99%（不加光晕）
#   非皮肤区     0 字节（用引擎自己的掩码判定，不是猜一个框）
#   脸颊台阶%    不上升
#   1080p 增量   ≤1.5 ms
#
# 判据说明：
#   · 中幅度带 = 「立体感」的代理指标。它上去了 = 明暗层次被增强。
#   · 大幅度带如果不掉 = 没在硬边上加，也就是没有光晕。
#   · 整体亮度变化应该接近 0（mid 在统计上是零均值，加它不该整体变亮/变暗）。

import ctypes
import os
import struct
import sys
import time

import numpy as np

import low_path_test as L

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = L.DLL
RES = L.RES
OUT = L.OUT
FACE = L.FACE


def load_mask(path, w, h):
    """BeautyCoreMask 落盘格式：int32 mw + int32 mh + mw*mh 字节。"""
    with open(path, 'rb') as f:
        mw, mh = struct.unpack('<ii', f.read(8))
        buf = f.read(mw * mh)
    m = np.frombuffer(buf, dtype=np.uint8).reshape((mh, mw))
    if (mw, mh) != (w, h):
        return None
    return m


def main():
    if not os.path.exists(DLL):
        print('[clarity] missing %s' % DLL)
        return 2
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    dll.BeautyCoreSetClarity.argtypes = [ctypes.c_float, ctypes.c_int,
                                        ctypes.c_float, ctypes.c_float]
    dll.BeautyCoreSetFreq.argtypes = [ctypes.c_int, ctypes.c_float,
                                      ctypes.c_float, ctypes.c_float]
    dll.BeautyCoreSetLowPath.argtypes = [ctypes.c_int, ctypes.c_int]
    dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreMask.restype = ctypes.c_int

    os.makedirs(OUT, exist_ok=True)
    W, H = 640, 394
    raw = os.path.join(RES, '640x394.raw')
    tmp = os.path.join(OUT, '_cl.raw')
    maskp = os.path.join(OUT, '_cl.mask')
    src = L.load(raw, W, H)

    # 掩码（引擎自己算的，用来判「非皮肤区是否 0 字节」）
    msg = ctypes.create_string_buffer(512)
    mask = None
    if dll.BeautyCoreMask(raw.encode(), W, H, maskp.encode(), msg, 512) == 0:
        mask = load_mask(maskp, W, H)

    # 分带（与 C4 / C8 同口径：σ=12 高斯定义低频）
    low_src = L.gauss_rgb(src[:, :, :3], 12.0)
    high_src = src[:, :, :3].astype(np.float32) - low_src
    hmag = np.abs(high_src).max(axis=2)
    region = np.zeros((H, W), bool)
    x0, x1, y0, y1 = FACE
    region[y0:y1, x0:x1] = True
    b_small = (hmag < 6) & region
    b_mid = (hmag >= 6) & (hmag < 30) & region
    b_big = (hmag >= 30) & region

    cheek = np.zeros((H, W), bool)
    cheek[175:215, 300:355] = True

    def bands_of(img):
        lo_i = L.gauss_rgb(img[:, :, :3], 12.0)
        hi_i = img[:, :, :3].astype(np.float32) - lo_i
        out = []
        for bm in (b_small, b_mid, b_big):
            out.append(100.0 * np.abs(hi_i[bm]).mean() / np.abs(high_src[bm]).mean())
        return out

    def steps(img):
        g = img[:, :, :3].astype(np.float32).mean(axis=2)
        lap = np.zeros_like(g)
        lap[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
                                 - g[1:-1, :-2] - g[1:-1, 2:])
        return 100.0 * (lap[cheek] > 2.0).mean()

    def luma_mean(img):
        return float((0.299 * img[:, :, 0] + 0.587 * img[:, :, 1]
                      + 0.114 * img[:, :, 2]).mean())

    # 固定磨皮 50 档，只改面板「清晰」
    dll.BeautyCoreSetFreq(1, 2.0, 6.0, 30.0)
    dll.BeautyCoreSetLowPath(0, 8)
    # 显式写成当前默认值（beauty_core.cpp 的 g_cfg），避免脚本与默认值漂移
    # 20/45 是初版软膝，会把大幅度带推到 105.9（边缘被加亮）；8/22 是收窄后的值
    dll.BeautyCoreSetClarity(0.30, 12, 8.0, 22.0)

    rows = []
    base = None
    print('%-10s 中%%     大%%     磨皮量  亮度  台阶%%  ms' % '清晰档')
    for panel in (0.0, 25.0, 50.0, 100.0):
        dll.BeautyCoreSetClarityPanel(panel)
        for _ in range(4):
            dll.BeautyCoreRun(raw.encode(), tmp.encode(), W, H, 50.0, 0, 0.0, 0.0, 1,
                              msg, 512)
        best = 1e9
        for _ in range(4):
            t0 = time.perf_counter()
            dll.BeautyCoreRun(raw.encode(), tmp.encode(), W, H, 50.0, 0, 0.0, 0.0, 1,
                              msg, 512)
            best = min(best, (time.perf_counter() - t0) * 1000.0)
        img = L.load(tmp, W, H)
        bs = bands_of(img)
        amt = float(np.abs(img[region][:, :3].astype(np.float32)
                           - src[region][:, :3].astype(np.float32)).mean())
        if panel == 0.0:
            base = img.copy()
        rows.append((panel, bs, amt, luma_mean(img), steps(img), best))
        print('%-10s %5.1f  %5.1f  %6.3f  %+5.2f  %5.1f  %5.2f'
              % ('%d' % panel, bs[1], bs[2], amt,
                 luma_mean(img) - luma_mean(src), steps(img), best))

    # 非皮肤区：与「清晰=0」逐字节比较
    nonskin_bad = -1
    if mask is not None:
        dll.BeautyCoreSetClarityPanel(100.0)
        dll.BeautyCoreRun(raw.encode(), tmp.encode(), W, H, 50.0, 0, 0.0, 0.0, 1,
                          msg, 512)
        img = L.load(tmp, W, H)
        zero = mask == 0
        diff = np.any(img[zero] != base[zero], axis=1)
        nonskin_bad = int(diff.sum())

    # 1080p 计时
    t1080 = None
    p1080 = os.path.join(RES, '1080p.raw')
    if os.path.exists(p1080):
        def timed(panel_val):
            dll.BeautyCoreSetClarityPanel(panel_val)
            for _ in range(4):
                dll.BeautyCoreRun(p1080.encode(), tmp.encode(), 1920, 1080, 50.0,
                                  0, 0.0, 0.0, 1, msg, 512)
            b = 1e9
            for _ in range(7):
                t0 = time.perf_counter()
                dll.BeautyCoreRun(p1080.encode(), tmp.encode(), 1920, 1080, 50.0,
                                  0, 0.0, 0.0, 1, msg, 512)
                b = min(b, (time.perf_counter() - t0) * 1000.0)
            return b
        t0v = timed(0.0)
        t1v = timed(100.0)
        t1080 = (t0v, t1v, t1v - t0v)

    # 报告
    md = ['# clarity 验收测量\n',
          '> 自动生成：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 素材：goldens/res/640x394.raw，磨皮固定 50 档，只改面板「清晰」',
          '> 指标口径：见 04_文档/D1_我们自己的技术线路.md §5.3\n',
          '| 清晰档 | 中幅度% | 大幅度% | 磨皮量 | 亮度变化 | 脸颊台阶% | 640×394 |',
          '|---|---|---|---|---|---|---|']
    for panel, bs, amt, lm, st, ms in rows:
        md.append('| %d | %.1f | %.1f | %.3f | %+.2f | %.1f | %.2f ms |'
                  % (panel, bs[1], bs[2], amt, lm - luma_mean(src), st, ms))
    md.append('')
    if nonskin_bad >= 0:
        md.append('非皮肤区与「清晰=0」的差异像素：**%d**（要求 = 0）' % nonskin_bad)
    else:
        md.append('非皮肤区检查：跳过（掩码尺寸不匹配）')
    if t1080:
        md.append('')
        md.append('1080p 耗时：清晰 0 → %.2f ms，清晰 100 → %.2f ms，'
                  '**增量 %.2f ms**（要求 ≤ 1.5）' % t1080)
    out_md = os.path.join(OUT, 'clarity.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print()
    print('[clarity] 非皮肤差异像素 = %d' % nonskin_bad)
    if t1080:
        print('[clarity] 1080p: %.2f -> %.2f ms (增量 %+.2f)' % t1080)
    print('[clarity] -> %s' % out_md)
    for f in (tmp, maskp):
        if os.path.exists(f):
            os.remove(f)
    return 0


if __name__ == '__main__':
    sys.exit(main())
