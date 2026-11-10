# -*- coding: utf-8 -*-
"""用真实摄像头帧（0 档截图 ≈ 原始帧）做离线对拍。

为什么要这个脚本：
    真机截图法是**不同时刻抓拍**，本底噪声 12.9%（两个 0 档之差），
    而档位效应只有 5~9% —— 信噪比 <1，全部无法定量。
    参见 C18 与 2026-10-29 工作日志。

    0 档在 core 里是逐字节透传（磨皮=0 且其余全 0 时 memcpy），所以
    **0 档截图 ≈ 未处理的摄像头原始帧**。拿它当离线对拍输入：
    同一张图喂两个引擎，噪声为零，档位差异完全可归因。
    而且是 1920x1080 / 脸宽 ~530px，正好是真机尺度（不再是 face_src 的 111px）。

用法：
    python cam_frame_ab.py                 # 默认用自制0
    python cam_frame_ab.py <jpg路径>       # 指定素材
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
from pick_material import ascii_model_copy, LONG_EDGE, SCORE_THR  # noqa: E402

REGIONS = RG.REGIONS          # (name, nx0, ny0, nx1, ny1) 归一化到脸框
P_COUNT = RG.P_COUNT
P_BLUR = RG.P_BLUR
SDK_DLL = RG.SDK_DLL
ENGINE_DIR = RG.ENGINE_DIR
TMP = os.path.join(HERE, 'goldens', 'masks')

DEFAULT_SRC = os.path.join(
    os.path.join(os.path.expanduser("~"), ".workbuddy/clipboard-images"),
    'clipboard-2026-10-28T17-27-00-131Z-a93b903c.jpg')   # 自制0


def detect_face(img):
    """返回 (x, y, w, h) 原图坐标的人脸框"""
    import cv2
    det = cv2.FaceDetectorYN.create(ascii_model_copy(), '',
                                    (LONG_EDGE, LONG_EDGE), SCORE_THR, 0.3, 5000)
    oh, ow = img.shape[:2]
    s = LONG_EDGE / float(max(oh, ow))
    sm = cv2.resize(img, (int(ow * s), int(oh * s)), interpolation=cv2.INTER_AREA)
    det.setInputSize((sm.shape[1], sm.shape[0]))
    _, fs = det.detect(sm)
    if fs is None:
        raise RuntimeError('没检到脸')
    f = max(fs, key=lambda t: t[2] * t[3])
    return [f[i] / s for i in range(4)], float(f[14])


def to_rgba_raw(img_bgr, path):
    import cv2
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
    rgba.tofile(path)
    return rgba


def masks(w, h, box):
    x, y, bw, bh = box
    out = []
    for name, nx0, ny0, nx1, ny1 in REGIONS:
        m = np.zeros((h, w), bool)
        x0 = int(x + nx0 * bw); x1 = int(x + nx1 * bw)
        y0 = int(y + ny0 * bh); y1 = int(y + ny1 * bh)
        m[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
        out.append((name, m))
    return out


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


def bands_of(rgba):
    y = (0.299 * rgba[:, :, 0].astype(np.float64)
         + 0.587 * rgba[:, :, 1].astype(np.float64)
         + 0.114 * rgba[:, :, 2].astype(np.float64))
    b1 = boxmean(y, 1); b7 = boxmean(y, 7); b21 = boxmean(y, 21)
    return np.abs(y - b1), np.abs(b1 - b7), np.abs(b7 - b21)


def levels(rgba, rms):
    sb = bands_of(rgba)
    return {n: [float(sb[i][m].mean()) for i in range(3)] for n, m in rms}


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
    return np.fromfile(out_path, dtype=np.uint8).reshape((h, w, 4)), ms


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
    return np.fromfile(out_path, dtype=np.uint8).reshape((h, w, 4))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    import cv2
    img = cv2.imread(src, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit('读不出来: %s' % src)
    h, w = img.shape[:2]
    box, score = detect_face(img)
    print('素材: %s' % os.path.basename(src))
    print('尺寸: %dx%d   人脸框: x=%.0f y=%.0f w=%.0f h=%.0f (score %.2f)'
          % (w, h, box[0], box[1], box[2], box[3], score))
    rms = masks(w, h, box)
    src_raw = os.path.join(TMP, '_camframe_src.raw')
    base_img = to_rgba_raw(img, src_raw)
    base = levels(base_img, rms)

    levels_sweep = [0.0, 50.0, 100.0]
    print()
    print('%-6s %-6s | %-22s | %-22s' % ('档', '引擎', '细/中/阴 (四区域均值)', '与 SDK 差'))
    rows = {}
    for lvl in levels_sweep:
        co, ms = run_core(src_raw, w, h, lvl, os.path.join(TMP, '_camframe_core.raw'))
        sd = run_sdk(src_raw, w, h, lvl, os.path.join(TMP, '_camframe_sdk.raw'))
        rows[lvl] = (levels(co, rms), levels(sd, rms), ms)

    names = ['额头', '鼻翼', '脸颊', '眼区']
    def avg3(d):
        return [sum(d[n][i] / base[n][i] for n in names) / len(names) * 100.0
                for i in range(3)]

    for lvl in levels_sweep:
        cb, sbk, ms = rows[lvl]
        cv_, sv_ = avg3(cb), avg3(sbk)
        print('%-6g %-6s | %6.1f%% %6.1f%% %6.1f%%' % (lvl, 'SDK', *sv_))
        print('%-6g %-6s | %6.1f%% %6.1f%% %6.1f%% | %+6.1f %+6.1f %+6.1f  (%.1f ms)'
              % (lvl, 'core', *cv_,
                 cv_[0] - sv_[0], cv_[1] - sv_[1], cv_[2] - sv_[2], ms))
        print()

    print('100 档逐区域（core / SDK / 差）：')
    cb, sbk, _ = rows[100.0]
    print('%-6s %9s %9s %9s | %9s %9s %9s' % ('区域', 'core细', 'SDK细', 'd细', 'core阴', 'SDK阴', 'd阴'))
    for n, m in rms:
        cf = 100.0 * cb[n][0] / base[n][0]; sf = 100.0 * sbk[n][0] / base[n][0]
        cs = 100.0 * cb[n][2] / base[n][2]; ss = 100.0 * sbk[n][2] / base[n][2]
        print('%-6s %8.1f%% %8.1f%% %+8.1f | %8.1f%% %8.1f%% %+8.1f'
              % (n, cf, sf, cf - sf, cs, ss, cs - ss))


if __name__ == '__main__':
    main()
