# -*- coding: utf-8 -*-
"""
blur_type / smooth_mode / skin_detect 三组 golden 的离线分析。

目的（第 0 批 0a）：
  1. blur_type = 0/1/2 三档到底怎么排序？强度差多少？
  2. 它们是「三套不同算法」还是「同一算法三个增益」？
     —— 判据：(out-src) 残差场之间的相关系数。
        高相关(>0.99) + 幅度成比例  => 同一核，只是增益不同
        低相关                        => 结构不同，是三套核
  3. smooth_mode 0-3、skin_detect 0/1 有没有实际差异（逐字节比）。

只用 numpy，不碰 OBS、不碰相机、不调用 SDK。
用法： python bt_analyze.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FLAT = os.path.join(HERE, "goldens_legacy", "flat")
SRC = os.path.join(HERE, "goldens_legacy", "src")
W, H = 640, 394


def load_raw(path):
    a = np.fromfile(path, dtype=np.uint8)
    if a.size != W * H * 4:
        raise ValueError("%s size=%d, expect %d" % (path, a.size, W * H * 4))
    return a.reshape(H, W, 4)


def luma(rgba):
    f = rgba[..., :3].astype(np.float32)
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def box3(x):
    """3x3 均值，边界用 clamp。"""
    p = np.pad(x, 1, mode="edge")
    s = np.zeros_like(x)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            s += p[dy:dy + H, dx:dx + W]
    return s / 9.0


def highpass(x):
    """3x3 高通的绝对值：|luma - box3(luma)|。"""
    return np.abs(x - box3(x))


def load_case(name):
    d = os.path.join(FLAT, name)
    with open(os.path.join(d, "params.json"), encoding="utf-8") as f:
        p = json.load(f)
    return p, load_raw(os.path.join(d, "out.raw"))


def main():
    src = load_raw(os.path.join(SRC, "face_src.raw"))
    src_l = luma(src)
    src_hp = highpass(src_l)
    print("src: %dx%d  luma mean=%.2f  hp mean=%.4f" % (W, H, src_l.mean(), src_hp.mean()))
    print()

    # ---------- 1. blur_type 三档 ----------
    levels = [0, 1, 25, 50, 75, 100]
    print("=" * 92)
    print("A. blur_type 三档：细节保留率（ROI = 该档位任一 bt 改动 > 4 的像素）")
    print("=" * 92)
    print("%-6s %-8s %-10s %-10s %-10s %-10s %-10s" %
          ("档位", "bt", "改动像素%", "平均|Δ|", "细频保留%", "hp_out", "最大差"))

    store = {}
    for lv in levels:
        outs = {}
        for bt in (0, 1, 2):
            name = "blur%03d_bt%d" % (lv, bt)
            p, o = load_case(name)
            outs[bt] = o
            store[(lv, bt)] = (p, o)

        # 统一 ROI：任一 bt 改动 > 4
        diff_any = np.zeros((H, W), dtype=bool)
        for bt in (0, 1, 2):
            dd = np.abs(outs[bt][..., :3].astype(np.int16) - src[..., :3].astype(np.int16))
            diff_any |= (dd.max(axis=2) > 4)

        roi_n = int(diff_any.sum())
        for bt in (0, 1, 2):
            o = outs[bt]
            dd = np.abs(o[..., :3].astype(np.int16) - src[..., :3].astype(np.int16))
            changed = (dd.max(axis=2) > 0).mean() * 100.0
            mean_abs = dd.mean()
            o_hp = highpass(luma(o))
            if roi_n > 0:
                ret = o_hp[diff_any].mean() / max(src_hp[diff_any].mean(), 1e-9) * 100.0
                hp_o = o_hp[diff_any].mean()
            else:
                ret = 100.0
                hp_o = 0.0
            print("%-6d %-8d %-10.2f %-10.3f %-10.2f %-10.4f %-10d" %
                  (lv, bt, changed, mean_abs, ret, hp_o, int(dd.max())))
        print("-" * 92)

    # ---------- 2. 三档是同一核还是三套核 ----------
    print()
    print("=" * 92)
    print("B. 结构判定：残差场 (out-src) 的相关系数与幅度比")
    print("   高相关 + 幅度成比例 => 同一核不同增益；低相关 => 不同核")
    print("=" * 92)
    print("%-6s %-10s %-10s %-10s %-10s %-10s" %
          ("档位", "r(0,1)", "r(0,2)", "r(1,2)", "|d2|/|d1|", "|d0|/|d1|"))
    for lv in levels:
        vecs = {}
        for bt in (0, 1, 2):
            o = store[(lv, bt)][1]
            d = (o[..., :3].astype(np.float32) - src[..., :3].astype(np.float32)).ravel()
            vecs[bt] = d
        def corr(a, b):
            sa, sb = a.std(), b.std()
            if sa < 1e-6 or sb < 1e-6:
                return float("nan")
            return float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))
        n1 = float(np.linalg.norm(vecs[1]))
        n0 = float(np.linalg.norm(vecs[0]))
        n2 = float(np.linalg.norm(vecs[2]))
        print("%-6d %-10.4f %-10.4f %-10.4f %-10.3f %-10.3f" %
              (lv, corr(vecs[0], vecs[1]), corr(vecs[0], vecs[2]), corr(vecs[1], vecs[2]),
               (n2 / n1 if n1 > 1e-9 else float("nan")),
               (n0 / n1 if n1 > 1e-9 else float("nan"))))

    # ---------- 3. smooth_mode / skin_detect 是否有差异 ----------
    print()
    print("=" * 92)
    print("C. smooth_mode 0-3 与 skin_detect 0/1：逐字节对比（基准 = blur050_bt1）")
    print("=" * 92)
    base_p, base = load_case("blur050_bt1")
    print("%-12s %-10s %-10s %-12s" % ("case", "最大差", "改动像素%", "与基准是否逐字节相同"))
    for name in ["smoothm0", "smoothm1", "smoothm2", "smoothm3", "skindet0", "skindet1"]:
        p, o = load_case(name)
        dd = np.abs(o[..., :3].astype(np.int16) - base[..., :3].astype(np.int16))
        changed = (dd.max(axis=2) > 0).mean() * 100.0
        same = bool((o == base).all())
        print("%-12s %-10d %-10.3f %-12s" % (name, int(dd.max()), changed, "是" if same else "否"))

    # ---------- 4. 三档互比（同一档位下 bt 之间的像素差）----------
    print()
    print("=" * 92)
    print("D. 同一档位下 bt 互比的像素级差异（看是否只是强度差）")
    print("=" * 92)
    print("%-6s %-14s %-14s %-14s" % ("档位", "bt0 vs bt1", "bt0 vs bt2", "bt1 vs bt2"))
    for lv in levels:
        row = []
        for a, b in ((0, 1), (0, 2), (1, 2)):
            oa = store[(lv, a)][1][..., :3].astype(np.int16)
            ob = store[(lv, b)][1][..., :3].astype(np.int16)
            dd = np.abs(oa - ob)
            row.append("max=%d mean=%.2f" % (int(dd.max()), dd.mean()))
        print("%-6d %-14s %-14s %-14s" % (lv, row[0], row[1], row[2]))


    # ---------- 5. 决定性实验：bilateral 匹配哪一档 ----------
    print()
    print("=" * 92)
    print("E. 裁定「哪一档是双边」：bilateral d=9 sc=40 分别匹配 bt0/bt1/bt2（100 档）")
    print("   S2 已证 bilateral 能复现 SDK 档位曲线；这里看它更像哪一档的核")
    print("=" * 92)
    try:
        import cv2
    except ImportError:
        print("  (未安装 cv2，跳过；可 pip install opencv-python 后重跑)")
        return 0

    src_rgb = src[..., :3].copy()
    bil = cv2.bilateralFilter(src_rgb, 9, 40, 13.5)
    print("%-10s %-12s %-12s %-12s" % ("", "RMSE", "MAD", "细频保留%"))
    o_bil = np.dstack([bil, src[..., 3:4]])
    bil_hp = highpass(luma(o_bil))
    for bt in (0, 1, 2):
        o = store[(100, bt)][1]
        dd_any = np.abs(o[..., :3].astype(np.int16) - src[..., :3].astype(np.int16))
        roi = (dd_any.max(axis=2) > 4)
        d = bil.astype(np.float32) - o[..., :3].astype(np.float32)
        rmse = float(np.sqrt((d[roi] ** 2).mean()))
        mad = float(np.abs(d[roi]).mean())
        ret = bil_hp[roi].mean() / max(src_hp[roi].mean(), 1e-9) * 100.0
        print("bt%-8d %-12.3f %-12.3f %-12.2f" % (bt, rmse, mad, ret))
    print()
    print("  RMSE 最小者 = bilateral 最接近的那一档。")

    # ---------- 6. 保边性判据：平坦区 vs 边缘区 ----------
    print()
    print("=" * 92)
    print("F. 保边性判据（决定性）：平坦区 vs 边缘区的细频保留率")
    print("   高斯不保边 => 两区保留率接近（比值≈1）；双边保边 => 边缘区保留率明显更高")
    print("=" * 92)
    # 用源图梯度幅值分位切两半
    gx = np.zeros_like(src_l)
    gy = np.zeros_like(src_l)
    gx[:, 1:-1] = src_l[:, 2:] - src_l[:, :-2]
    gy[1:-1, :] = src_l[2:, :] - src_l[:-2, :]
    grad = np.sqrt(gx * gx + gy * gy)

    print("%-10s %-14s %-14s %-10s %-12s" %
          ("", "平坦区保留%", "边缘区保留%", "边缘/平坦", "性质"))
    rows = [("bilateral", o_bil)]
    for bt in (0, 1, 2):
        rows.append(("bt%d" % bt, store[(100, bt)][1]))

    for name, o in rows:
        dd = np.abs(o[..., :3].astype(np.int16) - src[..., :3].astype(np.int16))
        roi = (dd.max(axis=2) > 4)
        g = grad[roi]
        if g.size == 0:
            continue
        thr = np.percentile(g, 50)
        flat_m = g <= thr
        edge_m = g > thr
        o_hp = highpass(luma(o))[roi]
        s_hp = src_hp[roi]
        rf = o_hp[flat_m].mean() / max(s_hp[flat_m].mean(), 1e-9) * 100.0
        re = o_hp[edge_m].mean() / max(s_hp[edge_m].mean(), 1e-9) * 100.0
        ratio = re / max(rf, 1e-9)
        kind = "保边型" if ratio > 1.25 else ("削平型" if ratio < 1.05 else "中间")
        print("%-10s %-14.2f %-14.2f %-10.3f %-12s" % (name, rf, re, ratio, kind))
    print()
    print("  解读：比值 >1.25 = 明显保边（双边族）；≈1.0 = 平坦区与边缘区同等削弱（高斯族）。")


if __name__ == "__main__":
    sys.exit(main())