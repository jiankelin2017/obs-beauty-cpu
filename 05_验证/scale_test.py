# -*- coding: utf-8 -*-
"""分辨率 / 脸大小依赖验证。

背景（2026-10-29）：
    离线 C17 用 face_src（640x394，脸宽 111px）测出我们「削过头」；
    真机 4 张（1920x1080，脸宽 ~550px）测出我们「削不够」（+16~23%）。
    两者相反。假说：我们的核是**绝对像素尺度**（boxRadius=2，sigma≈2px），
    不随分辨率 / 脸大小变；SDK 大概率按脸大小自适应。

实验：
    把同一张 face_src 用 LANCZOS 放大到 k 倍，再对拍 core 与 SDK。
    同一输入喂两边，所以插值带来的高频变化在两边相同，差值可比。
    看 gap 是否随 k 从「削过头（负）」翻转成「削不够（正）」。

用法：
    python scale_test.py            # k = 1, 2, 5
    python scale_test.py 1 2        # 指定倍数
"""
import ctypes
import os
import re
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import low_path_test as L  # noqa: E402
import region_gap as RG    # noqa: E402

RAW = RG.RAW
BASE_W, BASE_H = 640, 394
# 基准脸框（region_gap 在 640x394 上的实测值）
BX, BY, BW_, BH_ = RG.BX, RG.BY, RG.BW_, RG.BH_
REGIONS = RG.REGIONS
P_COUNT = RG.P_COUNT
P_BLUR = RG.P_BLUR
SDK_DLL = RG.SDK_DLL
ENGINE_DIR = RG.ENGINE_DIR
TMP = os.path.join(L.OUT)


def load_raw(path, w, h):
    return np.fromfile(path, dtype=np.uint8).reshape((h, w, 4))


def upscale(img, k):
    if k == 1:
        return img.copy()
    return cv2_resize(img, int(BASE_W * k), int(BASE_H * k))


def cv2_resize(img, w, h):
    import cv2
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_LANCZOS4)


def boxmean(a, r):
    h, w = a.shape
    k = 2 * r + 1
    p = np.pad(a, ((0, 0), (r, r)), mode='edge')
    c = np.cumsum(p, axis=1, dtype=np.float64)
    c = np.concatenate([np.zeros((h, 1)), c], axis=1)
    h1 = (c[:, k:] - c[:, :-k]) / k
    p2 = np.pad(h1, ((r, r), (0, 0)), mode='edge')
    c2 = np.cumsum(p2, axis=0, dtype=np.float64)
    c2 = np.concatenate([np.zeros((1, w)), c2], axis=0)
    return (c2[k:, :] - c2[:-k, :]) / k


def bands_of(img):
    """与 region_gap.bands 同口径：细 |Y-box1| / 中 |box1-box7| / 阴 |box7-box21|"""
    y = (0.299 * img[:, :, 0] + 0.587 * img[:, :, 1]
         + 0.114 * img[:, :, 2]).astype(np.float64)
    b1 = boxmean(y, 1)
    b7 = boxmean(y, 7)
    b21 = boxmean(y, 21)
    return np.abs(y - b1), np.abs(b1 - b7), np.abs(b7 - b21)


def masks(w, h, k):
    """区域掩码随放大倍数一起缩放"""
    out = []
    for name, nx0, ny0, nx1, ny1 in REGIONS:
        m = np.zeros((h, w), bool)
        x0 = int((BX + nx0 * BW_) * k); x1 = int((BX + nx1 * BW_) * k)
        y0 = int((BY + ny0 * BH_) * k); y1 = int((BY + ny1 * BH_) * k)
        m[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
        out.append((name, m))
    return out


def run_core(raw_path, w, h, blur, out_path):
    dll = ctypes.WinDLL(L.DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    for n in ('BeautyCoreSetTone', 'BeautyCoreSetDetail'):
        getattr(dll, n).argtypes = [ctypes.c_double, ctypes.c_double]
    dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    dll.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]
    dll.BeautyCoreSetTone(0.0, 0.0)
    dll.BeautyCoreSetDetail(0.0, 0.0)
    dll.BeautyCoreSetClarityPanel(0.0)
    for i in range(5):
        dll.BeautyCoreSetRegion(i, 0.0)
    msg = ctypes.create_string_buffer(512)
    ms = -1.0
    for _ in range(3):
        dll.BeautyCoreRun(raw_path.encode(), out_path.encode(), w, h, blur, 0,
                          0.0, 0.0, 1, msg, 512)
        m = re.search(r'ms=([0-9.]+)', msg.value.decode('ascii', 'replace'))
        if m:
            ms = float(m.group(1))
    return load_raw(out_path, w, h), ms


def run_sdk(raw_path, w, h, blur, out_path):
    d = ctypes.WinDLL(SDK_DLL)
    d.RefGoldenRun.argtypes = [ctypes.c_char_p] * 3 + [
        ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double),
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    arr = (ctypes.c_double * P_COUNT)(*[0.0] * P_COUNT)
    arr[P_BLUR] = blur
    msg = ctypes.create_string_buffer(512)
    rc = d.RefGoldenRun(ENGINE_DIR.encode(), raw_path.encode(), out_path.encode(),
                         w, h, arr, P_COUNT, 1, 1, 0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('sdk rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
    return load_raw(out_path, w, h)


def levels_of(img, rms):
    sb = bands_of(img)
    return {n: [float(sb[i][m].mean()) for i in range(3)] for n, m in rms}


def main():
    ks = [int(x) for x in sys.argv[1:]] or [1, 2, 5]
    levels = [50.0, 100.0]
    src0 = load_raw(RAW, BASE_W, BASE_H)

    rows = []
    for k in ks:
        w, h = int(BASE_W * k), int(BASE_H * k)
        img = upscale(src0, k)
        rp = os.path.join(TMP, '_scale%d_src.raw' % k)
        img.tofile(rp)
        rms = masks(w, h, k)
        base = levels_of(img, rms)

        for lvl in levels:
            co, ms = run_core(rp, w, h, lvl,
                              os.path.join(TMP, '_scale%d_core.raw' % k))
            sd = run_sdk(rp, w, h, lvl,
                         os.path.join(TMP, '_scale%d_sdk.raw' % k))
            cb = levels_of(co, rms)
            sbk = levels_of(sd, rms)
            rows.append((k, w, h, lvl, base, cb, sbk, ms))
        try:
            os.remove(rp)
        except OSError:
            pass
        print('  k=%d (%dx%d) 脸宽%.0fpx 完成' % (k, w, h, BW_ * k))

    print()
    print('保留率%：core − SDK（负=我们削过头，正=我们削不够）')
    print('%-5s %6s %5s | %-24s | %-24s' % ('k', '脸宽px', '档', '细  core/SDK/差', '阴影 core/SDK/差'))
    for k, w, h, lvl, base, cb, sbk, ms in rows:
        def pc(d, n, i):
            return 100.0 * d[n][i] / base[n][i] if base[n][i] > 1e-9 else float('nan')
        # 取皮肤相关四区域平均（与 C17 主指标一致：额头/鼻翼/脸颊/眼区）
        names = ['额头', '鼻翼', '脸颊', '眼区']
        for i, tag in ((0, '细'), (2, '阴')):
            c = sum(pc(cb, n, i) for n in names) / len(names)
            s = sum(pc(sbk, n, i) for n in names) / len(names)
            if tag == '细':
                line = '%-5d %6d %5g | 细 %6.1f/%6.1f/%+6.1f' % (k, BW_ * k, lvl, c, s, c - s)
            else:
                print(line + ' | 阴 %6.1f/%6.1f/%+6.1f  (%g ms)'
                      % (c, s, c - s, ms))

    print()
    print('全部 15 格明细（最后一档）：')
    k, w, h, lvl, base, cb, sbk, ms = rows[-1]
    print('%-6s %9s %9s %9s | %9s %9s %9s' % ('区域', 'core细', 'SDK细', 'd细', 'core阴', 'SDK阴', 'd阴'))
    for n, m in masks(w, h, k):
        cf = 100.0 * cb[n][0] / base[n][0]; sf = 100.0 * sbk[n][0] / base[n][0]
        cs = 100.0 * cb[n][2] / base[n][2]; ss = 100.0 * sbk[n][2] / base[n][2]
        print('%-6s %8.1f%% %8.1f%% %+8.1f | %8.1f%% %8.1f%% %+8.1f'
              % (n, cf, sf, cf - sf, cs, ss, cs - ss))


if __name__ == '__main__':
    main()
