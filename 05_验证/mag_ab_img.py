# -*- coding: utf-8 -*-
"""生成 magHi=60（当前默认） 与 magHi=40（候选） 的离线参照图。

用途：真机验证时人脸在动、光照在变，肉眼很难判断"到底差多少"。
这里用同一张素材、同一档位跑出三张图并排，让人知道**该盯哪个部位、
应该看到什么方向的变化**。真机只是确认这个方向在摄像头画面上同样成立。

用法：
    python mag_ab_img.py            # 默认跑 100 档
    python mag_ab_img.py 80
"""
import os
import sys

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "goldens", "res")
sys.path.insert(0, HERE)
import box_sweep as B          # noqa: E402
import region_gap as RG        # noqa: E402

W, H = RG.W, RG.H

# 人脸框（region_gap 里的实测值）
BX, BY, BW_, BH_ = RG.BX, RG.BY, RG.BW_, RG.BH_
# 眼区：归一化 (0.18,0.28)-(0.82,0.46) 附近，取 REGIONS 里的定义
EYE_WIN = (0.18, 0.26, 0.84, 0.50)


def run(env, level, tag):
    path = os.path.join(OUT, "_magimg_%s.raw" % tag)
    r = B.spawn(["img", env, "%g" % level, path])
    img = np.fromfile(path, dtype=np.uint8).reshape((H, W, 4))
    os.remove(path)
    return img[:, :, :3], r["ms"]


def crop(img, win, k):
    x0 = int(BX + win[0] * BW_); x1 = int(BX + win[2] * BW_)
    y0 = int(BY + win[1] * BH_); y1 = int(BY + win[3] * BH_)
    x0 = max(0, x0); y0 = max(0, y0); x1 = min(W, x1); y1 = min(H, y1)
    c = img[y0:y1, x0:x1]
    return np.kron(c, np.ones((k, k, 1), dtype=np.uint8))


def side_by_side(imgs, labels, win, k, name):
    tiles = [crop(im, win, k) for im in imgs]
    h = max(t.shape[0] for t in tiles)
    for i, t in enumerate(tiles):
        if t.shape[0] < h:
            tiles[i] = np.concatenate(
                [t, np.full((h - t.shape[0], t.shape[1], 3), 255, dtype=np.uint8)],
                axis=0)
    gap = np.full((h, 10, 3), 255, dtype=np.uint8)
    parts = []
    for i, t in enumerate(tiles):
        parts.append(t)
        if i < len(tiles) - 1:
            parts.append(gap)
    out = np.concatenate(parts, axis=1)
    p = os.path.join(OUT, name)
    Image.fromarray(out).save(p)
    return p, out.shape, ["%s 宽%dpx" % (l, t.shape[1] // k)
                          for l, t in zip(labels, tiles)]


def main():
    level = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0

    print("档位 磨皮%g —— 生成三组（每个组合独立子进程）" % level)
    sdk, _ = run("SDK=1", level, "sdk")
    print("  SDK          ok")
    cur, ms60 = run("BEAUTY_FREQ_MAG=6,60", level, "cur")
    print("  core magHi=60 ok (%.2f ms)" % ms60)
    new, ms40 = run("BEAUTY_FREQ_MAG=6,40", level, "new")
    print("  core magHi=40 ok (%.2f ms)" % ms40)

    imgs = [sdk, cur, new]
    labels = ["SDK 目标", "core magHi=60（现在）", "core magHi=40（候选）"]

    p, shape, info = side_by_side(imgs, labels, (0.0, 0.0, 1.0, 1.0), 3,
                                  "_mag_face_%g.png" % level)
    print("\n全脸并排：%s  %s" % (p, shape))
    for s in info:
        print("   ", s)

    p2, shape2, _ = side_by_side(imgs, labels, EYE_WIN, 6,
                                 "_mag_eye_%g.png" % level)
    print("眼区放大：%s  %s" % (p2, shape2))

    # 数值佐证：中频保留率（额头/脸颊/眼区）
    src = RG.L.load(RG.RAW, W, H)
    sb = RG.bands(src)
    rms = RG.region_masks()
    tb = RG.bands(sdk)
    c1 = RG.bands(cur)
    c2 = RG.bands(new)
    print("\n中频保留率（越接近 SDK 越好；眼区是糊眼副作用判据）：")
    print("%-8s %10s %12s %12s" % ("区域", "SDK", "magHi=60", "magHi=40"))
    for name, m in rms:
        a = float(sb[1][m].mean())
        if a <= 1e-9:
            continue
        print("%-8s %9.1f%% %11.1f%% %11.1f%%"
              % (name, 100 * float(tb[1][m].mean()) / a,
                 100 * float(c1[1][m].mean()) / a,
                 100 * float(c2[1][m].mean()) / a))


if __name__ == "__main__":
    main()
