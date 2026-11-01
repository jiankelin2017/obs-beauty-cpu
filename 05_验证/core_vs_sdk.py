# -*- coding: utf-8 -*-
"""自研引擎（CoreEngine）vs SDK —— 逐档位离线对拍。

不加载 LegacySDK，只跑自研核（beauty_core_test.dll），再和 golden 里已固化的
SDK 输出比。判据是**档位响应曲线**：用户拖滑块看到的是曲线，不是单点。

## 口径（2026-10-28 修正，重要）

以前用「SDK 磨皮 100 档改动过的像素（|Δ|>4）」当比较区域。实测这**不是皮肤区**：
face_src 上那个区域 12.99%，其中 **51.6% 是白蕾丝上衣和背景衣架**（高亮低饱和、
纹理多，一糊就变），真正的脸只占小部分。在那个区域上比，测的是「蕾丝被糊掉多少」，
不是「脸被磨了多少」—— 之前那个「曲线误差 1.09」就是这么来的，不成立。

现在改成 **SDK 自己的肤色掩码**（`goldens/masks/<scene>_fuai.mask`，fuai 分割结果，
192×256 低分辨率，最近邻放大到原尺寸）当比较区域。这才等于「OBS美颜摄像头认为的
皮肤」，也才对得上用户要的「数据对齐 OBS美颜摄像头」。

`CVS_REGION=sdk` 可切回旧口径，只用于对照，不要用它下结论。

用法（系统 Python 3.12，需 numpy）：
    python core_vs_sdk.py
"""

from __future__ import print_function

import ctypes
import json
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LEGACY = os.path.join(HERE, 'goldens_legacy')       # SDK 基线（产品实际路径）
SRC = os.path.join(HERE, 'goldens', 'src')
MASK_DIR = os.path.join(HERE, 'goldens', 'masks')
OUT = os.path.join(HERE, 'goldens', 'masks')
DLL = os.path.join(HERE, 'beauty_core_test.dll')
W, H = 640, 394
LEVELS = [0, 25, 50, 75, 100]
SCENE = 'face_src'


def load(p):
    return np.fromfile(p, np.uint8).reshape((H, W, 4))


def read_mask(p):
    """读 8 字节头 + mw*mh 的掩码文件（BeautyDumpMask / BeautyCoreMask 同一格式）。"""
    raw = open(p, 'rb').read()
    mw, mh = np.frombuffer(raw[:8], np.int32)
    return np.frombuffer(raw[8:], np.uint8).reshape((mh, mw))


def upscale_mask(m):
    """fuai 掩码是低分辨率的（192×256），最近邻放大到全尺寸。

    不用双线性：掩码是 0/255 的判决，插值会造出 0.5 这种中间值，
    再二值化等于偷偷改了边界。
    """
    if m.shape == (H, W):
        return m > 127
    ys = (np.arange(H) * m.shape[0]) // H
    xs = (np.arange(W) * m.shape[1]) // W
    return m[ys][:, xs] > 127


def detail(img):
    g = img.astype(np.float32)
    lap = np.zeros(g.shape[:2], np.float32)
    lap[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
                             - g[1:-1, :-2] - g[1:-1, 2:]).mean(axis=2) / 3.0
    return lap


def run_core(dll, raw_in, raw_out, blur, radius, ss, sc, down):
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    msg = ctypes.create_string_buffer(512)
    rc = dll.BeautyCoreRun(raw_in.encode('utf-8'), raw_out.encode('utf-8'),
                           W, H, float(blur), int(radius), float(ss), float(sc),
                           int(down), msg, 512)
    ms = 0.0
    m = msg.value.decode('utf-8', 'replace')
    for tok in m.split():
        if tok.startswith('ms='):
            try:
                ms = float(tok[3:])
            except ValueError:
                pass
    return rc, m, ms


# 配置扫描：down 是降采样倍率，radius/sigmaSpace 按低分辨率解释。
# 降采样已证伪（曲线误差 27+），保留 down2/down4 两组仅作反例留档。
CONFIGS = [
    ('当前默认 r2/ss7', 2, 7.0, 40.0, 1),
    ('r3/ss10', 3, 10.0, 40.0, 1),
    ('r4/ss13.5', 4, 13.5, 40.0, 1),
    ('r4/ss13.5 sc50', 4, 13.5, 50.0, 1),
    ('r5/ss17', 5, 17.0, 40.0, 1),
    ('r6/ss20', 6, 20.0, 40.0, 1),
    ('r4/ss13.5 sc60', 4, 13.5, 60.0, 1),
    ('反例 r2/ss6.75 down2', 2, 6.75, 40.0, 2),
]


def main():
    if not os.path.exists(DLL):
        print('[core] missing %s (run build_core_test.bat)' % DLL)
        return 2
    dll = ctypes.WinDLL(DLL)
    os.makedirs(OUT, exist_ok=True)

    src_p = os.path.join(SRC, SCENE + '.raw')
    src = load(src_p)
    sdk100 = load(os.path.join(LEGACY, 'flat', 'blur100_bt1', 'out.raw'))

    # ---- 比较区域 ----
    # 旧口径（仅对照）：SDK 100 档改动的像素。实测是纹理区，不是皮肤区。
    reg_sdk = np.abs(src[:, :, :3].astype(np.int16)
                     - sdk100[:, :, :3].astype(np.int16)).max(axis=2) > 4
    # 新口径（默认）：SDK 自己的肤色掩码
    fmp = os.path.join(MASK_DIR, SCENE + '_fuai.mask')
    have_fuai = os.path.exists(fmp)
    reg_fuai = upscale_mask(read_mask(fmp)) if have_fuai else None

    mode = os.environ.get('CVS_REGION', 'fuai').lower()
    if mode == 'sdk' or reg_fuai is None:
        reg = reg_sdk
        reg_name = 'SDK 100 档改动区（纹理区，仅对照）'
        if reg_fuai is None and mode != 'sdk':
            print('[core] 警告：缺 %s，退回旧口径' % fmp)
    else:
        reg = reg_fuai
        reg_name = 'SDK 肤色掩码（fuai，%s）' % SCENE

    # 证据：说明旧口径为什么不能用
    import cv2
    hsv = cv2.cvtColor(src[:, :, :3], cv2.COLOR_RGB2HSV)
    sat, val = hsv[:, :, 1].astype(np.float32), hsv[:, :, 2].astype(np.float32)
    white = (val > 150) & (sat < 60)
    print('[core] 区域：%s' % reg_name)
    print('[core]   区域占画面 %.2f%%' % (100.0 * reg.mean()))
    print('[core]   区域内「高亮低饱和（白衣/背景）」占 %.1f%%' % (100.0 * white[reg].mean()))
    print('[core]   对照：SDK 改动区 %.2f%%，其中白衣/背景 %.1f%%'
          % (100.0 * reg_sdk.mean(), 100.0 * white[reg_sdk].mean()))
    if reg_fuai is not None:
        print('[core]   肤色掩码 %.2f%%  vs  SDK 改动区 %.2f%%  交集 %.2f%%'
              % (100.0 * reg_fuai.mean(), 100.0 * reg_sdk.mean(),
                 100.0 * (reg_fuai & reg_sdk).mean()))

    d_src = float(detail(src[:, :, :3])[reg].mean())

    sdk_keep = {}
    for lv in LEVELS:
        p = os.path.join(LEGACY, 'flat', 'blur%03d_bt1' % lv, 'out.raw')
        if os.path.exists(p):
            sdk_keep[lv] = float(100.0 * detail(load(p)[:, :, :3])[reg].mean() / d_src)
    print('[core] SDK 曲线: ' + '  '.join('%d=%.1f' % (k, v)
                                          for k, v in sorted(sdk_keep.items())))

    results = []
    for label, r, ss, sc, down in CONFIGS:
        keeps, mss = [], []
        for lv in LEVELS:
            tmp = os.path.join(OUT, '_core_tmp.raw')
            rc, msg, ms = run_core(dll, src_p, tmp, lv, r, ss, sc, down)
            if rc != 0:
                keeps.append(float('nan'))
                continue
            core = load(tmp)[:, :, :3]
            keeps.append(100.0 * detail(core)[reg].mean() / d_src)
            if lv in (50, 100):
                mss.append(ms)
            os.remove(tmp)
        err = float(np.sqrt(np.mean([(a - sdk_keep[lv]) ** 2
                                     for a, lv in zip(keeps, LEVELS)
                                     if lv in sdk_keep])))
        avg_ms = sum(mss) / len(mss) if mss else 0.0
        results.append({'label': label, 'r': r, 'ss': ss, 'sc': sc, 'down': down,
                        'keep': [round(float(k), 1) for k in keeps],
                        'err': round(err, 2), 'ms': round(avg_ms, 1)})
        print('  %-24s keep=%s  曲线RMSE=%.2f  %.1fms'
              % (label, '/'.join('%.1f' % k for k in keeps), err, avg_ms))

    results.sort(key=lambda x: x['err'])
    md = ['# 自研引擎（CoreEngine）vs SDK —— 档位曲线与性能\n',
          '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 自研核：`beauty_smooth.cpp` 双边滤波（定点 LUT）+ 线性混合',
          '> 素材 %s·%d×%d；**比较区域 = %s**' % (SCENE, W, H, reg_name),
          '',
          '## 口径说明（2026-10-28 修正）\n',
          '旧口径「SDK 磨皮 100 档改动过的像素（|Δ|>4）」**不是皮肤区**：'
          '该区域 %.2f%% 的画面里，**%.1f%% 是高亮低饱和的白蕾丝上衣与背景衣架**。'
          '在那个区域上比，测的是「蕾丝被糊掉多少」，不是「脸被磨了多少」。'
          % (100.0 * reg_sdk.mean(), 100.0 * white[reg_sdk].mean()),
          '',
          '现口径取 **SDK 自己的肤色掩码（fuai 分割）**：%.2f%% 画面，'
          '区域内白衣/背景只占 %.1f%%。这才等于「OBS美颜摄像头认为的皮肤」。'
          % (100.0 * reg.mean(), 100.0 * white[reg].mean()),
          '',
          '## SDK 基准曲线（区域细节保留 %）\n',
          '| 档位 | ' + ' | '.join(str(lv) for lv in LEVELS) + ' |',
          '|---|' + '---|' * len(LEVELS),
          '| SDK | ' + ' | '.join('%.1f' % sdk_keep.get(lv, 0) for lv in LEVELS) + ' |',
          '',
          '## 配置扫描（按曲线误差排序）\n',
          '| 配置 | ' + ' | '.join('%d档' % lv for lv in LEVELS) +
          ' | 曲线RMSE | 耗时ms |',
          '|---|' + '---|' * (len(LEVELS) + 2)]
    for x in results:
        md.append('| %s | %s | %.2f | %.1f |'
                  % (x['label'], ' | '.join('%.1f' % k for k in x['keep']),
                     x['err'], x['ms']))
    md.append('')
    md.append('> 曲线RMSE 单位是「百分点」，小于约 2 个百分点看不出差别。'
              '耗时是 640×394 单帧、CPU、含混合。1080p 约为它的 4.5 倍。')

    out = os.path.join(OUT, 'core_vs_sdk.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('[core] -> %s' % out)
    with open(os.path.join(OUT, 'core_vs_sdk.json'), 'w', encoding='utf-8') as f:
        json.dump({'region': reg_name,
                   'region_pct': float(100.0 * reg.mean()),
                   'region_white_pct': float(100.0 * white[reg].mean()),
                   'reg_sdk_pct': float(100.0 * reg_sdk.mean()),
                   'reg_sdk_white_pct': float(100.0 * white[reg_sdk].mean()),
                   'sdk_keep': {int(k): float(v) for k, v in sdk_keep.items()},
                   'results': results},
                  f, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
