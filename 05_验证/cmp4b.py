# -*- coding: utf-8 -*-
"""四张截图的脸颊细节对比：避开眼镜/头发/轮廓，只看皮肤纹理保留度。"""
import glob
import os

import numpy as np
from PIL import Image

import importlib.util
spec = importlib.util.spec_from_file_location("c4", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cmp4.py"))
c4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c4)

# 脸颊 ROI（相对于预览画面的比例，左右各一块，避开镜框与发际线）
CHEEKS = [(0.40, 0.42, 0.50, 0.54), (0.48, 0.42, 0.58, 0.54)]
# 额头（磨皮最强区之一）
FOREHEAD = (0.43, 0.24, 0.55, 0.33)
# 背景墙
WALL = (0.70, 0.14, 0.92, 0.38)


def sub(g, box):
    h, w = g.shape
    x0, y0, x1, y1 = box
    return g[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def detail(g):
    """1-2px 细节能量（减 3x3 盒式模糊后的 std）"""
    p = np.pad(g, 1, mode="edge")
    box = np.zeros_like(g)
    for dy in range(3):
        for dx in range(3):
            box += p[dy:dy + g.shape[0], dx:dx + g.shape[1]]
    box /= 9.0
    return float((g - box).std())


def main():
    files = sorted(glob.glob(
        "C:/Users/<user>/.workbuddy/clipboard-images/clipboard-2026-10-25T14-25-26-*.jpg"))
    print("%-14s %9s %9s %9s %9s" % ("file", "左颊", "右颊", "额头", "墙面"))
    for p in files:
        im = Image.open(p)
        box = c4.find_preview(im)
        g = np.asarray(im.crop(box).convert("L")).astype(np.float64)
        lc = detail(sub(g, CHEEKS[0]))
        rc = detail(sub(g, CHEEKS[1]))
        fh = detail(sub(g, FOREHEAD))
        wl = detail(sub(g, WALL))
        print("%-14s %9.3f %9.3f %9.3f %9.3f"
              % (p.split("-")[-1].replace(".jpg", "")[:14], lc, rc, fh, wl))


if __name__ == "__main__":
    main()
