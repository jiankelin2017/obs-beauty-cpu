# -*- coding: utf-8 -*-
"""横向对比 4 张 OBS 截图：自制(LegacySDK Beauty) vs OBS美颜摄像头 2.4.2。

做法：
  1. 自动定位 OBS 预览窗口的红色选框（#ff0000 边框），向内收缩裁出画面区；
  2. 在画面区内再分两个 ROI：
     - face: 人脸中部（画面中央偏左区域，按比例固定）
     - bg  : 背景书架/墙面（画面右上，远离人脸）
  3. 指标：
     - lap_var  拉普拉斯方差（细节/清晰度）
     - hf       高通能量占比（高频细节比例）
     - lum      平均亮度
     - grad     平均梯度（Sobel）
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

RED = (255, 0, 0)


def find_preview(im):
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    m = (a[:, :, 0] > 140) & (a[:, :, 1] < 110) & (a[:, :, 2] < 110) & (a[:, :, 0] - a[:, :, 1] > 60)
    cs = m.sum(axis=0)
    rs = m.sum(axis=1)
    H, W = m.shape
    cols = np.where(cs > H * 0.25)[0]
    rows = np.where(rs > W * 0.25)[0]
    if len(cols) < 2 or len(rows) < 2:
        return None
    x0 = 0 if cols.min() > W * 0.4 else cols.min()
    x1 = W if cols.max() < W * 0.5 else cols.max()
    y0 = 0 if rows.min() > H * 0.4 else rows.min()
    y1 = H if rows.max() < H * 0.5 else rows.max()
    if x1 - x0 < 100 or y1 - y0 < 100:
        return None
    # 红色边框本身可能只有 2px，向内收缩
    return (x0 + 4, y0 + 4, x1 - 4, y1 - 4)


def roi(gray, fx0, fy0, fx1, fy1):
    h, w = gray.shape
    return gray[int(h * fy0):int(h * fy1), int(w * fx0):int(w * fx1)]


def lap_var(g):
    p_ = np.pad(g, 1, mode="reflect")
    lap = (-4 * p_[1:-1, 1:-1] + p_[:-2, 1:-1] + p_[2:, 1:-1]
           + p_[1:-1, :-2] + p_[1:-1, 2:])
    return float(lap.var())


def hf_ratio(g):
    f = np.fft.rfft2(g.astype(np.float64) - g.mean())
    p = np.abs(f) ** 2
    h, w = g.shape
    cy, cx = h / 2.0, w / 2.0
    yy = np.fft.fftfreq(h)[:, None]
    xx = np.fft.rfftfreq(w)[None, :]
    r = np.sqrt(yy ** 2 + (xx * (h / w)) ** 2)
    total = p.sum()
    high = p[r > 0.25].sum()
    return float(high / total) if total > 0 else 0.0


def sob_mean(g):
    gx = np.abs(np.diff(g.astype(np.float64), axis=1)).mean()
    gy = np.abs(np.diff(g.astype(np.float64), axis=0)).mean()
    return float((gx + gy) / 2)


def main(paths):
    rows = []
    for p in paths:
        im = Image.open(p)
        box = find_preview(im)
        if box is None:
            print("no preview box:", p)
            continue
        crop = im.crop(box).convert("L")
        g = np.asarray(crop).astype(np.float64)
        face = roi(g, 0.30, 0.18, 0.62, 0.72)   # 人脸中部
        bg = roi(g, 0.66, 0.10, 0.95, 0.42)     # 书架/墙面
        rows.append(dict(
            name=os.path.basename(p),
            box=box,
            f_lap=lap_var(face), f_hf=hf_ratio(face), f_lum=face.mean(),
            f_grad=sob_mean(face),
            b_lap=lap_var(bg), b_hf=hf_ratio(bg), b_lum=bg.mean(),
            b_grad=sob_mean(bg),
        ))
    hdr = ("%-34s %10s %8s %8s %8s | %10s %8s %8s %8s"
           % ("file", "f_lap", "f_hf", "f_lum", "f_grad", "b_lap", "b_hf", "b_lum", "b_grad"))
    print(hdr)
    for r in rows:
        print("%-34s %10.2f %8.5f %8.2f %8.3f | %10.2f %8.5f %8.2f %8.3f"
              % (r["name"][:34], r["f_lap"], r["f_hf"], r["f_lum"], r["f_grad"],
                 r["b_lap"], r["b_hf"], r["b_lum"], r["b_grad"]))
    return rows


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args if args else sorted(glob.glob(
        "C:/Users/<user>/.workbuddy/clipboard-images/clipboard-2026-10-25T14-25-26-*.jpg")))
