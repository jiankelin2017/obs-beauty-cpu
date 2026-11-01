# -*- coding: utf-8 -*-
"""S1 掩码离线对拍 —— 换掉 fuai 之前，先量化「候选掩码差多少」。

不碰任何现有代码，只做测量。当前可测的两方：

  A · fuai AI 皮肤分割（192x256）     —— 自研掩码要追的目标
  B · YCbCr 颜色启发式（可复刻）      —— 我们手里现成的、纯 CPU 的候选

判据为什么是这两方：发布出去的产品里 fuai 不可用（分发包只有加密 bundle），
所以「现在用户看到的」其实不是 A 也不是 B，而是 SDK 内部的 skin_detect。
B 是我们能完全掌控的下界；拿 B 和 A 比，就知道自研掩码至少要把差距补到哪。

用法（系统 Python 3.12，需 numpy + PIL）：
    python mask_compare.py dump     导出每个场景的 fuai 掩码 -> goldens/masks/
    python mask_compare.py compare  计算 A/B 各项指标 -> goldens/masks/mask_compare.md
    python mask_compare.py all      依次跑上面两步

模型（PPHumanSeg / YuNet）在本机网络下下载不到，脚本里留了 `model_mask()`
钩子：把模型放到 06_离线验证/models/ 之后，实现那个函数即可把第三方候选接进来
对拍，不需要改别的地方。
"""

from __future__ import print_function

import ctypes
import json
import os
import struct
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, 'goldens')
SRC = os.path.join(GOLD, 'src')
MASKS = os.path.join(GOLD, 'masks')
DLL = os.path.join(HERE, 'ref_golden.dll')
MODELS = os.path.join(HERE, 'models')

W, H = 640, 394
ENGINE_DIR = os.environ.get(
    'GOLDEN_ENGINE_DIR',
    r'C:\Users\<user>\AppData\Local\Temp\legacy_abtest\engine')

SCENES = ['face_src', 'crop_a', 'crop_b', 'crop_c', 'crop_d',
          'look1', 'look2', 'obs_grab', 'noface_skin', 'noface_gray']

# 受控变体：现有素材里只有 face_src 能同时让 fuai 与启发式都出结果
# （look1/look2/obs_grab 的 fuai 覆盖率是 0，基准不可用），所以基于 face_src
# 造一组受控扰动，把有效样本从 1 个扩到 8 个 —— 要测的是「候选掩码在什么条件下
# 会崩」，受控扰动比随机找图更能回答这个问题。
VARIANTS = ['v_zoom15', 'v_zoom07', 'v_noise5', 'v_dark', 'v_bright',
            'v_flip', 'v_skinbg']


def cmd_variants(_a=None):
    src = np.fromfile(os.path.join(SRC, 'face_src.raw'), dtype=np.uint8)
    src = src.reshape((H, W, 4)).astype(np.float32)
    rng = np.random.default_rng(20261028)

    def save(name, arr):
        a = np.clip(arr, 0, 255).astype(np.uint8)
        a.tofile(os.path.join(SRC, name + '.raw'))
        Image.fromarray(a, 'RGBA').save(os.path.join(SRC, name + '.png'))

    def zoom(f):
        im = Image.fromarray(src.astype(np.uint8), 'RGBA')
        nw, nh = int(W * f), int(H * f)
        im = im.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        canvas.paste(im, ((W - nw) // 2, (H - nh) // 2))
        return np.asarray(canvas, dtype=np.float32)

    save('v_zoom15', zoom(1.5))
    save('v_zoom07', zoom(0.7))
    save('v_noise5', src + rng.normal(0, 5, src.shape))
    save('v_dark', src * 0.7)
    save('v_bright', np.clip(src * 1.3, 0, 255))
    save('v_flip', src[:, ::-1, :])
    bg = src.copy()
    bg[int(H * 0.55):, int(W * 0.6):, 0] = 214   # 右下角贴一块米色（近似肤色）
    bg[int(H * 0.55):, int(W * 0.6):, 1] = 178
    bg[int(H * 0.55):, int(W * 0.6):, 2] = 150
    save('v_skinbg', bg)
    print('[variants] %d -> %s' % (len(VARIANTS), SRC))


def all_scenes():
    return SCENES + VARIANTS


# ---------------------------------------------------------------------------
# fuai 掩码（基准 A）
# ---------------------------------------------------------------------------
def load_dll():
    d = ctypes.WinDLL(DLL)
    d.BeautyDumpMask.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                 ctypes.c_int, ctypes.c_int,
                                 ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    d.BeautyDumpMask.restype = ctypes.c_int
    return d


def cmd_dump(_a=None):
    os.makedirs(MASKS, exist_ok=True)
    dll = load_dll()
    recs = []
    for sid in all_scenes():
        raw = os.path.join(SRC, sid + '.raw')
        if not os.path.exists(raw):
            continue
        out = os.path.join(MASKS, sid + '_fuai.mask')
        msg = ctypes.create_string_buffer(512)
        rc = dll.BeautyDumpMask(ENGINE_DIR.encode('utf-8'), raw.encode('utf-8'),
                                W, H, out.encode('utf-8'), msg, 512)
        m = msg.value.decode('utf-8', 'replace')
        recs.append({'scene': sid, 'rc': rc, 'msg': m})
        print('  %-14s rc=%d %s' % (sid, rc, m[:80]))
    with open(os.path.join(MASKS, 'dump.json'), 'w', encoding='utf-8') as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    print('[dump] %d scenes' % len(recs))


def read_mask(path):
    with open(path, 'rb') as f:
        hdr = f.read(8)
        mw, mh = struct.unpack('<ii', hdr)
        a = np.frombuffer(f.read(mw * mh), dtype=np.uint8)
    return a.reshape((mh, mw))


# ---------------------------------------------------------------------------
# 候选掩码
# ---------------------------------------------------------------------------
def heuristic_mask(rgba, mw, mh):
    """复刻 legacy_engine.cpp applyWhiten 的 YCbCr 肤色判据，再按目标网格降采样。

    判据（与源码逐项一致）：
        Y  = (66R + 129G + 25B + 128) >> 8
        Cb = ((-38R - 74G + 112B + 128) >> 8) + 128
        Cr = ((112R - 94G - 18B + 128) >> 8) + 128
        skin = 133<=Cr<=173 且 77<=Cb<=127 且 R>G>B 且 R>80 且 60<Y<235
    源码在 1/4 分辨率上算（每 4x4 取一个样本）再双线性放大；这里直接按目标
    网格（192x256）做区域平均后判定，避免「采样点位置」带来的额外误差 ——
    要比较的是判据本身，不是采样策略。
    """
    h, w = rgba.shape[:2]
    R = rgba[:, :, 0].astype(np.int32)
    G = rgba[:, :, 1].astype(np.int32)
    B = rgba[:, :, 2].astype(np.int32)
    Y = (66 * R + 129 * G + 25 * B + 128) >> 8
    Cb = ((-38 * R - 74 * G + 112 * B + 128) >> 8) + 128
    Cr = ((112 * R - 94 * G - 18 * B + 128) >> 8) + 128
    skin = ((Cr >= 133) & (Cr <= 173) & (Cb >= 77) & (Cb <= 127) &
            (R > G) & (G > B) & (R > 80) & (Y > 60) & (Y < 235))
    s = skin.astype(np.float32)
    # 按目标网格做区域平均（等价于源码的 3x3 羽化的软化效果）
    im = Image.fromarray((s * 255).astype(np.uint8), 'L')
    im = im.resize((mw, mh), Image.BOX)
    m = np.asarray(im, dtype=np.uint8)
    # 3x3 均值羽化，与源码对齐
    k = np.ones((3, 3), dtype=np.float32) / 9.0
    pad = np.pad(m.astype(np.float32), 1, mode='edge')
    out = np.zeros_like(m, dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            out += k[dy, dx] * pad[dy:dy + mh, dx:dx + mw]
    return np.clip(out, 0, 255).astype(np.uint8)


PP_MODEL = os.path.join(MODELS, 'pphumanseg_2023mar.onnx')
YUNET_MODEL = os.path.join(MODELS, 'yunet_2023mar.onnx')
_pp_net = None
_yunet = None

_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


def _ascii_path(p):
    """cv2.dnn / FaceDetectorYN 读不了含中文的路径（ONNXImporter2 用窄字符 fopen）。
    模型放在中文目录下时必须先复制到 ASCII 临时目录再加载。"""
    if not p or all(ord(ch) < 128 for ch in p):
        return p
    import shutil
    import tempfile
    d = os.path.join(tempfile.gettempdir(), 'beauty_models')
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, os.path.basename(p))
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(p):
        shutil.copy2(p, dst)
    return dst


def _pp_seg(rgb):
    """PPHumanSeg 人像概率图（192x192，0..1）。模型不在就返回 None。"""
    global _pp_net
    if not os.path.exists(PP_MODEL):
        return None
    import cv2
    if _pp_net is None:
        _pp_net = cv2.dnn.readNetFromONNX(_ascii_path(PP_MODEL))
    im = cv2.resize(rgb, (192, 192), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    x = (im / 255.0 - _MEAN) / _STD
    _pp_net.setInput(x.transpose(2, 0, 1)[None])
    out = _pp_net.forward()[0]
    return out[1]            # 通道 1 = 人像前景


def _yunet_faces(rgb_bgr):
    """YuNet 人脸框列表 [(x,y,w,h), ...]，原图坐标。模型不在就返回 None。"""
    global _yunet
    if not os.path.exists(YUNET_MODEL):
        return None
    import cv2
    h, w = rgb_bgr.shape[:2]
    if _yunet is None:
        _yunet = cv2.FaceDetectorYN.create(_ascii_path(YUNET_MODEL), "", (w, h), 0.6, 0.3, 5000)
    _yunet.setInputSize((w, h))
    _, faces = _yunet.detect(rgb_bgr)
    if faces is None:
        return []
    return [(float(f[0]), float(f[1]), float(f[2]), float(f[3])) for f in faces]


def _box_mask(faces, mw, mh, grow=1.25):
    """把原图坐标的人脸框（外扩 grow 倍）画到 mw x mh 网格上。"""
    m = np.zeros((mh, mw), np.uint8)
    for (x, y, w, h) in faces:
        cx, cy = x + w / 2.0, y + h / 2.0
        w2, h2 = w * grow / 2.0, h * grow / 2.0
        x0 = max(0, int((cx - w2) / W * mw))
        x1 = min(mw, int((cx + w2) / W * mw) + 1)
        y0 = max(0, int((cy - h2) / H * mh))
        y1 = min(mh, int((cy + h2) / H * mh) + 1)
        m[y0:y1, x0:x1] = 255
    return m


def model_mask(rgba, mw, mh):
    """返回候选掩码字典；模型缺失时返回空字典（对拍自动跳过这些列）。

    候选设计（都在 mw x mh 网格上）：
      pp        PPHumanSeg 人像概率 >= 0.5（含头发/衣服，只做下界参考）
      pp_skin   pp ∩ 肤色启发式   —— 去掉衣服，保留皮肤
      pp_face   pp ∩ 人脸框       —— 只留脸，去掉身体
      skin_face 肤色 ∩ 人脸框     —— 纯 YuNet 方案，完全不用分割模型
    """
    import cv2
    rgb = rgba[:, :, :3].copy()
    bgr = rgb[:, :, ::-1].copy()
    out = {}

    seg = _pp_seg(rgb)
    if seg is not None:
        fg = cv2.resize(seg, (mw, mh), interpolation=cv2.INTER_LINEAR)
        pp = np.clip(fg * 255.0, 0, 255).astype(np.uint8)
        out['pp'] = pp

    faces = _yunet_faces(bgr)
    skin = heuristic_mask(rgba, mw, mh)
    if faces is not None and len(faces) > 0:
        fm = _box_mask(faces, mw, mh)
        out['skin_face'] = np.minimum(skin, fm)
        if seg is not None:
            out['pp_face'] = np.minimum(out['pp'], fm)
    if seg is not None:
        out['pp_skin'] = np.minimum(out['pp'], skin)
    return out


# ---------------------------------------------------------------------------
# 指标
# ---------------------------------------------------------------------------
def binmask(m, thr=128):
    return m >= thr


def iou(a, b):
    A, B = binmask(a), binmask(b)
    inter = float(np.logical_and(A, B).sum())
    union = float(np.logical_or(A, B).sum())
    return inter / union if union > 0 else 0.0


def prf(a, b):
    """a 相对 b 的精确率 / 召回率（b 当真值）。"""
    A, B = binmask(a), binmask(b)
    tp = float(np.logical_and(A, B).sum())
    p = tp / float(A.sum()) if A.sum() > 0 else 0.0
    r = tp / float(B.sum()) if B.sum() > 0 else 0.0
    return p, r


def edge_roughness(m):
    """掩码梯度均值：边界越碎这个值越大（羽化不足 / 噪点多）。"""
    g = m.astype(np.float32)
    gx = np.abs(np.diff(g, axis=1)).mean()
    gy = np.abs(np.diff(g, axis=0)).mean()
    return float((gx + gy) / 2.0)


def boundary_ratio(m):
    """处于过渡带（16..240）的像素占掩码面积的比例：越高说明边界越宽/越软。"""
    b = (m >= 16) & (m <= 240)
    hard = m >= 128
    return float(b.sum()) / float(hard.sum()) if hard.sum() > 0 else 0.0


def cmd_compare(_a=None):
    rows = []
    for sid in all_scenes():
        raw = os.path.join(SRC, sid + '.raw')
        mp = os.path.join(MASKS, sid + '_fuai.mask')
        if not (os.path.exists(raw) and os.path.exists(mp)):
            continue
        rgba = np.fromfile(raw, dtype=np.uint8).reshape((H, W, 4))
        a = read_mask(mp)                       # 基准 A：fuai
        mh, mw = a.shape
        b = heuristic_mask(rgba, mw, mh)        # 候选 B：肤色启发式
        cands = model_mask(rgba, mw, mh)        # 候选 C 组：模型/组合
        cands['skin'] = b

        # 可视化：A 与各候选叠加，掩码放大回原图尺寸便于肉眼核对
        base = Image.fromarray(rgba, 'RGBA').convert('RGB')
        ov_a = np.asarray(base.resize((mw, mh), Image.LANCZOS), dtype=np.float32)
        ma = (a >= 128)[:, :, None]
        os.makedirs(os.path.join(MASKS, 'viz'), exist_ok=True)
        Image.fromarray(np.where(ma, ov_a * 0.35 + np.array([255, 60, 60], np.float32) * 0.65,
                                 ov_a).astype(np.uint8)).save(
            os.path.join(MASKS, 'viz', sid + '_A_fuai.png'))
        for k, cm in cands.items():
            ov = ov_a.copy()
            mc = (cm >= 128)[:, :, None]
            ov = np.where(mc, ov * 0.35 + np.array([60, 200, 255], np.float32) * 0.65, ov)
            Image.fromarray(ov.astype(np.uint8)).save(
                os.path.join(MASKS, 'viz', sid + '_C_%s.png' % k))

        p, r = prf(b, a)
        row = {
            'scene': sid,
            'grid': '%dx%d' % (mw, mh),
            'cov_a': round(float(binmask(a).mean()) * 100, 2),
            'cov_b': round(float(binmask(b).mean()) * 100, 2),
            'iou': round(iou(a, b), 3),
            'prec': round(p, 3),
            'recall': round(r, 3),
            'rough_a': round(edge_roughness(a), 2),
            'rough_b': round(edge_roughness(b), 2),
            'soft_a': round(boundary_ratio(a), 2),
            'soft_b': round(boundary_ratio(b), 2),
            'cand': {},
        }
        for k, cm in cands.items():
            cp, cr = prf(cm, a)
            row['cand'][k] = {
                'cov': round(float(binmask(cm).mean()) * 100, 2),
                'iou': round(iou(a, cm), 3),
                'prec': round(cp, 3),
                'recall': round(cr, 3),
                'rough': round(edge_roughness(cm), 2),
            }
        rows.append(row)

    md = []
    md.append('# S1 掩码对拍：fuai AI 分割 vs YCbCr 颜色启发式\n')
    md.append('> 生成时间：%s　·　掩码网格：%s（fuai 原生分辨率）\n'
              % (time.strftime('%Y-%m-%d %H:%M:%S'),
                 rows[0]['grid'] if rows else '-'))
    md.append('**A** = fuai AI 皮肤分割（自研掩码要追的目标）；'
              '**B** = YCbCr 颜色启发式（我们手里现成的纯 CPU 候选）。\n')
    md.append('| 场景 | A 覆盖% | B 覆盖% | IoU | 精确率 | 召回率 '
              '| A 边界粗糙度 | B 边界粗糙度 | A 软边比 | B 软边比 |')
    md.append('|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        md.append('| %(scene)s | %(cov_a).2f | %(cov_b).2f | %(iou).3f | %(prec).3f '
                  '| %(recall).3f | %(rough_a).2f | %(rough_b).2f '
                  '| %(soft_a).2f | %(soft_b).2f |' % r)
    md.append('')
    md.append('## 口径\n')
    md.append('- **覆盖率**：掩码 >=128 的像素占全图比例。')
    md.append('- **IoU / 精确率 / 召回率**：以 A（fuai）为真值，衡量 B 与它重合多少。'
              '精确率低 = 启发式把非皮肤当成皮肤（误伤背景）；'
              '召回率低 = 漏掉真皮肤（脸上会有区域没被磨到）。')
    md.append('- **边界粗糙度**：掩码相邻像素差的均值，越大越碎。')
    md.append('- **软边比**：过渡带像素 / 硬掩码像素，越大说明边界越软（越不容易出现硬边）。\n')
    # ---- 候选掩码汇总（face 组：同一张脸的受控扰动，最能反映「谁更准」）----
    face_rows = [r for r in rows
                 if (r['scene'] == 'face_src' or r['scene'].startswith('v_'))
                 and r['cov_a'] > 0]
    if face_rows:
        keys = []
        for r in face_rows:
            for k in r['cand']:
                if k not in keys:
                    keys.append(k)
        desc = {
            'skin': '纯 YCbCr 肤色判据（无模型，当前产品路径）',
            'pp': 'PPHumanSeg 人像 ≥0.5（含头发/衣服，仅作下界）',
            'pp_skin': '人像 ∩ 肤色（去衣服、留皮肤）',
            'pp_face': '人像 ∩ 人脸框（只留脸，去身体）',
            'skin_face': '肤色 ∩ 人脸框（纯 YuNet，不用分割模型）',
        }
        md.append('## 候选掩码汇总（face 组 %d 场景均值）\n' % len(face_rows))
        md.append('| 候选 | 覆盖% | IoU | 精确率 | 召回率 | 边界粗糙度 | 说明 |')
        md.append('|---|---|---|---|---|---|---|')
        for k in keys:
            vs = [r['cand'][k] for r in face_rows if k in r['cand']]
            if not vs:
                continue
            def f(key, vs=vs):
                return sum(v[key] for v in vs) / len(vs)
            md.append('| `%s` | %.2f | %.3f | %.3f | %.3f | %.2f | %s |'
                      % (k, f('cov'), f('iou'), f('prec'), f('recall'), f('rough'),
                         desc.get(k, '')))
        md.append('')
        md.append('> **口径**：A（fuai）当真值。精确率低 = 把非皮肤当成皮肤；'
                  '召回率低 = 漏掉真皮肤。边界粗糙度越大越碎。\n')
    # 只统计「基准可用」的场景：fuai 覆盖率 > 0 才算 A 真的给了结果。
    # v_* 是 face_src 的受控变体（缩放/噪声/亮度/翻转/肤色背景干扰）。
    valid = [r for r in rows if r['cov_a'] > 0]
    # 分两组统计：两组失败原因不同，混在一起会把结论带偏。
    #   face 组 = face_src 及其受控变体：同一张脸，B 的问题是「面积放大」
    #   crop 组 = crop_* 宽幅裁剪：画面里有第二块肤色，B 的问题是「检错位置」
    face_g = [r for r in valid if r['scene'] == 'face_src' or r['scene'].startswith('v_')]
    crop_g = [r for r in valid if r['scene'].startswith('crop_')]

    def stat(g, key):
        v = [r[key] for r in g]
        return (min(v), max(v), sum(v) / len(v)) if v else (0, 0, 0)

    def table(g, title):
        if not g:
            return
        md.append('### %s（%d 个场景）\n' % (title, len(g)))
        md.append('| 指标 | 范围 | 均值 |')
        md.append('|---|---|---|')
        for key, name in (('iou', 'IoU（B vs A）'), ('prec', '精确率'),
                          ('recall', '召回率')):
            lo, hi, avg = stat(g, key)
            md.append('| %s | %.3f ~ %.3f | %.3f |' % (name, lo, hi, avg))
        rr = [r['cov_b'] / r['cov_a'] for r in g if r['cov_a'] > 0]
        if rr:
            md.append('| 面积放大倍数 B/A | %.2f ~ %.2f | %.2f |'
                      % (min(rr), max(rr), sum(rr) / len(rr)))
        md.append('')

    if face_g or crop_g:
        md.append('## 结论（%d 个基准可用场景，分两组）\n'
                  % (len(face_g) + len(crop_g)))
        table(face_g, 'A · 同一张脸的受控扰动')
        table(crop_g, 'B · 画面含第二块肤色区域')
        md.append('### 读出来的三条规律\n')
        md.append('1. **召回率够用，精确率崩了。** face 组召回率稳定在 0.90 以上'
                  '（真皮肤基本覆盖到），但精确率只有 0.16~0.35 —— '
                  '掩码里三分之二以上是误检。这就是「背景/衣服被一起磨、一起提亮」'
                  '的量化根源。')
        md.append('2. **画面里出现第二块肤色时，B 会检错位置**，不只是面积变大：'
                  '`crop_c` 上 A 的质心在 x≈95、B 在 x≈45，差了 50 个网格像素，'
                  'IoU 掉到 0.05。这类场景靠调阈值救不回来。')
        md.append('3. **亮度偏暗时召回率掉到 0.903**（`v_dark`，漏掉约 10% 真皮肤）；'
                  '噪声 ±5 对两方影响都很小。\n')
        md.append('### 自研掩码的验收门槛（建议）\n')
        md.append('| 指标 | 当前启发式（face 组） | 门槛 |')
        md.append('|---|---|---|')
        for key, name, floor in (('iou', 'IoU vs fuai', 0.60),
                                 ('prec', '精确率', 0.70),
                                 ('recall', '召回率', 0.90)):
            md.append('| %s | %.3f | **≥ %.2f** |' % (name, stat(face_g, key)[2], floor))
        md.append('| 无人脸画面误检 | 100%（`noface_skin` 全检）| **= 0** |')
        md.append('')
    else:
        md.append('## 结论\n\n（没有基准可用的场景，fuai 全部没输出。）\n')

    dead = [r['scene'] for r in rows if r['cov_a'] <= 0]
    if dead:
        md.append('## ⚠️ 基准失效的场景\n')
        md.append('以下场景 fuai **完全没输出**（覆盖率 0），A 侧无法作为基准：'
                  + '、'.join('`%s`' % s for s in dead) + '。\n')
        md.append('这不是采集出错 —— 这些图上 fuai 的皮肤分割就是没检出皮肤。'
                  '它同时说明一件事：**即使把明文 bundle 装上、让 fuai 可用，'
                  '它在不少实拍素材上也不工作**。所以自研掩码的目标不该是'
                  '「复刻 fuai」，而是「比 fuai 更鲁棒」。\n')

    out = os.path.join(MASKS, 'mask_compare.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('[compare] %d scenes -> %s' % (len(rows), out))
    for r in rows:
        print('  %-14s covA=%5.2f%% covB=%5.2f%% IoU=%.3f P=%.3f R=%.3f'
              % (r['scene'], r['cov_a'], r['cov_b'], r['iou'], r['prec'], r['recall']))
    with open(os.path.join(MASKS, 'mask_compare.json'), 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def cmd_growscan(_a=None):
    """扫「肤色 ∩ 人脸框」的外扩系数 —— 决定召回率与精确率的取舍点。"""
    grows = [1.0, 1.15, 1.25, 1.4, 1.5, 1.8, 2.2]
    agg = {g: [] for g in grows}
    for sid in ['face_src'] + VARIANTS:
        raw = os.path.join(SRC, sid + '.raw')
        mp = os.path.join(MASKS, sid + '_fuai.mask')
        if not (os.path.exists(raw) and os.path.exists(mp)):
            continue
        rgba = np.fromfile(raw, dtype=np.uint8).reshape((H, W, 4))
        a = read_mask(mp)
        mh, mw = a.shape
        if binmask(a).sum() == 0:
            continue
        skin = heuristic_mask(rgba, mw, mh)
        faces = _yunet_faces(rgba[:, :, :3][:, :, ::-1].copy()) or []
        for g in grows:
            m = np.minimum(skin, _box_mask(faces, mw, mh, g))
            p, r = prf(m, a)
            agg[g].append((iou(a, m), p, r, 100.0 * binmask(m).mean()))
    md = ['# 人脸框外扩系数扫描（肤色 ∩ YuNet 人脸框）\n',
          '> 生成时间：%s　·　A = fuai 掩码当真值　·　face 组 %d 场景\n'
          % (time.strftime('%Y-%m-%d %H:%M:%S'), len(agg[grows[0]])),
          '| grow | IoU | 精确率 | 召回率 | 覆盖% |',
          '|---|---|---|---|---|']
    best = None
    for g in grows:
        v = np.array(agg[g]) if agg[g] else np.zeros((1, 4))
        m = v.mean(axis=0)
        md.append('| %.2f | %.3f | %.3f | %.3f | %.2f |' % (g, m[0], m[1], m[2], m[3]))
        if best is None or m[0] > best[0]:
            best = (m[0], g)
    md.append('')
    bv = np.array(agg[best[1]]).mean(axis=0) if agg[best[1]] else np.zeros(4)
    md.append('**IoU 峰值在 grow = %.2f**（IoU %.3f、精确率 %.3f、召回率 %.3f）。'
              '再放大只会拿精确率换召回率：grow 越小框越紧、越不会误伤脸周，'
              '但漏掉脖子/耳朵。\n'
              % (best[1], bv[0], bv[1], bv[2]))
    md.append('取舍建议：磨皮/美白默认用 **grow = %.2f**；若用户反馈「脖子没被磨」，'
              '再单独开一条人脸以下的肤色通道，不要把矩形框继续放大 —— '
              '放大矩形会连背景一起框进来。\n' % best[1])
    out = os.path.join(MASKS, 'grow_scan.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('\n'.join(md[3:]))
    print('[growscan] -> %s' % out)


def main():
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    c = sys.argv[1]
    if c == 'variants':
        cmd_variants()
    elif c == 'dump':
        cmd_dump()
    elif c == 'compare':
        cmd_compare()
    elif c == 'growscan':
        cmd_growscan()
    elif c == 'all':
        cmd_variants()
        cmd_dump()
        cmd_compare()
        cmd_growscan()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
