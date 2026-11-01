# -*- coding: utf-8 -*-
"""
blur_type 三档的「滤波器族」判别（第 0 批 0a 延伸 · 选项 A · 修订版）

第一版（本文件的 v1）有两处方法论错误，已修：
  · 错误 1：每个对象用自己的「改动>0」像素集，像素群体不同，曲线不能横向比。
            -> 改为统一 ROI = 三档改动的并集，所有对象在同一批像素上测。
  · 错误 2：残差自相关测到的宽Y/宽X 对高斯族也给出 3.3，
            说明它测的是源图自身的各向异性，不是核。
            -> 改为「MTF 轴向各向异性」：|H| 分别沿 fx 轴和 fy 轴测，
               这是比值量，源谱自动约掉。

三个判据：
  G. 梯度十分位衰减曲线（对比度依赖性）
       线性低通：各梯度档的保留率基本水平
       双边    ：高梯度档保留率明显上升
     排除 src_hp < 0.75 的像素（亚量化噪声，除法的分母问题）。

  H. 等效 MTF（径向）
       |H(f)| = sqrt(PSD_out / PSD_src)，核心区 16x16 块加窗 FFT 累积。

  I. MTF 轴向各向异性
       |H| 沿 fx 轴、fy 轴各自求降到 0.5 的频率 f50。
       椭圆核：长轴方向磨得更狠 => 该方向 f50 更小。
       文档记录固定 UV 半轴 => @640x394 预期 1.690 x 1.847 px，f50_x/f50_y 应 >1。

纯 numpy + cv2。不碰 OBS、不碰相机、不调用 SDK。
用法： python bt_mtf.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FLAT = os.path.join(HERE, "goldens_legacy", "flat")
SRC = os.path.join(HERE, "goldens_legacy", "src")
W, H = 640, 394

UV_SX = 0.002640845
UV_SY = 0.0046875

BIN_EDGES = [0.05, 0.10, 0.20, 0.30, 0.45, 0.60, 0.80, 1.00]
BIN_LABELS = ["%.2f-%.2f" % (BIN_EDGES[i], BIN_EDGES[i + 1])
              for i in range(len(BIN_EDGES) - 1)]
BS, STEP = 16, 8
HP_FLOOR = 0.75
LV = 100


def load_raw(path):
    a = np.fromfile(path, dtype=np.uint8)
    if a.size != W * H * 4:
        raise ValueError("%s size=%d, expect %d" % (path, a.size, W * H * 4))
    return a.reshape(H, W, 4)


def luma(rgba):
    f = rgba[..., :3].astype(np.float32)
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def load_case(name):
    d = os.path.join(FLAT, name)
    with open(os.path.join(d, "params.json"), encoding="utf-8") as f:
        p = json.load(f)
    return p, load_raw(os.path.join(d, "out.raw"))


def boxsum(mask, r):
    p = np.pad(mask.astype(np.int32), r)
    s = np.zeros(mask.shape, dtype=np.int32)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            s += p[dy:dy + H, dx:dx + W]
    return s


def box3(x):
    p = np.pad(x, 1, mode="edge")
    s = np.zeros_like(x)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            s += p[dy:dy + H, dx:dx + W]
    return s / 9.0


def highpass(x):
    return np.abs(x - box3(x))


def integral(mask):
    ii = np.zeros((H + 1, W + 1), dtype=np.int32)
    ii[1:, 1:] = np.cumsum(np.cumsum(mask.astype(np.int32), 0), 1)
    return ii


def rect_sum(ii, y0, y1, x0, x1):
    return int(ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0])


def psd_accum(img, ii, min_frac=0.85):
    win = np.outer(np.hanning(BS), np.hanning(BS)).astype(np.float32)
    acc = np.zeros((BS, BS), dtype=np.float64)
    need = BS * BS * min_frac
    n = 0
    for y in range(0, H - BS + 1, STEP):
        for x in range(0, W - BS + 1, STEP):
            if rect_sum(ii, y, y + BS, x, x + BS) < need:
                continue
            b = img[y:y + BS, x:x + BS].astype(np.float32)
            b = b - b.mean()
            F = np.fft.fft2(b * win)
            acc += (F.real ** 2 + F.imag ** 2)
            n += 1
    return acc, n


def radial_profile(psd):
    fy = np.fft.fftfreq(BS)[:, None] * 2.0
    fx = np.fft.fftfreq(BS)[None, :] * 2.0
    fr = np.sqrt(fy * fy + fx * fx)
    out = []
    for i in range(len(BIN_EDGES) - 1):
        m = (fr >= BIN_EDGES[i]) & (fr < BIN_EDGES[i + 1])
        out.append(psd[m].mean() if m.any() else np.nan)
    return np.array(out)


def axis_profile(psd, axis):
    """axis=0 -> 沿 fy（取 fx=0 那一列）；axis=1 -> 沿 fx（取 fy=0 那一行）。"""
    line = psd[:, 0] if axis == 0 else psd[0, :]
    ks = np.arange(1, BS // 2 + 1)
    vals = np.array([line[k] for k in ks])
    freqs = ks.astype(np.float64) / BS * 2.0   # 归一化到 Nyquist=1
    return freqs, vals


def f50(freqs, h):
    """|H| 降到 0.5 的频率，线性插值；没降到就 nan。"""
    ok = np.isfinite(h)
    f, h = freqs[ok], h[ok]
    for i in range(len(h) - 1):
        if h[i] >= 0.5 >= h[i + 1]:
            t = (h[i] - 0.5) / (h[i] - h[i + 1] + 1e-12)
            return float(f[i] + t * (f[i + 1] - f[i]))
    return float("nan")


def main():
    try:
        import cv2
    except ImportError:
        print("需要 opencv-python：pip install opencv-python")
        return 1

    src = load_raw(os.path.join(SRC, "face_src.raw"))
    src_l = luma(src)
    src_rgb = src[..., :3].copy()
    src_hp = highpass(src_l)

    gx = np.zeros_like(src_l)
    gy = np.zeros_like(src_l)
    gx[:, 1:-1] = src_l[:, 2:] - src_l[:, :-2]
    gy[1:-1, :] = src_l[2:, :] - src_l[:-2, :]
    grad = np.sqrt(gx * gx + gy * gy)

    print("=" * 106)
    print("0. 参考：文档记录的固定 UV 半轴换算成像素")
    print("=" * 106)
    print("  sx=%.9f  sy=%.9f   (sy/sx = %.4f)" % (UV_SX, UV_SY, UV_SY / UV_SX))
    print("  @1136x640 -> %.3f x %.3f px   (正圆)" % (UV_SX * 1136, UV_SY * 640))
    print("  @640x394  -> %.3f x %.3f px   (竖椭圆)" % (UV_SX * W, UV_SY * H))
    print("  若核按此固定 UV 生成，I 段的 f50_x/f50_y 应 > 1（竖直方向磨得更狠）")
    print()

    outs = {}
    for bt in (0, 1, 2):
        _, outs[bt] = load_case("blur%03d_bt%d" % (LV, bt))

    # ---- 统一 ROI：三档改动的并集 ----
    common = np.zeros((H, W), dtype=bool)
    for bt in (0, 1, 2):
        dd = np.abs(outs[bt][..., :3].astype(np.int16) - src[..., :3].astype(np.int16))
        common |= (dd.max(axis=2) > 0)
    print("统一 ROI（三档改动并集）= %d px = 全图 %.1f%%" % (int(common.sum()),
                                                       common.mean() * 100))
    core = boxsum(common, 4) == 81
    ii = integral(core)
    psd_src, NB = psd_accum(src_l, ii)
    print("MTF 核心区 = %d px，可用 16x16 块 n=%d" % (int(core.sum()), NB))
    print()

    cands = []
    for s in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        cands.append(("gauss_s%.1f" % s, "高斯族", cv2.GaussianBlur(src_rgb, (0, 0), s)))
    for k in (3, 5, 7, 9):
        cands.append(("box_r%d" % (k // 2), "盒式族", cv2.blur(src_rgb, (k, k))))
    for sc in (15, 25, 40):
        cands.append(("bilat_c%d" % sc, "双边族", cv2.bilateralFilter(src_rgb, 9, sc, 13.5)))

    rows = [("bt%d" % bt, "SDK", outs[bt]) for bt in (0, 1, 2)]
    for name, fam, img in cands:
        rows.append((name, fam, np.dstack([img, src[..., 3:4]])))

    # ================= G =================
    print("=" * 106)
    print("G. 梯度十分位衰减曲线 @ 强度 %d（统一 ROI，排除 src_hp<%.2f）" % (LV, HP_FLOOR))
    print("   格子 = 该梯度档细频保留率%%；曲线平 = 不依赖对比度 = 线性低通；上升 = 保边")
    print("=" * 106)

    sel = common & (src_hp >= HP_FLOOR)
    print("  参与统计像素 = %d" % int(sel.sum()))
    g = grad[sel]
    qs = np.percentile(g, np.arange(10, 100, 10))
    idx = np.searchsorted(qs, g)
    cnt = [int((idx == i).sum()) for i in range(10)]
    print("  各档像素数： " + " ".join("%6d" % c for c in cnt))
    print("  各档源高频： " + " ".join("%6.2f" % src_hp[sel][idx == i].mean() for i in range(10)))
    print()
    print("  %-13s %-8s %s %-9s %-13s" %
          ("", "族", " ".join("%6s" % ("D%d" % (i + 1)) for i in range(10)),
           "依赖比", "判定"))
    print("  " + "-" * 104)

    curves = {}
    for name, fam, o in rows:
        o_hp = highpass(luma(o))[sel]
        s_hp = src_hp[sel]
        curve = np.array([
            o_hp[idx == i].mean() / max(s_hp[idx == i].mean(), 1e-9) * 100.0
            for i in range(10)])
        dep = curve[-1] / max(curve[0], 1e-9)
        kind = ("强保边" if dep > 1.30 else "弱保边" if dep > 1.12 else
                "线性低通" if dep < 1.08 else "中间")
        curves[name] = (fam, curve, dep)
        print("  %-13s %-8s %s %-9.3f %-13s" %
              (name, fam, " ".join("%6.1f" % v for v in curve), dep, kind))
    print("  " + "-" * 104)
    print()

    print("  ---- 曲线形状匹配（10 点 L2，允许平移一个常数以消除整体强度差）----")
    print("  %-8s %-14s %-10s %-14s %-10s %-14s" %
          ("SDK档", "最像", "残差", "次像", "残差", "最像的族"))
    for bt in (0, 1, 2):
        key = "bt%d" % bt
        ref = curves[key][1]
        sc = []
        for name, (fam, curve, dep) in curves.items():
            if fam == "SDK":
                continue
            diff = curve - ref
            diff = diff - diff.mean()
            sc.append((float(np.sqrt((diff ** 2).mean())), name, fam))
        sc.sort()
        print("  %-8s %-14s %-10.3f %-14s %-10.3f %-14s" %
              (key, sc[0][1], sc[0][0], sc[1][1], sc[1][0], sc[0][2]))
    print()

    # ================= H + I =================
    print("=" * 106)
    print("H. 等效 MTF（径向）+ I. 轴向各向异性 @ 强度 %d" % LV)
    print("=" * 106)
    print("  %-13s %-8s %s %-8s %-8s %-9s" %
          ("", "族", " ".join("%9s" % b for b in BIN_LABELS), "f50_x", "f50_y", "x/y"))
    print("  " + "-" * 104)
    for name, fam, o in rows:
        psd_o, n = psd_accum(luma(o), ii)
        if n == 0:
            continue
        p_out, p_src = radial_profile(psd_o), radial_profile(psd_src)
        with np.errstate(divide="ignore", invalid="ignore"):
            h = np.sqrt(np.where(p_src > 0, p_out / p_src, np.nan))
        fx, vx = axis_profile(psd_o, 1)
        fy, vy = axis_profile(psd_o, 0)
        sx, sy = axis_profile(psd_src, 1)[1], axis_profile(psd_src, 0)[1]
        with np.errstate(divide="ignore", invalid="ignore"):
            hx = np.sqrt(np.where(sx > 0, vx / sx, np.nan))
            hy = np.sqrt(np.where(sy > 0, vy / sy, np.nan))
        f50x, f50y = f50(fx, hx), f50(fy, hy)
        r = f50x / f50y if (f50x == f50x and f50y == f50y and f50y > 0) else float("nan")
        print("  %-13s %-8s %s %-8.3f %-8.3f %-9.3f" %
              (name, fam, " ".join("%9.3f" % v for v in h),
               f50x, f50y, r))
    print("  " + "-" * 104)
    print("  注：f50 未降到 0.5 记 nan（磨得太轻，全程高于 0.5）。")
    print("      x/y > 1 表示水平方向衰减更快、竖直方向磨得更狠 => 竖椭圆核。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
