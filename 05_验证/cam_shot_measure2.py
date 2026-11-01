# -*- coding: utf-8 -*-
"""第二次测量：只取脸颊区（避开眼镜/头发/背景），并做曝光归一化。

第一版用「整张脸框 + 细频带绝对能量」，事后发现细能量与画面亮度高度正相关
（相关系数接近 1），即指标被摄像头自动曝光驱动，而不是被磨皮驱动。
这一版改两处：
  1) 只取脸框内 y∈[0.45,0.85] 的脸颊/嘴周条带，避开眼镜、头发、背景；
  2) 用 fine/luma 与 mid/luma 归一化，消掉曝光差。
"""
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageOps

sys.stdout.reconfigure(encoding="utf-8")

HERE = r"C:\Users\<user>\.workbuddy\clipboard-images"
MODEL = r"D:\插件\OBS美颜\06_离线验证\models\yunet.onnx"

# (时间, 文件名)
SHOTS = [
    ("00:37:25", "clipboard-2026-10-28T16-39-39-695Z-da4285aa.jpg"),
    ("00:37:34", "clipboard-2026-10-28T16-39-39-694Z-3e65ce39.jpg"),
    ("00:37:42", "clipboard-2026-10-28T16-39-39-693Z-9c8c54cb.jpg"),
    ("00:38:42", "clipboard-2026-10-28T16-39-39-692Z-7944f760.jpg"),
    ("00:38:49", "clipboard-2026-10-28T16-39-39-691Z-96058f33.jpg"),
    ("00:38:58", "clipboard-2026-10-28T16-39-39-694Z-3372ea47.jpg"),
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
    # 脸颊/嘴周条带：横向收窄避开脸框边缘的背景，纵向 0.45~0.85 避开眼镜与头发
    x0 = max(0, int(x + 0.15 * w)); x1 = min(ow, int(x + 0.85 * w))
    y0 = max(0, int(y + 0.45 * h)); y1 = min(oh, int(y + 0.85 * h))
    crop = img[y0:y1, x0:x1]
    yv = (0.299 * crop[:, :, 2].astype(np.float64)
          + 0.587 * crop[:, :, 1] + 0.114 * crop[:, :, 0])
    fine = float(np.abs(yv - box_mean(yv, 1)).mean())
    mid = float(np.abs(yv - box_mean(yv, 4)).mean())
    luma = float(yv.mean())
    px = float(w)  # 脸宽像素，用于看构图变化
    return dict(fine=fine, mid=mid, luma=luma, fw=px,
                nf=fine / luma, nm=mid / luma)


def main():
    det = cv2.FaceDetectorYN.create(ascii_model(), "", (1280, 1280), 0.6, 0.3, 5000)
    rows = []
    for t, name in SHOTS:
        st = cheek_stats(load_bgr(os.path.join(HERE, name)), det)
        if st:
            rows.append((t, st))

    print("%-9s %8s %8s %8s %9s %9s %8s"
          % ("时间", "亮度", "细能量", "中能量", "细/亮度", "中/亮度", "脸宽px"))
    for t, st in rows:
        print("%-9s %8.2f %8.3f %8.3f %9.5f %9.5f %8.0f"
              % (t, st["luma"], st["fine"], st["mid"], st["nf"], st["nm"], st["fw"]))

    lum = np.array([r[1]["luma"] for r in rows])
    fin = np.array([r[1]["fine"] for r in rows])
    mid = np.array([r[1]["mid"] for r in rows])
    fw = np.array([r[1]["fw"] for r in rows])
    print("\n相关性（Pearson）：")
    print("  细能量 vs 亮度  r = %+.3f" % np.corrcoef(fin, lum)[0, 1])
    print("  中能量 vs 亮度  r = %+.3f" % np.corrcoef(mid, lum)[0, 1])
    print("  细能量 vs 脸宽  r = %+.3f" % np.corrcoef(fin, fw)[0, 1])

    print("\n归一化细能量排序（低 = 磨得多）：")
    for i, (t, st) in enumerate(sorted(rows, key=lambda r: r[1]["nf"])):
        print("  %d. %s  nf=%.5f  luma=%.1f  脸宽=%.0f"
              % (i + 1, t, st["nf"], st["luma"], st["fw"]))

    nfs = np.array([r[1]["nf"] for r in rows])
    print("\n归一化后跨度：%.5f ~ %.5f（%.0f%%）"
          % (nfs.min(), nfs.max(), 100 * (nfs.max() / nfs.min() - 1)))


if __name__ == "__main__":
    main()
