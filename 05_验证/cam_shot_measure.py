# -*- coding: utf-8 -*-
"""量化 6 张摄像头截图：脸框位置/大小、细频带能量、肤色、亮度。"""
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
OUT = r"D:\插件\OBS美颜\06_离线验证\_cam_shot"

FILES = [
    ("96058f33", "clipboard-2026-10-28T16-39-39-691Z-96058f33.jpg"),
    ("7944f760", "clipboard-2026-10-28T16-39-39-692Z-7944f760.jpg"),
    ("9c8c54cb", "clipboard-2026-10-28T16-39-39-693Z-9c8c54cb.jpg"),
    ("3e65ce39", "clipboard-2026-10-28T16-39-39-694Z-3e65ce39.jpg"),
    ("3372ea47", "clipboard-2026-10-28T16-39-39-694Z-3372ea47.jpg"),
    ("da4285aa", "clipboard-2026-10-28T16-39-39-695Z-da4285aa.jpg"),
]


def ascii_model():
    d = os.path.join(tempfile.gettempdir(), "yunet_scan")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "yunet.onnx")
    if not os.path.exists(p):
        shutil.copy(MODEL, p)
    return p


def load_bgr(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    a = np.asarray(im)
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)


def box_mean(a, r):
    h, w = a.shape
    k = 2 * r + 1
    p = np.pad(a, ((0, 0), (r, r)), mode="edge")
    c = np.cumsum(p, axis=1, dtype=np.float64)
    c = np.concatenate([np.zeros((h, 1)), c], axis=1)
    h1 = (c[:, k:] - c[:, :-k]) / k
    p2 = np.pad(h1, ((r, r), (0, 0)), mode="edge")
    c2 = np.cumsum(p2, axis=0, dtype=np.float64)
    c2 = np.concatenate([np.zeros((1, w)), c2], axis=0)
    return (c2[k:, :] - c2[:-k, :]) / k


def face_stats(img, det):
    oh, ow = img.shape[:2]
    s = 1280.0 / max(oh, ow)
    sm = cv2.resize(img, (int(ow * s), int(oh * s)), interpolation=cv2.INTER_AREA)
    det.setInputSize((sm.shape[1], sm.shape[0]))
    _, fs = det.detect(sm)
    if fs is None:
        return None
    f = max(fs, key=lambda t: t[2] * t[3])
    x, y, w, h = [f[i] / s for i in range(4)]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(ow, int(x + w)), min(oh, int(y + h))
    crop = img[y0:y1, x0:x1]
    yv = (0.299 * crop[:, :, 2].astype(np.float64)
          + 0.587 * crop[:, :, 1] + 0.114 * crop[:, :, 0])
    fine = np.abs(yv - box_mean(yv, 1)).mean()          # 1px 尺度细节
    mid = np.abs(yv - box_mean(yv, 4)).mean()           # 4px 尺度
    bgr = crop.reshape(-1, 3).mean(axis=0)              # BGR
    return dict(box=(x0, y0, x1, y1), w=w, h=h,
                ratio=100.0 * w / ow, fine=fine, mid=mid,
                luma=float(yv.mean()), R=float(bgr[2]),
                G=float(bgr[1]), B=float(bgr[0]), score=float(f[14]))


def main():
    os.makedirs(OUT, exist_ok=True)
    det = cv2.FaceDetectorYN.create(ascii_model(), "", (1280, 1280), 0.6, 0.3, 5000)
    rows = []
    for tag, name in FILES:
        p = os.path.join(HERE, name)
        img = load_bgr(p)
        st = face_stats(img, det)
        if st is None:
            print("%-10s 未检出人脸" % tag)
            continue
        rows.append((tag, st))
        # 存脸区 PNG 供人工复核
        x0, y0, x1, y1 = st["box"]
        crop = img[y0:y1, x0:x1]
        cp = os.path.join(OUT, tag + "_face.png")
        Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).save(cp)

    print("%-10s %-18s %7s %7s %7s %7s %7s" %
          ("标签", "脸框 x0,y0", "脸宽%", "细能量", "中能量", "亮度", "R-G"))
    for tag, st in rows:
        print("%-10s %-18s %6.1f%% %7.3f %7.3f %7.1f %7.1f" %
              (tag, "(%d,%d)" % st["box"][:2], st["ratio"],
               st["fine"], st["mid"], st["luma"], st["R"] - st["G"]))

    if rows:
        fs = [r[1]["fine"] for r in rows]
        print("\n细频带能量排序（低 = 磨得多）：")
        order = sorted(rows, key=lambda r: r[1]["fine"])
        for i, (tag, st) in enumerate(order):
            print("  %d. %-10s fine=%.3f  mid=%.3f  luma=%.1f  R-G=%.1f" %
                  (i + 1, tag, st["fine"], st["mid"], st["luma"], st["R"] - st["G"]))
        print("\n脸框位置最大偏移：")
        xs = [r[1]["box"][0] for r in rows]
        ys = [r[1]["box"][1] for r in rows]
        ws = [r[1]["w"] for r in rows]
        print("  dx=%d  dy=%d  dw=%.0f px  → %s" %
              (max(xs) - min(xs), max(ys) - min(ys), max(ws) - min(ws),
               "基本同一姿态" if (max(xs) - min(xs) < 40 and max(ys) - min(ys) < 40)
               else "姿态/构图不同，不能像素级比较"))
        print("\n脸区裁片已存到：%s" % OUT)


if __name__ == "__main__":
    main()
