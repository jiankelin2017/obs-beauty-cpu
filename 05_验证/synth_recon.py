# -*- coding: utf-8 -*-
"""跨画幅可行性侦察：fuai 在 720p / 1080x1920 上还能不能检出人脸。

背景
----
C23 §6.0 要求在动 25 tap 之前先验证核几何。原本的计划是「把合成探针嵌进
真人脸里、反演环半径」。但 golden DLL 的 W/H 是入参、引擎内部也不缩放工作
分辨率，于是有一条更便宜且信号强得多的路：

    核的 UV 半轴若真是固定常量（sx=0.002640845, sy=0.0046875），
    那么同一个核在不同画幅上的**像素**各向异性会剧烈变化：

        640x394   -> sx*W / sy*H = 1.690/1.847 = 1.093
        1280x720  -> 3.380/3.375 = 1.002   ← 恰好各向同性
        1080x1920 -> 2.852/9.000 = 3.168   ← 强椭圆

    三画幅摆在一起就是判决：固定 UV 半轴 → (1.09, 1.00, 3.17)；
    核自适应画幅 → 三个都是 1.00。中间那个 3.17 是噪声淹没不了的量级。

前提是 fuai 得在这些画幅上照样检出人脸，否则实验作废。本脚本只做这一步
侦察：把 face_src 等比 letterbox 到三种画幅，各跑一次 BeautyDumpMask。

用法
----
    python synth_recon.py
"""
import ctypes
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'ref_golden.dll')
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')
SRC_PNG = os.path.join(HERE, 'face_src.png')
OUT = os.path.join(HERE, 'goldens', 'masks')

# 核的 UV 半轴（源码常量）。像素各向异性 = sy*H / sx*W：
# sy 大 -> y 方向核更宽 -> y 的 f50 更小 -> f50_x/f50_y > 1。
UV_SX, UV_SY = 0.002640845, 0.0046875
SIZES = [
    (640, 394),
    (1280, 720),
    (1080, 1920),
]
WARMUP = 6


def letterbox(path, w, h):
    """等比缩放 + 居中 letterbox，RGBA uint8。与 golden_capture.py 同口径。"""
    im = Image.open(path)
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    iw, ih = im.size
    scale = min(float(w) / iw, float(h) / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    canvas.paste(im, ((w - nw) // 2, (h - nh) // 2))
    return np.asarray(canvas, dtype=np.uint8)


def load_dll():
    if not os.path.exists(DLL):
        print('[recon] DLL not found: %s' % DLL)
        sys.exit(2)
    d = ctypes.WinDLL(DLL)
    d.BeautyDumpMask.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    d.BeautyDumpMask.restype = ctypes.c_int
    d.RefGoldenRun.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(ctypes.c_double), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    return d


def warmup(d, raw, out, w, h, n=WARMUP):
    """热身：fuai 的检测器首帧在建会话，faces 要到第 2 帧才出来。

    必须先跑满 RefGoldenRun 若干帧，再调 BeautyDumpMask，否则拿到的
    是冷启动那一帧的掩码（faces=0、coverage 偏小）。OBS 日志里
    frame#0 faces=0 / frame#1 faces=1 就是这个现象。
    """
    panel = (ctypes.c_double * 11)()
    panel[0] = 0.0          # blur=0：热身只求检测器收敛，不引入任何效果
    msg = ctypes.create_string_buffer(512)
    last = ''
    for _ in range(n):
        d.RefGoldenRun(ENGINE_DIR.encode('utf-8'), raw.encode('utf-8'),
                        out.encode('utf-8'), w, h, panel, 11,
                        1, 1, 0, 0, msg, 512)
        last = msg.value.decode('utf-8', 'replace')
    return last


def parse_msg(msg):
    out = {}
    for tok in msg.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            try:
                out[k] = float(v) if '.' in v else int(v)
            except ValueError:
                out[k] = v
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    d = load_dll()
    rows = []
    for w, h in SIZES:
        arr = letterbox(SRC_PNG, w, h)
        raw = os.path.join(OUT, '_recon_%dx%d.raw' % (w, h))
        arr.tofile(raw)
        mask = os.path.join(OUT, '_recon_%dx%d.mask' % (w, h))
        if os.path.exists(mask):
            os.remove(mask)
        wmsg = warmup(d, raw, os.path.join(OUT, '_recon_%dx%d.out' % (w, h)),
                      w, h)
        msg = ctypes.create_string_buffer(512)
        rc = d.BeautyDumpMask(ENGINE_DIR.encode('utf-8'), raw.encode('utf-8'),
                              w, h, mask.encode('utf-8'), msg, 512)
        txt = msg.value.decode('utf-8', 'replace')
        info = parse_msg(txt)
        pred = (UV_SY * h) / (UV_SX * w)
        winfo = parse_msg(wmsg)
        rows.append((w, h, rc, winfo.get('faces', -1),
                     info.get('coverage', -1.0),
                     info.get('mask', '?'), pred, txt))
        print('  %4dx%-4d rc=%d  %s' % (w, h, rc, txt))
        print('            warmup(last): %s' % wmsg)

    print()
    print('%-11s %-5s %-9s %-11s %-7s' % ('画幅', 'faces', 'coverage',
                                          'mask', '预期各向异性'))
    print('-' * 52)
    ok = True
    for w, h, rc, faces, cov, mk, pred, _ in rows:
        flag = '' if faces and faces > 0 else '   <-- 无人脸，作废'
        if not faces or faces <= 0:
            ok = False
        print('%-11s %-5s %-9s %-11s %-7.3f%s'
              % ('%dx%d' % (w, h), faces, round(cov, 4), mk, pred, flag))
    print()
    print('结论：%s' % ('三画幅都能检出人脸，跨画幅各向异性判决可行。'
                      if ok else '至少一个画幅检不出人脸，需换素材或换画幅。'))


if __name__ == '__main__':
    main()
