# -*- coding: utf-8 -*-
"""6 张摄像头截图的真机对拍表（修正版）。

修正说明
--------
第一版把 da4285aa 与 3372ea47 的时间标反了（按 clipboard 的 Z 序号猜的），
导致档位序列不自洽。用户澄清「命名就是时间」，即文件名里的 HH-MM-SS 就是
截图时刻，与内容一一对应。修正后两组各自单调递减，指标可信度才成立。

分组（用户标注）
----------------
  00:37:25 / 00:37:34 / 00:37:42  = 第三方 SDK 的 90 / 50 / 0
  00:38:42 / 00:38:49 / 00:38:58  = 自制插件的   90 / 50 / 0

口径
----
只看脸框内 y∈[0.45,0.85] 的脸颊/嘴周条带（避开眼镜、头发、背景），
细频带用 mean|Y − box1|，并除以区域亮度做曝光归一化
—— 因为实测细能量与亮度相关（整脸区 r>0、脸颊区 r=−0.566），不归一化是伪指标。
"""
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageOps

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.join(os.path.expanduser("~"), ".workbuddy/clipboard-images")
MODEL = r"D:\插件\OBS美颜\06_离线验证\models\yunet.onnx"

# 时间 = 文件名里的时间戳；引擎与档位由用户标注
SHOTS = [
    ("00:37:25", "clipboard-2026-10-28T16-39-39-694Z-3372ea47.jpg", "SDK", 90),
    ("00:37:34", "clipboard-2026-10-28T16-39-39-694Z-3e65ce39.jpg", "SDK", 50),
    ("00:37:42", "clipboard-2026-10-28T16-39-39-693Z-9c8c54cb.jpg", "SDK", 0),
    ("00:38:42", "clipboard-2026-10-28T16-39-39-692Z-7944f760.jpg", "自制", 90),
    ("00:38:49", "clipboard-2026-10-28T16-39-39-691Z-96058f33.jpg", "自制", 50),
    ("00:38:58", "clipboard-2026-10-28T16-39-39-695Z-da4285aa.jpg", "自制", 0),
]


def ascii_model():
    d = os.path.join(tempfile.gettempdir(), "yunet_scan")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "yunet.onnx")
    if not os.path.exists(p):
        shutil.copy(MODEL, p)
    return p


def load_bgr(path):
    im = ImageOps.exif_transpose(Image.open(path))
    if im.mode != "RGB":
        im = im.convert("RGB")
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def box_mean(a, r):
    h, w = a.shape
    k = 2 * r + 1
    p = np.pad(a, ((0, 0), (r, r)), mode="edge")
    c = np.concatenate([np.zeros((h, 1)), np.cumsum(p, axis=1, dtype=np.float64)], axis=1)
    h1 = (c[:, k:] - c[:, :-k]) / k
    p2 = np.pad(h1, ((r, r), (0, 0)), mode="edge")
    c2 = np.concatenate([np.zeros((1, w)), np.cumsum(p2, axis=0, dtype=np.float64)], axis=0)
    return (c2[k:, :] - c2[:-k, :]) / k


def cheek_stats(img, det):
    oh, ow = img.shape[:2]
    s = 1280.0 / max(oh, ow)
    sm = cv2.resize(img, (int(ow * s), int(oh * s)), interpolation=cv2.INTER_AREA)
    det.setInputSize((sm.shape[1], sm.shape[0]))
    _, fs = det.detect(sm)
    if fs is None:
        return None
    f = max(fs, key=lambda t: t[2] * t[3])
    x, y, w, h = [f[i] / s for i in range(4)]
    x0 = max(0, int(x + 0.15 * w)); x1 = min(ow, int(x + 0.85 * w))
    y0 = max(0, int(y + 0.45 * h)); y1 = min(oh, int(y + 0.85 * h))
    crop = img[y0:y1, x0:x1].astype(np.float64)
    yv = 0.299 * crop[:, :, 2] + 0.587 * crop[:, :, 1] + 0.114 * crop[:, :, 0]
    b, g, r = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    return dict(
        fine=float(np.abs(yv - box_mean(yv, 1)).mean()),
        mid=float(np.abs(yv - box_mean(yv, 4)).mean()),
        luma=float(yv.mean()),
        rg=float(r.mean() - g.mean()),
        fw=float(w),
    )


def main():
    det = cv2.FaceDetectorYN.create(ascii_model(), "", (1280, 1280), 0.6, 0.3, 5000)
    res = {}
    print("%-8s %-6s %5s %8s %8s %10s %8s %7s"
          % ("时间", "引擎", "档位", "亮度", "R−G", "细/亮度", "脸宽px", "单调?"))
    by_eng = {}
    for t, name, eng, lvl in SHOTS:
        st = cheek_stats(load_bgr(os.path.join(HERE, name)), det)
        if st is None:
            print("%-8s %-6s %5d  未检出人脸" % (t, eng, lvl))
            continue
        st["nf"] = st["fine"] / st["luma"]
        by_eng.setdefault(eng, []).append((lvl, st, t))
        res[(eng, lvl)] = st

    for eng in ("SDK", "自制"):
        seq = sorted(by_eng[eng], key=lambda r: r[0])   # 0, 50, 90
        vals = [r[1]["nf"] for r in seq]
        mono = "是" if all(vals[i] >= vals[i + 1] - 1e-9 for i in range(len(vals) - 1)) else "否"
        for i, (lvl, st, t) in enumerate(seq):
            print("%-8s %-6s %5d %8.2f %8.2f %10.5f %8.0f %7s"
                  % (t, eng, lvl, st["luma"], st["rg"], st["nf"], st["fw"],
                     mono if i == 0 else ""))

    print("\n" + "=" * 66)
    print("相对各自 0 档的削减率（消除抓拍本底差异）：")
    print("%-6s %8s %10s %10s" % ("引擎", "档位", "残留%", "削减%"))
    red = {}
    for eng in ("SDK", "自制"):
        base = res[(eng, 0)]["nf"]
        for lvl in (0, 50, 90):
            v = res[(eng, lvl)]["nf"]
            red[(eng, lvl)] = 100.0 * v / base
            print("%-6s %8d %9.1f%% %9.1f%%" % (eng, lvl, red[(eng, lvl)],
                                                100.0 - red[(eng, lvl)]))

    print("\n" + "=" * 66)
    print("同档位直接对比：")
    print("%-6s %10s %10s %12s %12s" % ("档位", "SDK 残留", "自制残留", "自制/SDK", "削减差(pp)"))
    for lvl in (50, 90):
        rs, rc = red[("SDK", lvl)], red[("自制", lvl)]
        print("%-6d %9.1f%% %9.1f%% %11.2fx %11.1f"
              % (lvl, rs, rc, rc / rs, (100 - rc) - (100 - rs)))

    b0s, b0c = res[("SDK", 0)]["nf"], res[("自制", 0)]["nf"]
    print("\n" + "=" * 66)
    print("本底噪声：两个 0 档理论上应当相同（都不磨），实测差 %.1f%%"
          % (100 * (b0c / b0s - 1)))
    eff_s = 100 - red[("SDK", 90)]
    eff_c = 100 - red[("自制", 90)]
    print("档位效应：SDK 0→90 削 %.1f%%，自制 0→90 削 %.1f%%" % (eff_s, eff_c))
    print("→ 信噪比约 %.1f : 1（<2 时只能定性，不能定量）"
          % (eff_s / max(1e-9, abs(100 * (b0c / b0s - 1)))))


if __name__ == "__main__":
    main()
