# -*- coding: utf-8 -*-
"""real_frame_eval.py —— 在**真机摄像头画面**上做 SDK 对齐对拍。

为什么需要这个脚本
------------------
到今天为止，C23 的所有画质验收都是拿 `goldens/src/face_src.raw`（640x394 的
合成图 crop_c）跑的。真机画面从来没进过这套评估。真脸有噪点、有光照不均、
有眼镜反光，统计特性和合成图完全不同 —— 合成图上的 RMSE 2.417 能不能代表
真机，是未知数。

本脚本把真机帧变成一份可复现的金标：

    1. 拿一张**关掉滤镜**的原始摄像头帧（PNG）
    2. 用 ref_golden.dll 离线跑第三方 SDK（blur=100, bt=1）→ 金标
    3. 同时导出 SDK 自己的肤色掩码 → 评估区域
    4. 用 beauty_core_test.dll 跑自研引擎，同参数同输入
    5. 算像素级 RMSE / 改动量 / 空间相关

分辨率说明（重要）
------------------
OBS 的「截图」按**画布**分辨率出图。本机画布 1920x1080、摄像头 1280x720，
所以拿到的帧是源被放大 1.5 倍的结果。这**不影响对拍的自洽性**：两边引擎吃
的是同一张图，核又是 UV 固定的（σ ∝ W），脸和核一起放大 1.5 倍，相对关系
不变。但绝对 RMSE 会偏低 —— 放大插值本身削掉了高频，而磨皮比的正是高频。
要更严格就在 OBS 里把画布设成 1280x720 再截一次。

环境变量必须在**进程启动前**设好（g_cfg 在 ensureReady 里只读一次），所以
一次进程只能测一个模型，多模型要在外面循环。

用法
----
    python real_frame_eval.py --png "D:\\c\\Screenshot ... .png" --mk
    python real_frame_eval.py --model legacy
    python real_frame_eval.py --model surface3 --tap25 1
    python real_frame_eval.py --model surface3 --tap25 1 --half 0
"""
import argparse
import ctypes
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CORE_DLL = os.path.join(HERE, 'beauty_core_test.dll')
GOLD_DLL = os.path.join(HERE, 'ref_golden.dll')
def _pick_engine_dir():
    """参照引擎目录：优先 GOLDEN_ENGINE_DIR，否则按存在性挑一个。

    2026-10-30：原先写死 Temp\\legacy_abtest\\engine，系统清 Temp 后就找不到了
    （acquireSlot failed: LoadLibrary 失败 err=126）。实际引擎在 C:\\btwork\\engine。
    """
    cands = [os.environ.get('GOLDEN_ENGINE_DIR'),
             r'C:\btwork\engine',
             r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine']
    for c in cands:
        if c and os.path.exists(os.path.join(c, 'CNamaSDK.dll')):
            return c
    return cands[0]


ENGINE_DIR = _pick_engine_dir()
WORK = os.path.join(HERE, 'goldens', 'real')
WARMUP = 6
BLUR = 100.0
# blur_type：1 = 双边滤波，2 = 弱磨皮，-1 = 不下发（SDK 取 bundle 内建默认）
#
# ⚠ 2026-10-30 更正：本文件的 BT 常量原本写死 1，于是 C19/C23 全部画质指标都是
#   对着「我们自己显式下发 bt1」这个自发行为标定的，而不是对着第三方产品。
#   产品实测**从不下发 blur_type**（见 03_逆向资料/IPC序列化_20261030/ 与
#   06_离线验证/goldens_encrypted/），生效档 = bundle 裸默认 = 2。
#   所以「对齐产品」的金标必须用 BT = -1 生成，见 --gold-bt 参数。
BT = 1              # 保留为默认值，只为向后兼容旧资产
GOLD_BT_DEFAULT = 1
SKIN_DETECT = 1
SMOOTH_MODE = 0


def bt_suffix(bt):
    """金标文件名的档位后缀。bt=1 不加后缀，兼容 2026-10-30 之前生成的旧资产。"""
    if bt == 1:
        return ''
    return '_btM%d' % (-bt) if bt < 0 else '_bt%d' % bt


def gold_path(tag, bt):
    return os.path.join(WORK, '%s_gold%s.raw' % (tag, bt_suffix(bt)))


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def png_to_rgba(path):
    im = Image.open(path)
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    return np.asarray(im, dtype=np.uint8)


def load_raw(path, w, h):
    a = np.fromfile(path, np.uint8)
    if a.size != w * h * 4:
        raise IOError('%s: %d bytes, expect %d' % (path, a.size, w * h * 4))
    return a.reshape((h, w, 4))


def read_mask(path):
    raw = open(path, 'rb').read()
    mw, mh = np.frombuffer(raw[:8], np.int32)
    return np.frombuffer(raw[8:], np.uint8).reshape((mh, mw))


def upscale_mask(m, w, h):
    if m.shape == (h, w):
        return m > 127
    ys = (np.arange(h) * m.shape[0]) // h
    xs = (np.arange(w) * m.shape[1]) // w
    return m[ys][:, xs] > 127


# ---------------------------------------------------------------------------
# 第三方 SDK（金标）
# ---------------------------------------------------------------------------
def load_gold_dll():
    d = ctypes.WinDLL(GOLD_DLL)
    d.RefGoldenRun.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(ctypes.c_double), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    d.BeautyDumpMask.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    d.BeautyDumpMask.restype = ctypes.c_int
    return d


def run_gold(d, raw_in, raw_out, w, h, blur, bt=None):
    """bt=None → 用模块默认 BT；bt=-1 → 不下发 blur_type（= 第三方产品的真实行为）。"""
    if bt is None:
        bt = BT
    panel = (ctypes.c_double * 11)()
    panel[0] = float(blur)
    msg = ctypes.create_string_buffer(512)
    rc = d.RefGoldenRun(ENGINE_DIR.encode('utf-8'), raw_in.encode('utf-8'),
                         raw_out.encode('utf-8'), w, h, panel, 11,
                         int(bt), SKIN_DETECT, SMOOTH_MODE, 1, msg, 512)
    return rc, msg.value.decode('utf-8', 'replace')


def make_golden(png, w, h, tag, bt=None):
    if bt is None:
        bt = BT
    os.makedirs(WORK, exist_ok=True)
    arr = png_to_rgba(png)
    if arr.shape[:2] != (h, w):
        raise SystemExit('PNG 尺寸 %s 与 --w/--h %dx%d 不符'
                         % (arr.shape[1::-1], w, h))
    raw_in = os.path.join(WORK, '%s_in.raw' % tag)
    arr.tofile(raw_in)

    d = load_gold_dll()
    out_tmp = os.path.join(WORK, '_warm.raw')
    # 检测器首帧在建会话，必须热身，否则拿到的是 faces=0 那一帧
    for _ in range(WARMUP):
        rc, txt = run_gold(d, raw_in, out_tmp, w, h, 0.0, bt)
        if rc != 0:
            raise SystemExit('热身失败 rc=%d: %s' % (rc, txt))

    gold = gold_path(tag, bt)
    for _ in range(3):
        rc, txt = run_gold(d, raw_in, gold, w, h, BLUR, bt)
        if rc != 0:
            raise SystemExit('金标失败 rc=%d: %s' % (rc, txt))
    print('金标 : %s  (blur_type=%s)' % (gold, bt))
    print('       %s' % txt)

    mask_p = os.path.join(WORK, '%s_fuai.mask' % tag)
    if os.path.exists(mask_p):
        os.remove(mask_p)
    msg = ctypes.create_string_buffer(512)
    rc = d.BeautyDumpMask(ENGINE_DIR.encode('utf-8'), raw_in.encode('utf-8'),
                          w, h, mask_p.encode('utf-8'), msg, 512)
    print('掩码 : rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
    return raw_in, gold, mask_p


# ---------------------------------------------------------------------------
# 自研引擎
# ---------------------------------------------------------------------------
def run_core(raw_in, raw_out, w, h, blur=BLUR):
    d = ctypes.WinDLL(CORE_DLL)
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
    rc = 0
    for _ in range(3):      # 首帧含模型加载
        rc = d.BeautyCoreRun(raw_in.encode(), raw_out.encode(), w, h,
                             float(blur), 0, 0.0, 0.0, 1, msg, 512)
    if rc != 0:
        raise RuntimeError('BeautyCoreRun rc=%d: %s'
                           % (rc, msg.value.decode('utf-8', 'replace')))
    return load_raw(raw_out, w, h), msg.value.decode('utf-8', 'replace')


# ---------------------------------------------------------------------------
# 度量
# ---------------------------------------------------------------------------
def boxsum(a, r):
    p = np.pad(a.astype(np.int32), r)
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def erode(reg, r):
    return reg if r <= 0 else boxsum(reg, r) == (2 * r + 1) ** 2


def rmse_in(a, b, reg):
    d = a[:, :, :3].astype(np.float32)[reg] - b[:, :, :3].astype(np.float32)[reg]
    return float(np.sqrt((d * d).mean())) if d.size else float('nan')


def change_in(src, out, reg):
    d = np.abs(out[:, :, :3].astype(np.int16) - src[:, :, :3].astype(np.int16))
    return float(d[reg].mean()) if reg.any() else float('nan')


def spatial_corr(src, out, ref, reg):
    """改动方向的一致性：把「我们改了多少」和「SDK 改了多少」逐像素求相关。
    强度对得上但位置错，这个数会掉到 0 附近。"""
    ds = (out[:, :, :3].astype(np.float32)
          - src[:, :, :3].astype(np.float32))[reg]
    dr = (ref[:, :, :3].astype(np.float32)
          - src[:, :, :3].astype(np.float32))[reg]
    ds = ds - ds.mean()
    dr = dr - dr.mean()
    den = float(np.sqrt((ds * ds).sum() * (dr * dr).sum()))
    return float((ds * dr).sum() / den) if den > 0 else float('nan')


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--png', default=None, help='关掉滤镜截的原始帧')
    ap.add_argument('--w', type=int, default=1920)
    ap.add_argument('--h', type=int, default=1080)
    ap.add_argument('--tag', default='cam')
    ap.add_argument('--mk', action='store_true', help='生成金标与掩码')
    ap.add_argument('--model', default='legacy', choices=['legacy', 'surface3'])
    ap.add_argument('--tap25', type=int, default=0)
    ap.add_argument('--band', type=int, default=0, help='1 = 双尺度带通（C23 §12）')
    ap.add_argument('--bt', type=float, default=14.0, help='振幅门控阈值 T（与金标档位无关）')
    ap.add_argument('--gold-bt', type=int, default=GOLD_BT_DEFAULT,
                    help='金标 blur_type：-1 = 不下发（= 第三方产品真实行为，'
                         '对齐产品时必须用 -1）；1 = 双边（旧基准，仅作对照）')
    ap.add_argument('--half', type=int, default=1)
    ap.add_argument('--blur', type=float, default=BLUR)
    ap.add_argument('--dump', action='store_true', help='导出对比图与残差热图')
    args = ap.parse_args()

    os.makedirs(WORK, exist_ok=True)
    raw_in = os.path.join(WORK, '%s_in.raw' % args.tag)
    gold_p = gold_path(args.tag, args.gold_bt)
    mask_p = os.path.join(WORK, '%s_fuai.mask' % args.tag)

    if args.mk:
        if not args.png:
            raise SystemExit('--mk 需要 --png')
        make_golden(args.png, args.w, args.h, args.tag, args.gold_bt)
        print()

    for p in (raw_in, gold_p, mask_p):
        if not os.path.exists(p):
            raise SystemExit('缺 %s，先跑 --mk' % p)

    os.environ['BEAUTY_SMOOTH_MODEL'] = args.model
    os.environ['BEAUTY_S3_TAP25'] = str(args.tap25)
    os.environ['BEAUTY_S3_HALF'] = str(args.half)
    os.environ['BEAUTY_S3_BAND'] = str(args.band)
    os.environ['BEAUTY_S3_BT'] = str(args.bt)

    src = load_raw(raw_in, args.w, args.h)
    ref = load_raw(gold_p, args.w, args.h)
    reg = upscale_mask(read_mask(mask_p), args.w, args.h)
    if not reg.any():
        raise SystemExit('掩码是空的 —— SDK 没检出人脸，这张帧不能用')

    tag = args.model + ('_band' if args.band else ('_tap25' if args.tap25 else ''))
    out_p = os.path.join(WORK, '_core_%s.raw' % tag)
    out, msg = run_core(raw_in, out_p, args.w, args.h, args.blur)

    inner = erode(reg, 6)
    print('画面 %dx%d，肤色掩码占 %.2f%%（内缩 6px 后 %.2f%%）'
          % (args.w, args.h, 100.0 * reg.mean(), 100.0 * inner.mean()))
    print('配置 model=%s tap25=%d band=%d bt=%g half=%d blur=%g'
          % (args.model, args.tap25, args.band, args.bt, args.half, args.blur))
    _note = ('← 不下发，第三方产品真实行为' if args.gold_bt < 0
             else '← 我们自己显式下发 bt1，不是产品行为' if args.gold_bt == 1
             else '')
    print('金标档位 gold_bt=%d %s' % (args.gold_bt, _note))
    print('引擎 : %s' % msg)
    print()
    print('%-18s %8s %8s' % ('区域', 'RMSE', '改动量'))
    print('-' * 38)
    print('%-18s %8.3f %8.3f' % ('全域', rmse_in(out, ref, np.ones_like(reg)),
                                 change_in(src, out, np.ones_like(reg))))
    print('%-18s %8.3f %8.3f' % ('肤色掩码内', rmse_in(out, ref, reg),
                                 change_in(src, out, reg)))
    print('%-18s %8.3f %8.3f' % ('内缩 6px', rmse_in(out, ref, inner),
                                 change_in(src, out, inner)))
    print()
    print('SDK 改动量   : %.3f' % change_in(src, ref, reg))
    print('我们改动量   : %.3f' % change_in(src, out, reg))
    print('空间相关     : %.3f' % spatial_corr(src, out, ref, reg))
    print('验收线       : RMSE < 2.0（C23 §6.1）')

    if args.dump:
        tag = '%s_%s_%s' % (args.tag, args.model,
                            ('band%d' % int(args.bt)) if args.band
                            else ('tap%d' % args.tap25))
        Image.fromarray(src[:, :, :3]).save(
            os.path.join(WORK, 'd_%s_src.png' % tag))
        Image.fromarray(ref[:, :, :3]).save(
            os.path.join(WORK, 'd_%s_sdk.png' % tag))
        Image.fromarray(out[:, :, :3]).save(
            os.path.join(WORK, 'd_%s_core.png' % tag))
        # 残差热图：×8 放大，看结构差异堆在哪
        dif = np.abs(out[:, :, :3].astype(np.int16)
                     - ref[:, :, :3].astype(np.int16)).max(axis=2)
        Image.fromarray(np.clip(dif * 8, 0, 255).astype(np.uint8)).save(
            os.path.join(WORK, 'd_%s_diff.png' % tag))
        # 改动量对照：我们改的 vs SDK 改的，同一放大倍数
        dsd = np.abs(ref[:, :, :3].astype(np.int16)
                     - src[:, :, :3].astype(np.int16)).max(axis=2)
        dou = np.abs(out[:, :, :3].astype(np.int16)
                     - src[:, :, :3].astype(np.int16)).max(axis=2)
        Image.fromarray(np.clip(dsd * 8, 0, 255).astype(np.uint8)).save(
            os.path.join(WORK, 'd_%s_chg_sdk.png' % tag))
        Image.fromarray(np.clip(dou * 8, 0, 255).astype(np.uint8)).save(
            os.path.join(WORK, 'd_%s_chg_core.png' % tag))
        print('对比图       : %s\\d_%s_*.png' % (WORK, tag))
    return 0


if __name__ == '__main__':
    sys.exit(main())
