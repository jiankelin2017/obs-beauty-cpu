# -*- coding: utf-8 -*-
"""s3_pixel_eval.py —— surface3 / 25 tap 的**像素级**对拍（C23 第 2 批-A 验收）。

为什么需要这个脚本
------------------
`s3_eval.py` 报的是「四区域 × 三频带的细节保留率」，那是**曲线**口径。
S2 的教训是曲线对了结构不一定对（RMSE 1.16 个百分点，像素级 3.977）。
C23 §6.1 给第 2 批-A 的验收判据是像素级：

    100 档 像素级 RMSE 从 3.977 降到 < 2.0

所以这里直接量像素级残差。

口径
----
比较区域用 fuai 肤色掩码（`goldens/masks/<scene>_fuai.mask`），与 `core_vs_sdk.py`
同一套。基线可以选 `goldens`（region=on）或 `goldens_legacy`（region=off），
脚本会把两边都报出来，方便确认哪个才复现 3.977。

环境变量必须在**进程启动前**设好：`g_cfg` 在 `ensureReady` 里只读一次环境。

用法
----
    python s3_pixel_eval.py                    # 默认：盒式基线（tap25=0）
    python s3_pixel_eval.py --tap25 1          # 25 tap 路径
    python s3_pixel_eval.py --tap25 1 --half 0 # 25 tap，全分辨率
    python s3_pixel_eval.py --sweep            # 跑一组对照
"""
import argparse
import ctypes
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
MASK_DIR = os.path.join(HERE, 'goldens', 'masks')
SRC_DIR = os.path.join(HERE, 'goldens', 'src')
GOLD = os.path.join(HERE, 'goldens')
LEGACY = os.path.join(HERE, 'goldens_legacy')

W, H = 640, 394


def read_mask(p):
    raw = open(p, 'rb').read()
    mw, mh = np.frombuffer(raw[:8], np.int32)
    return np.frombuffer(raw[8:], np.uint8).reshape((mh, mw))


def upscale(m):
    if m.shape == (H, W):
        return m > 127
    ys = (np.arange(H) * m.shape[0]) // H
    xs = (np.arange(W) * m.shape[1]) // W
    return m[ys][:, xs] > 127


def load(p):
    a = np.fromfile(p, np.uint8)
    if a.size != W * H * 4:
        raise IOError('%s: %d bytes' % (p, a.size))
    return a.reshape((H, W, 4))


def run_core(raw_in, raw_out, blur):
    d = ctypes.WinDLL(DLL)
    d.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_double, ctypes.c_int,
                                ctypes.c_float, ctypes.c_float,
                                ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    d.BeautyCoreRun.restype = ctypes.c_int
    for n in ('BeautyCoreSetTone', 'BeautyCoreSetDetail'):
        getattr(d, n).argtypes = [ctypes.c_double, ctypes.c_double]
        getattr(d, n).restype = None
    d.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    d.BeautyCoreSetClarityPanel.restype = None
    d.BeautyCoreSetRegion.argtypes = [ctypes.c_int, ctypes.c_double]
    d.BeautyCoreSetRegion.restype = None
    d.BeautyCoreSetTone(0.0, 0.0)
    d.BeautyCoreSetDetail(0.0, 0.0)
    d.BeautyCoreSetClarityPanel(0.0)
    for i in range(5):
        d.BeautyCoreSetRegion(i, 0.0)
    msg = ctypes.create_string_buffer(512)
    # 连跑 3 次：首帧含模型加载，取最后一次的 ms 才是稳态
    for _ in range(3):
        rc = d.BeautyCoreRun(raw_in.encode(), raw_out.encode(), W, H,
                             float(blur), 0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('BeautyCoreRun rc=%d: %s'
                           % (rc, msg.value.decode('utf-8', 'replace')))
    return load(raw_out), msg.value.decode('utf-8', 'replace')


def boxsum(a, r):
    p = np.pad(a.astype(np.int32), r)
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def erode(reg, r):
    if r <= 0:
        return reg
    return boxsum(reg, r) == (2 * r + 1) ** 2


def metrics(out, ref, reg):
    a = out[:, :, :3].astype(np.float32)[reg]
    b = ref[:, :, :3].astype(np.float32)[reg]
    d = a - b
    rmse = float(np.sqrt((d * d).mean()))
    mad = float(np.abs(d).mean())
    mx = float(np.abs(d).max())
    return rmse, mad, mx


def one(tag, blur, region):
    src_p = os.path.join(SRC_DIR, 'face_src.raw')
    out_p = os.path.join(MASK_DIR, '_s3pe_%s.raw' % tag)
    out, msg = run_core(src_p, out_p, blur)
    src = load(src_p)
    rows = []
    for name, root in (('goldens(region on)', GOLD),
                       ('goldens_legacy(off)', LEGACY)):
        rp = os.path.join(root, 'flat', 'blur%03d_bt1' % blur, 'out.raw')
        if not os.path.exists(rp):
            continue
        ref = load(rp)
        rmse, mad, mx = metrics(out, ref, region)
        rows.append((name, rmse, mad, mx))
    # 相对输入的改动量，用来判断「磨了多少」
    dd = np.abs(out[:, :, :3].astype(np.int16)
                - src[:, :, :3].astype(np.int16))
    chg = float(dd[region].mean())
    return rows, chg, msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blur', type=int, default=100)
    ap.add_argument('--tap25', type=int, default=0)
    ap.add_argument('--half', type=int, default=1)
    ap.add_argument('--sx', type=float, default=None)
    ap.add_argument('--sy', type=float, default=None)
    ap.add_argument('--yf1', type=float, default=None)
    ap.add_argument('--yf2', type=float, default=None)
    ap.add_argument('--scene', default='face_src')
    ap.add_argument('--sweep', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(DLL):
        print('缺 %s，先跑 build_core_test.bat' % DLL)
        return 2

    # 这些必须在加载 DLL / 首次 ensureReady 之前设进环境
    os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
    os.environ['BEAUTY_S3_TAP25'] = str(args.tap25)
    os.environ['BEAUTY_S3_HALF'] = str(args.half)
    if args.sx is not None:
        os.environ['BEAUTY_S3_SX'] = repr(args.sx)
    if args.sy is not None:
        os.environ['BEAUTY_S3_SY'] = repr(args.sy)
    if args.yf1 is not None:
        os.environ['BEAUTY_S3_YF1'] = repr(args.yf1)
    if args.yf2 is not None:
        os.environ['BEAUTY_S3_YF2'] = repr(args.yf2)

    mp = os.path.join(MASK_DIR, args.scene + '_fuai.mask')
    reg = upscale(read_mask(mp))
    print('区域：fuai 肤色掩码 %s，占画面 %.2f%%'
          % (args.scene, 100.0 * reg.mean()))
    print('配置：tap25=%d half=%d blur=%d' % (args.tap25, args.half, args.blur))
    print()
    print('%-22s %8s %8s %8s' % ('基线', 'RMSE', 'MAD', 'max'))
    print('-' * 50)
    rows, chg, msg = one('t%d_h%d_b%d' % (args.tap25, args.half, args.blur),
                         args.blur, reg)
    for name, rmse, mad, mx in rows:
        flag = '  <= 达标' if rmse < 2.0 else ''
        print('%-22s %8.3f %8.3f %8.0f%s' % (name, rmse, mad, mx, flag))
    print()
    # 内缩口径：把掩码边界排除后看「真·皮肤内部」的残差。
    # 我们用的是 YuNet + 椭圆，SDK 用 fuai，两者边界形状本来就不一样；
    # 不分开看，会把「掩码不一致」记到「核不对」头上。
    src_p = os.path.join(SRC_DIR, 'face_src.raw')
    out_p = os.path.join(MASK_DIR, '_s3pe_t%d_h%d_b%d.raw'
                         % (args.tap25, args.half, args.blur))
    out = load(out_p)
    ref = load(os.path.join(GOLD, 'flat', 'blur%03d_bt1' % args.blur, 'out.raw'))
    print('内缩口径（排除掩码边界，看皮肤内部）：')
    print('%-10s %9s %8s %8s' % ('内缩', '像素数', 'RMSE', 'MAD'))
    for er in (0, 2, 4, 6, 8):
        r = erode(reg, er)
        if r.sum() < 100:
            continue
        rmse, mad, _ = metrics(out, ref, r)
        flag = '  <= 达标' if rmse < 2.0 else ''
        print('%-10d %9d %8.3f %8.3f%s' % (er, int(r.sum()), rmse, mad, flag))
    print()
    print('相对输入的改动量 mean|Δ| = %.2f 灰阶（皮肤区内）' % chg)
    print('SDK 自身改动量 = 2.71 灰阶（region on）—— 比这个数高太多就是过磨')
    print('引擎: %s' % msg.strip())
    return 0


if __name__ == '__main__':
    sys.exit(main())
