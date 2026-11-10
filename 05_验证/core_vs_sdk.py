# -*- coding: utf-8 -*-
"""core_vs_sdk.py 0.1.0 —— 自研引擎（CoreEngine）vs SDK：逐档位离线对拍。

不加载 LegacySDK，只跑自研核（beauty_core_test.dll），再和 golden 里已固化的
SDK 输出比。判据是**档位响应曲线**：用户拖滑块看到的是曲线，不是单点。

## 0.1.0 修正：移除伪配置扫描，并写明本报告的能力边界

旧版在这里列了 8 组 `radius / sigmaSpace / sigmaColor / down` 做「配置扫描」，
并按曲线 RMSE 排序。2026-11-06 用独立子进程实测，这 8 组给出**完全相同的输出**：
当前 DLL 默认 `smoothModel = 1`、`s3Band = 1`（`01_源码/beauty_core.cpp`），
`process()` 走 `surface3RgbBand`，不消费上述四个双边滤波参数；即使显式设
`BEAUTY_SMOOTH_MODEL=legacy`，因 `freqMode = 1` 与 `lowPath = 3`，走的仍是盒式
高低频，同样不读它们。实测 `def_r2 / def_r6 / def_down2` 三份输出 sha256 前 16 位
全为 `36bf9d1547ff12f8`（maxdiff=0），`leg_r2 / leg_r6` 同为 `ac7c2af4bf2cbd6a`。
真正改变输出的是 `BEAUTY_SMOOTH_MODEL` 与 `blur` 档位（后者本就是本脚本的横轴）。

0.1.0 因此把配置收缩为**一组「当前默认核」**，并在运行时做一次逐字节敏感性自检；
报告也不再把 RMSE 当作「哪个配置更接近 SDK」的判据。

**能力边界（务必先读）**：本报告的 SDK 基准取自
`goldens_legacy/flat/blur%03d_bt1/out.raw`，即 `ref_golden.dll` 显式下发
`blur_type=1` 的输出。归档件 `ab-smooth-20261106.md`（已删除） 已说明产品实际
生效的不是 bt1 口径，所以这里的 RMSE **不能当作画质达标与否的判据**。78 组 flat
同理是 SDK 快照，当前自研引擎与 `blur050_bt1` 实测 maxdiff=11、
263782/1008640 个像素不同，本来就不该逐字节相等。

本机 78 组实测还给出一条方向性证据：同档位下 `bt2` 快照与当前引擎的差异最小
（25/50/75/100 四档的「不同通道数」与「平均绝对差」全部低于 `bt0` / `bt1`）；
换 `bt2` 基准后曲线 RMSE 由 14.9 降到 5.0。但 5.0 仍高于本脚本自述的经验阈值
「约 2 个百分点以内看不出差别」，且产品真值到底对应哪组 flat 需要用户确认，
所以 0.1.0 **不擅自更换基准**。要关闭根 `README.md` §8 第 3 项的
「画质 golden A/B」，仍需先定义产品真值基准与达标判据，本脚本不提供这两样。

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


# 0.1.0：只保留一组「当前默认核」。旧 8 组的 radius / ss / sc / down 在默认核
# 与 legacy 核下都不改变输出（逐字节相同，见文件头），再按 RMSE 排序只会误导。
# 这里的四个值只是沿用 BeautyCoreRun 的调用签名，不是可调维度。
CONFIGS = [
    ('当前默认核（smoothModel=1 / s3Band=1）', 2, 7.0, 40.0, 1),
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

    # ---- 0.1.0 参数敏感性自检 ----
    # 同一档位、两次不同 radius/sigmaSpace 的调用，若输出逐字节相同，就证明
    # BeautyCoreRun 这四个参数在当前默认核下不参与计算。结果必须显式打印，
    # 免得有人再把「按 RMSE 排序」当成选配置或判达标的依据。
    probes = []
    for i, (pr, pss) in enumerate(((2, 7.0), (6, 20.0))):
        p = os.path.join(OUT, '_cvs_probe_%d.raw' % i)
        rc, msg, _ = run_core(dll, src_p, p, 50, pr, pss, 40.0, 1)
        if rc != 0:
            print('[core] 自检调用失败 rc=%d %s' % (rc, msg))
            return 3
        probes.append(p)
    try:
        pa = np.fromfile(probes[0], np.uint8)
        pb = np.fromfile(probes[1], np.uint8)
        param_inert = bool(np.array_equal(pa, pb))
    finally:
        for p in probes:
            if os.path.exists(p):
                os.remove(p)
    if param_inert:
        print('[core] 自检：radius/sigmaSpace 在当前默认核下逐字节不改变输出；'
              '旧 8 组配置扫描为伪扫描，本表曲线只作记录、不作画质达标判据。')
    else:
        print('[core] 自检：参数会改变输出；若默认磨皮核已更换，请复核本脚本口径。')

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
    md = ['# 自研引擎（CoreEngine）vs SDK —— 档位曲线与性能（0.1.0 口径修正）\n',
          '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 台架：`core_vs_sdk.py` 0.1.0；参数敏感性自检 = %s'
          % ('参数不改变输出，旧 8 组配置扫描已移除' if param_inert
             else '参数会改变输出，需复核口径'),
          '> 自研核：当前 DLL 默认 `smoothModel=1 / s3Band=1` 的 surface3 带通路径，'
          '**不是** `beauty_smooth.cpp` 的双边滤波',
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
          '## 当前默认核的档位曲线（仅记录，不用于选配置或判达标）\n',
          '| 配置 | ' + ' | '.join('%d档' % lv for lv in LEVELS) +
          ' | 曲线RMSE(仅记录) | 耗时ms |',
          '|---|' + '---|' * (len(LEVELS) + 2)]
    for x in results:
        md.append('| %s | %s | %.2f | %.1f |'
                  % (x['label'], ' | '.join('%.1f' % k for k in x['keep']),
                     x['err'], x['ms']))
    md.append('')
    md.append('> 曲线RMSE 单位是「百分点」，小于约 2 个百分点看不出差别。'
              '耗时是 640×394 单帧、CPU、含混合。1080p 约为它的 4.5 倍。')
    md.append('')
    md.append('## 本报告不能作为画质 golden A/B 的依据\n')
    md.append('1. **旧 8 组配置扫描是伪扫描，已移除**。当前默认核走 '
              '`surface3RgbBand`，不消费 `radius / sigmaSpace / sigmaColor / down`；'
              '切到 legacy 核也因 `freqMode=1 / lowPath=3` 走盒式高低频而不读它们。'
              '独立进程实测不同配置的输出逐字节相同（maxdiff=0），'
              '所以此前那张「按 RMSE 排序」的表没有区分度。')
    md.append('2. **SDK 基准口径与产品不一致**。本表的 SDK 曲线取自 '
              '`goldens_legacy/flat/blur%03d_bt1/out.raw`，即 `ref_golden.dll` '
              '显式下发 `blur_type=1` 的输出；归档件 '
              '`ab-smooth-20261106.md`（已删除） 已说明产品实际生效的不是 bt1 口径，'
              '因此这里的 RMSE 不能回答「画质达不达标」。本机 78 组实测中 `bt2` '
              '快照与当前引擎的差异最小，换基准后 RMSE 由 14.9 降到 5.0；'
              '但 5.0 仍高于经验阈值约 2，且基准该选哪组需用户确认，'
              '故 0.1.0 未更换基准。')
    md.append('3. **78 组 flat 不适用于当前引擎的逐字节复现**。它们是 SDK 快照，'
              '当前自研引擎与 `blur050_bt1` 实测 maxdiff=11、'
              '263782/1008640 个像素不同，算法不同本就不该相等；'
              '`golden_capture.py verify` 验证的是 SDK 自身的复现率。')
    md.append('4. **要关闭根 `README.md` §8 第 3 项的「画质 golden A/B」，'
              '还缺产品真值基准的定义与判据**。本脚本只提供一组口径明确的档位曲线记录，'
              '不提供这两样，也不改 `01_源码/`。')

    out = os.path.join(OUT, 'core_vs_sdk.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('[core] -> %s' % out)
    with open(os.path.join(OUT, 'core_vs_sdk.json'), 'w', encoding='utf-8') as f:
        json.dump({'bench_version': '0.1.0',
                   'param_scan_inert': param_inert,
                   'sdk_basis': 'ref_golden.dll blur_type=1 (goldens_legacy/flat/*/out.raw)',
                   'usable_as_golden_ab': False,
                   'region': reg_name,
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
