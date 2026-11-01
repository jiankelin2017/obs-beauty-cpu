# -*- coding: utf-8 -*-
"""基线冻结（M0）—— 趁 LegacySDK 还在手上，把它的输出固化成回归集。

对应《自研美颜引擎替换方案 v1》的 M0：
    goldens/flat/    静态帧（不同场景 x 磨皮档 x blur_type x 美白/红润/锐化）
    goldens/motion/  运动帧序列（平移，含 faces=0 段）
    每组存 输入.raw / 输出.raw / params.json
    baseline.md      每组的细节保留率 / 亮度变化 / 改动像素 / faces / 掩码覆盖率

用系统 Python 3.12 跑（需要 numpy + PIL）：
    C:\\Users\\<user>\\AppData\\Local\\Programs\\Python\\Python312\\python.exe

用法：
    python golden_capture.py prep      准备素材（png -> 640x394 RGBA raw + 合成对照）
    python golden_capture.py all       跑完整矩阵（flat: 每组独立进程；motion: 同进程连续帧）
    python golden_capture.py verify    复现性验证：重跑 flat 全组，逐字节比对
    python golden_capture.py report    只根据已有输出重算 baseline.md

为什么 flat 每组要用**独立进程**：SDK 内部的人脸跟踪器是进程全局状态，同一进程里
先跑哪一档会影响后一档的跟踪结果。分组独立进程能让每组成为可独立复现的快照；
motion 集则必须在同一进程里连续调用，才能反映真实的时序行为。
"""

from __future__ import print_function

import ctypes
import json
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))

# 语义皮肤掩码的两种状态，基线两套都要采：
#   on  = fuai AI 分割可用（需要明文 bundle）—— 完整能力，自研引擎的目标
#   off = 退回 YCbCr 颜色启发式 —— **发布出去的产品实际跑的就是这一条路**，
#         因为 04_依赖与SDK/installer-stage 里只有加密的 ai_face_processor_pc.bundle，
#         nsi 打的也是它。要对齐「老观感」，对标的是 off 这一套。
REGION = os.environ.get('GOLDEN_REGION', 'on').strip().lower()
if REGION == 'off':
    os.environ['BEAUTY_REGION_OFF'] = '1'

GOLD = os.path.join(HERE, 'goldens' if REGION == 'on' else 'goldens_legacy')
SRC = os.path.join(GOLD, 'src')
FLAT = os.path.join(GOLD, 'flat')
MOTION = os.path.join(GOLD, 'motion')
DLL = os.path.join(HERE, 'ref_golden.dll')

W, H = 640, 394
NFRAME_BYTES = W * H * 4

# 引擎数据目录（含 CNamaSDK.dll）。可用环境变量 GOLDEN_ENGINE_DIR 覆盖。
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')

# 参数表顺序，必须与 legacy_engine.h 的 P_* 一致
P_BLUR, P_CLARITY, P_WHITEN, P_RED, P_SHARPEN, P_GLOBAL_SHARP, \
    P_THREED, P_EYEBRIGHT, P_POUCH, P_NASOLABIAL, P_DELSPOT = range(11)
P_COUNT = 11

# ---------------------------------------------------------------------------
# 素材
# ---------------------------------------------------------------------------
# (id, 源文件名 or None=合成, 说明)
SCENES = [
    ('face_src', 'face_src.png', '基准人脸（640x394，原尺寸）'),
    ('crop_a', 'crop_05896fdb.png', '宽幅裁剪 A'),
    ('crop_b', 'crop_0f897ccf.png', '宽幅裁剪 B'),
    ('crop_c', 'crop_d29b5c62.png', '裁剪 C'),
    ('crop_d', 'crop_e08f64a3.png', '裁剪 D'),
    ('look1', 'look1.png', '实拍 1'),
    ('look2', 'look2.png', '实拍 2'),
    ('obs_grab', 'obs_grab.png', 'OBS 抓帧'),
    ('noface_skin', None, '合成：大面积肤色块，无人脸（faces=0 对照）'),
    ('noface_gray', None, '合成：中灰渐变，无人脸（滤镜/全局改动对照）'),
]

MAIN_SCENE = 'face_src'


def letterbox_rgba(path, w=W, h=H):
    """等比缩放 + 居中 letterbox 到 w x h，返回 RGBA uint8 数组。不变形。"""
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


def synth_skin_block(w=W, h=H):
    """无人脸的大面积肤色块：用来验证「只磨皮肤 / 只提亮皮肤」不会误伤。"""
    a = np.zeros((h, w, 4), dtype=np.uint8)
    y, x = np.mgrid[0:h, 0:w]
    # 三个不同亮度的肤色色块 + 一块米色（接近肤色但不是皮肤）
    blocks = [
        ((0, 0, w // 2, h // 2), (226, 178, 150)),
        ((w // 2, 0, w, h // 2), (198, 142, 116)),
        ((0, h // 2, w // 2, h), (242, 205, 178)),
        ((w // 2, h // 2, w, h), (214, 198, 176)),  # 米色墙
    ]
    for (x0, y0, x1, y1), (r, g, b) in blocks:
        a[y0:y1, x0:x1, 0] = r
        a[y0:y1, x0:x1, 1] = g
        a[y0:y1, x0:x1, 2] = b
    a[:, :, 3] = 255
    return a


def synth_gray_ramp(w=W, h=H):
    """中灰横向量化到灰阶 ramp：用来验证全局滤镜 / 整帧提亮。"""
    x = np.linspace(0, 255, w).astype(np.uint8)
    a = np.zeros((h, w, 4), dtype=np.uint8)
    a[:, :, 0] = x[None, :]
    a[:, :, 1] = x[None, :]
    a[:, :, 2] = x[None, :]
    a[:, :, 3] = 255
    return a


def cmd_prep():
    os.makedirs(SRC, exist_ok=True)
    made = []
    for sid, fname, desc in SCENES:
        if fname:
            arr = letterbox_rgba(os.path.join(HERE, fname))
        elif sid == 'noface_skin':
            arr = synth_skin_block()
        elif sid == 'noface_gray':
            arr = synth_gray_ramp()
        else:
            continue
        raw = os.path.join(SRC, sid + '.raw')
        png = os.path.join(SRC, sid + '.png')
        arr.tofile(raw)
        Image.fromarray(arr, 'RGBA').save(png)
        made.append((sid, desc, arr.shape))
        print('  prepared %-14s %s' % (sid, desc))
    meta = [{'id': s, 'desc': d, 'size': '%dx%d' % (a[1], a[0])}
            for s, d, a in made]
    with open(os.path.join(SRC, 'scenes.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print('[prep] %d scenes -> %s' % (len(made), SRC))


# ---------------------------------------------------------------------------
# 参数矩阵
# ---------------------------------------------------------------------------
def base_panel(**kw):
    p = [0.0] * P_COUNT
    p[P_BLUR] = kw.get('blur', 50)
    p[P_WHITEN] = kw.get('whiten', 0)
    p[P_RED] = kw.get('red', 0)
    p[P_SHARPEN] = kw.get('sharpen', 0)
    p[P_CLARITY] = kw.get('clarity', 0)
    return p


def build_matrix():
    """返回 [(case_id, scene, panel, blur_type, skin_detect, smooth_mode)]"""
    cases = []

    # 1) 主矩阵：基准人脸 x 磨皮 6 档 x blur_type 3 档
    for bt in (1, 0, 2):
        for b in (0, 1, 25, 50, 75, 100):
            cases.append(('blur%03d_bt%d' % (b, bt), MAIN_SCENE,
                          base_panel(blur=b), bt, 1, 0))

    # 2) 其余场景 x 磨皮 5 档（默认 blur_type=1）
    for sid, _, _ in SCENES:
        if sid == MAIN_SCENE:
            continue
        for b in (0, 25, 50, 75, 100):
            cases.append(('%s_blur%03d' % (sid, b), sid,
                          base_panel(blur=b), 1, 1, 0))

    # 3) 美白 / 红润 / 锐化各 3 档（磨皮 50 基线）
    for v in (0, 50, 100):
        cases.append(('whiten%03d' % v, MAIN_SCENE,
                      base_panel(blur=50, whiten=v), 1, 1, 0))
        cases.append(('red%03d' % v, MAIN_SCENE,
                      base_panel(blur=50, red=v), 1, 1, 0))
        cases.append(('sharpen%03d' % v, MAIN_SCENE,
                      base_panel(blur=50, sharpen=v), 1, 1, 0))

    # 4) 磨皮模式 4 档（磨皮 50）
    for m in (0, 1, 2, 3):
        cases.append(('smoothm%d' % m, MAIN_SCENE, base_panel(blur=50), 1, 1, m))

    # 5) 精准美肤 开/关 对照（验证「只磨皮肤」的边界）
    for sd in (1, 0):
        cases.append(('skindet%d' % sd, MAIN_SCENE, base_panel(blur=50), 1, sd, 0))

    return cases


# ---------------------------------------------------------------------------
# 引擎调用
# ---------------------------------------------------------------------------
def load_dll():
    if not os.path.exists(DLL):
        print('[golden] DLL not found: %s (run build_golden.bat first)' % DLL)
        sys.exit(2)
    d = ctypes.WinDLL(DLL)
    d.RefGoldenRun.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(ctypes.c_double), ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int]
    d.RefGoldenRun.restype = ctypes.c_int
    return d


def run_one(dll, in_raw, out_raw, panel, blur_type=1, skin_detect=1,
            smooth_mode=0, reset=1):
    arr = (ctypes.c_double * P_COUNT)(*panel)
    msg = ctypes.create_string_buffer(512)
    rc = dll.RefGoldenRun(
        ENGINE_DIR.encode('utf-8'), in_raw.encode('utf-8'), out_raw.encode('utf-8'),
        W, H, arr, P_COUNT, blur_type, skin_detect, smooth_mode, reset,
        msg, 512)
    return rc, msg.value.decode('utf-8', 'replace')


def parse_msg(msg):
    out = {'faces': -1, 'coverage': -1.0, 'sdk': -1.0, 'item': -1, 'region': -1}
    for tok in msg.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            try:
                out[k] = float(v) if '.' in v else int(v)
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------------------
# 指标
# ---------------------------------------------------------------------------
def load_raw(path):
    a = np.fromfile(path, dtype=np.uint8)
    if a.size != NFRAME_BYTES:
        raise IOError('%s: %d bytes, expected %d' % (path, a.size, NFRAME_BYTES))
    return a.reshape((H, W, 4))


def detail(a):
    """mean |Laplacian| / 3，与 obs-beauty.cpp 的 frame_detail 同口径。"""
    g = a[:, :, :3].astype(np.float32)
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] \
        - g[1:-1, :-2] - g[1:-1, 2:]
    return float(np.abs(lap).mean()) / 3.0


def metrics(inp, out):
    d_in, d_out = detail(inp), detail(out)
    di = out[:, :, :3].astype(np.int16) - inp[:, :, :3].astype(np.int16)
    changed = float((np.abs(di).max(axis=2) > 4).mean()) * 100.0
    return {
        'detail_in': round(d_in, 4),
        'detail_out': round(d_out, 4),
        'detail_keep_pct': round(100.0 * d_out / d_in, 2) if d_in > 0 else 0.0,
        'dmean': round(float(di.mean()), 3),
        'changed_px_pct': round(changed, 2),
        'max_abs_diff': int(np.abs(di).max()),
    }


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------
def cmd_run_one(args):
    """worker：单次采集（每个 flat 组一个独立进程，保证可复现）。"""
    spec = json.loads(args[0])
    dll = load_dll()
    panel = spec['panel']
    bt = spec.get('blur_type', 1)
    sd = spec.get('skin_detect', 1)
    sm = spec.get('smooth_mode', 0)
    # 预热：每组进程里先跑几帧再记录。首帧含 GL 纹理/模型的懒加载，
    # SDK 耗时能到 20~40ms，不能代表稳态；人脸跟踪器也需要看几帧才稳定。
    # 每帧都 reset=1，保证被记录的那一帧仍是从干净状态开始的。
    warm = int(spec.get('warmup', 2))
    tmp = spec['out'] + '.warm'
    rc, msg = 0, ''
    for _ in range(warm):
        rc, msg = run_one(dll, spec['in'], tmp, panel, bt, sd, sm, 1)
        if rc != 0:
            break
    if rc == 0:
        rc, msg = run_one(dll, spec['in'], spec['out'], panel, bt, sd, sm,
                          spec.get('reset', 1))
    if os.path.exists(tmp):
        os.remove(tmp)
    print('rc=%d' % rc)
    print('msg=%s' % msg)
    return 0 if rc == 0 else 1


def cmd_all(_args=None):
    os.makedirs(FLAT, exist_ok=True)
    os.makedirs(MOTION, exist_ok=True)
    cases = build_matrix()
    print('[all] %d flat cases' % len(cases))
    t0 = time.time()
    ok = 0
    for i, (cid, scene, panel, bt, sd, sm) in enumerate(cases):
        d = os.path.join(FLAT, cid)
        os.makedirs(d, exist_ok=True)
        in_raw = os.path.join(SRC, scene + '.raw')
        out_raw = os.path.join(d, 'out.raw')
        spec = {'in': in_raw, 'out': out_raw, 'panel': panel,
                'blur_type': bt, 'skin_detect': sd, 'smooth_mode': sm,
                'reset': 1, 'warmup': 2}
        with open(os.path.join(d, 'params.json'), 'w', encoding='utf-8') as f:
            json.dump({'case': cid, 'scene': scene, 'panel': panel,
                       'blur_type': bt, 'skin_detect': sd, 'smooth_mode': sm},
                      f, ensure_ascii=False, indent=2)
        r = subprocess.run([sys.executable, os.path.abspath(__file__),
                            'run-one', json.dumps(spec, ensure_ascii=False)],
                           capture_output=True, text=True)
        msg = [l for l in (r.stdout or '').splitlines() if l.startswith('msg=')]
        msg = msg[0][4:] if msg else ((r.stderr or '').strip()[:120])
        info = parse_msg(msg)
        with open(os.path.join(d, 'engine.json'), 'w', encoding='utf-8') as f:
            json.dump({'rc': r.returncode, 'msg': msg, **info}, f, ensure_ascii=False, indent=2)
        if r.returncode == 0:
            ok += 1
        print('  [%3d/%d] %-22s rc=%d %s' % (i + 1, len(cases), cid, r.returncode, msg[:72]))
    print('[all] flat done: %d/%d ok, %.0fs' % (ok, len(cases), time.time() - t0))

    # ---- motion：同进程连续帧（平移序列）----
    print('[all] motion sequences')
    src = load_raw(os.path.join(SRC, MAIN_SCENE + '.raw'))
    for name, steps in (('pan', [0, 6, 12, 18, 24, 30]),
                        ('faces_out', [0, 40, 80, 120, 160, 220])):
        d = os.path.join(MOTION, name)
        os.makedirs(d, exist_ok=True)
        dll = load_dll()
        recs = []
        for k, dx in enumerate(steps):
            if name == 'faces_out':
                frame = np.roll(src, dx, axis=1)
                frame[:, :dx, :] = 0        # 把脸推出画面左侧
            else:
                frame = np.roll(src, dx, axis=1)
            raw_in = os.path.join(d, 'seq_%03d.raw' % k)
            raw_out = os.path.join(d, 'out_%03d.raw' % k)
            frame.astype(np.uint8).tofile(raw_in)
            rc, msg = run_one(dll, raw_in, raw_out, base_panel(blur=50),
                              1, 1, 0, reset=(1 if k == 0 else 0))
            recs.append({'frame': k, 'shift': dx, 'rc': rc, 'msg': msg,
                         **parse_msg(msg)})
            print('    %s#%d dx=%-4d rc=%d %s' % (name, k, dx, rc, msg[:64]))
        with open(os.path.join(d, 'params.json'), 'w', encoding='utf-8') as f:
            json.dump({'case': name, 'scene': MAIN_SCENE, 'panel': base_panel(blur=50),
                       'blur_type': 1, 'skin_detect': 1, 'smooth_mode': 0,
                       'shifts': steps, 'frames': recs}, f, ensure_ascii=False, indent=2)
    print('[all] DONE %.0fs' % (time.time() - t0))


def cmd_report(_args=None):
    rows = []
    for cid in sorted(os.listdir(FLAT)):
        d = os.path.join(FLAT, cid)
        pj = os.path.join(d, 'params.json')
        oj = os.path.join(d, 'out.raw')
        if not (os.path.exists(pj) and os.path.exists(oj)):
            continue
        p = json.load(open(pj, encoding='utf-8'))
        e = {}
        ej = os.path.join(d, 'engine.json')
        if os.path.exists(ej):
            e = json.load(open(ej, encoding='utf-8'))
        try:
            inp = load_raw(os.path.join(SRC, p['scene'] + '.raw'))
            out = load_raw(oj)
            m = metrics(inp, out)
        except Exception as ex:
            m = {'detail_in': 0, 'detail_out': 0, 'detail_keep_pct': 0,
                 'dmean': 0, 'changed_px_pct': 0, 'max_abs_diff': 0}
            print('  [warn] %s: %s' % (cid, ex))
        rows.append({'case': cid, 'scene': p['scene'],
                     'blur': p['panel'][P_BLUR], 'whiten': p['panel'][P_WHITEN],
                     'red': p['panel'][P_RED], 'sharpen': p['panel'][P_SHARPEN],
                     'blur_type': p['blur_type'], 'skin_detect': p['skin_detect'],
                     'smooth_mode': p['smooth_mode'],
                     'faces': e.get('faces', -1), 'coverage': e.get('coverage', -1),
                     'sdk_ms': e.get('sdk', -1), **m})

    mot = []
    for name in sorted(os.listdir(MOTION)):
        pj = os.path.join(MOTION, name, 'params.json')
        if os.path.exists(pj):
            mot.append(json.load(open(pj, encoding='utf-8')))

    md = []
    md.append('# SDK 基线（M0）—— 3.0.19 / LegacySDK + fuai（语义掩码 = %s）\n'
              % ('on · fuai AI 分割' if REGION == 'on' else 'off · 颜色启发式（产品实际路径）'))
    md.append('> 自动生成：%s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    md.append('> 引擎数据目录：%s' % ENGINE_DIR)
    md.append('> 帧尺寸：%dx%d RGBA8' % (W, H))
    if REGION == 'off':
        md.append('> **这一套对应发布出去的产品实际行为**：`installer-stage` 与 nsi 里'
                  '只有加密 `ai_face_processor_pc.bundle`，没有明文件，'
                  '所以 fuai 语义掩码在用户机器上是不可用的，'
                  '全部效果退回 v1.4 的 YCbCr 颜色判据。对齐「老观感」要用这一套。')
    else:
        md.append('> 这一套是**完整能力**（AI 皮肤分割开）。产品当前达不到，'
                  '是自研引擎的目标；不要拿它对标老观感。')
    md.append('')
    md.append('## 复现方式\n')
    md.append('```')
    md.append('06_离线验证\\build_golden.bat')
    md.append('python golden_capture.py prep')
    md.append('python golden_capture.py all')
    md.append('python golden_capture.py verify   # 逐字节复现率应为 100%')
    md.append('```\n')
    md.append('flat 组每组跑在**独立进程**（SDK 人脸跟踪是进程全局状态，'
              '同进程内先跑哪一档会影响后一档）；motion 组必须同进程连续调用。\n')
    md.append('## flat 集（%d 组）\n' % len(rows))
    md.append('| case | 场景 | 磨皮 | 美白 | 红润 | 锐化 | blur_type | skin_det | 模式 '
              '| faces | 掩码覆盖 | 细节 in | 细节 out | 保留率% | Δ亮度 | 改动像素% | 最大差 | SDK ms |')
    md.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        md.append('| %(case)s | %(scene)s | %(blur).0f | %(whiten).0f | %(red).0f | '
                  '%(sharpen).0f | %(blur_type)d | %(skin_detect)d | %(smooth_mode)d | '
                  '%(faces)s | %(coverage).4f | %(detail_in).3f | %(detail_out).3f | '
                  '%(detail_keep_pct).2f | %(dmean).2f | %(changed_px_pct).2f | '
                  '%(max_abs_diff)d | %(sdk_ms).1f |' % r)
    md.append('')
    md.append('## motion 集\n')
    for m in mot:
        md.append('### %s（平移 %s px）\n' % (m['case'], m['shifts']))
        md.append('| 帧 | 位移 | faces | 掩码覆盖 | SDK ms |')
        md.append('|---|---|---|---|---|')
        for f in m['frames']:
            md.append('| %d | %d | %s | %s | %.1f |' % (
                f['frame'], f['shift'], f.get('faces', -1),
                f.get('coverage', -1), f.get('sdk', -1)))
        md.append('')
    md.append('## 指标口径\n')
    md.append('- **细节**：mean |Laplacian| / 3，与 `obs-beauty.cpp` 的 '
              '`frame_detail` 同口径。越小越平滑。')
    md.append('- **保留率**：输出细节 / 输入细节 × 100%。磨皮档位的核心刻度。')
    md.append('- **Δ亮度**：输出减输入的 RGB 均值差（正 = 变亮）。')
    md.append('- **改动像素**：单通道差 > 4 的像素占比。')
    md.append('- **掩码覆盖**：fuai 皮肤分割的覆盖率（`LegacyEngine::regionCoverage`）。\n')

    out = os.path.join(GOLD, 'baseline.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('[report] %d flat + %d motion -> %s' % (len(rows), len(mot), out))
    with open(os.path.join(GOLD, 'baseline.json'), 'w', encoding='utf-8') as f:
        json.dump({'flat': rows, 'motion': mot}, f, ensure_ascii=False, indent=2)


def cmd_verify(_args=None):
    """复现性验证：重跑每组到临时文件，与已存输出逐字节比对。"""
    cases = build_matrix()
    same, diff, missing = 0, [], 0
    dll_probe = load_dll()
    del dll_probe
    for cid, scene, panel, bt, sd, sm in cases:
        d = os.path.join(FLAT, cid)
        ref = os.path.join(d, 'out.raw')
        if not os.path.exists(ref):
            missing += 1
            continue
        tmp = os.path.join(d, 'out_verify.raw')
        spec = {'in': os.path.join(SRC, scene + '.raw'), 'out': tmp,
                'panel': panel, 'blur_type': bt, 'skin_detect': sd,
                'smooth_mode': sm, 'reset': 1, 'warmup': 2}
        r = subprocess.run([sys.executable, os.path.abspath(__file__),
                            'run-one', json.dumps(spec, ensure_ascii=False)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(tmp):
            diff.append((cid, 'rerun failed'))
            continue
        a = open(ref, 'rb').read()
        b = open(tmp, 'rb').read()
        if a == b:
            same += 1
            os.remove(tmp)
        else:
            n = sum(1 for x, y in zip(a, b) if x != y)
            diff.append((cid, '%d bytes differ' % n))
    total = same + len(diff)
    print('[verify] %d/%d byte-identical (%s)' % (
        same, total, '100%%' if not diff and total else '%.1f%%' % (100.0 * same / max(1, total))))
    for cid, why in diff[:20]:
        print('   DIFF %-22s %s' % (cid, why))
    if missing:
        print('[verify] %d cases missing (run "all" first)' % missing)
    return 0 if not diff else 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == 'prep':
        cmd_prep()
    elif cmd == 'all':
        cmd_all(rest)
    elif cmd == 'report':
        cmd_report(rest)
    elif cmd == 'verify':
        return cmd_verify(rest)
    elif cmd == 'run-one':
        return cmd_run_one(rest)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
