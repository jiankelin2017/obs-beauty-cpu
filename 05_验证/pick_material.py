# -*- coding: utf-8 -*-
"""pick_material —— 从相机目录批量筛人脸素材（离线工具，不进插件）。

为什么要有这个脚本：磨皮画质的评价口径是「五区域 × 三频带保留率」，
要求脸足够大（脸宽占画面 25%~40%）、大致正脸、且画面里有可辨认的皮肤细节。
263 张相机原图靠人眼一张张翻不现实，先用 YuNet（与插件同一个模型）自动量一遍。

量什么：
  face_ratio  最大脸的宽 / 画面宽 —— 决定五区域能不能分得开
  face_px     最大脸的宽（原图像素）—— 决定细频带有没有统计意义
  yaw         |鼻尖 x − 两眼中点 x| / 眼距 —— 正脸程度，越小越正
  roll        两眼连线与水平夹角（度）—— 歪头程度
  detail      脸部区域高频能量的 std —— 皮肤细节多不多（痘印/纹理的代理指标）
  faces       画面里检出几张脸 —— 单人优先，多人会干扰掩码对拍

用法：
    python pick_material.py                 # 全目录
    python pick_material.py 20              # 只看前 20 张（试跑）
"""

from __future__ import print_function

import csv
import math
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageOps

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = r"D:\100MSDCF"
MODEL = os.path.join(HERE, "models", "yunet.onnx")
OUT_CSV = os.path.join(HERE, "_material_scan.csv")

LONG_EDGE = 1280      # 检测用的长边（YuNet 内部还会缩到 640）
SCORE_THR = 0.6       # 置信度门限，与插件一致


def ascii_model_copy():
    """OpenCV 的 ONNX importer 走 fopen，遇到中文路径会报 Can't read ONNX file。

    项目目录正好叫「D:\\插件\\OBS美颜」，所以先把模型拷到纯 ASCII 的临时目录。
    """
    try:
        MODEL.encode("ascii")
        return MODEL
    except UnicodeEncodeError:
        pass
    d = os.path.join(tempfile.gettempdir(), "yunet_scan")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, "yunet.onnx")
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(MODEL):
        shutil.copyfile(MODEL, dst)
    return dst


def analyze_face(img_bgr, box):
    """在原图上裁出脸区域，量清晰度与两档高频能量。"""
    x, y, w, h = box
    H, W = img_bgr.shape[:2]
    x0 = max(0, int(x)); y0 = max(0, int(y))
    x1 = min(W, int(x + w)); y1 = min(H, int(y + h))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0.0, 0.0, 0.0
    roi = img_bgr[y0:y1, x0:x1]
    # 统一到 256×256，让不同尺寸的脸之间可比
    roi = cv2.resize(roi, (256, 256), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lap = cv2.Laplacian(g, cv2.CV_32F)
    detail = float(lap.std())                      # 细尺度：痘印、唇纹所在
    mid = cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), 1.2), cv2.CV_32F)
    return detail, float(mid.std()), float(g.std())


def load_bgr(path):
    """读 JPEG 并按 EXIF Orientation 转正。

    相机竖拍的照片在文件里是横躺存的，方向只写在 EXIF 里。不转正的话
    YuNet 会把侧躺的人误检成一个横跨大半画面的「大脸」—— 第一轮扫描
    就栽在这上面，A7300862 报出 38.5% 的脸占比，实际只是一次误检。
    """
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGB")
    a = np.array(im)
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith((".jpg", ".jpeg")))
    if limit:
        files = files[:limit]

    det = cv2.FaceDetectorYN.create(ascii_model_copy(), "", (LONG_EDGE, LONG_EDGE),
                                    SCORE_THR, 0.3, 5000)
    rows = []
    for i, name in enumerate(files):
        path = os.path.join(SRC, name)
        img = load_bgr(path)
        oh, ow = img.shape[:2]
        scale = LONG_EDGE / float(max(oh, ow))
        small = cv2.resize(img, (int(ow * scale), int(oh * scale)),
                           interpolation=cv2.INTER_AREA)
        sh, sw = small.shape[:2]
        det.setInputSize((sw, sh))
        _, faces = det.detect(small)
        if faces is None or len(faces) == 0:
            rows.append(dict(name=name, ow=ow, oh=oh, faces=0))
            continue
        # 取最大的那张脸
        f = max(faces, key=lambda t: t[2] * t[3])
        fx, fy, fw, fh = f[0] / scale, f[1] / scale, f[2] / scale, f[3] / scale
        rex, rey, lex, ley = f[4] / scale, f[5] / scale, f[6] / scale, f[7] / scale
        ntx, nty = f[8] / scale, f[9] / scale
        eye_dx = lex - rex
        eye_dy = ley - rey
        eye_dist = math.hypot(eye_dx, eye_dy)
        eye_mid_x = (rex + lex) / 2.0
        yaw = abs(ntx - eye_mid_x) / eye_dist if eye_dist > 1 else 9.9
        roll = math.degrees(math.atan2(eye_dy, eye_dx))
        detail, mid, contrast = analyze_face(img, (fx, fy, fw, fh))
        rows.append(dict(name=name, ow=ow, oh=oh, faces=len(faces),
                         fx=fx, fy=fy, fw=fw, fh=fh,
                         ratio=fw / float(ow), face_px=fw,
                         yaw=yaw, roll=roll, score=float(f[14]),
                         detail=detail, mid=mid, contrast=contrast))
        if (i + 1) % 25 == 0:
            print("  ... %d / %d" % (i + 1, len(files)))

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as fp:
        cols = ["name", "ow", "oh", "faces", "ratio", "face_px", "yaw",
                "roll", "score", "detail", "mid", "contrast", "fx", "fy", "fw", "fh"]
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("写好了：%s（%d 行）" % (OUT_CSV, len(rows)))

    ok = [r for r in rows if r.get("faces") == 1 and r.get("ratio", 0) >= 0.15]
    print("\n=== 单人 + 脸宽占比 >= 15%，按脸占比排序（前 15）===")
    print("%-14s %6s %7s %6s %6s %8s" % ("文件", "占比%", "脸宽px", "yaw", "roll", "detail"))
    for r in sorted(ok, key=lambda t: -t["ratio"])[:15]:
        print("%-14s %6.1f %7.0f %6.2f %6.1f %8.1f"
              % (r["name"], r["ratio"] * 100, r["face_px"], r["yaw"], r["roll"], r["detail"]))

    print("\n=== 细节最丰富（找痘印/纹理阳性样本），脸占比 >= 15%（前 10）===")
    print("%-14s %6s %7s %6s %8s %8s" % ("文件", "占比%", "脸宽px", "yaw", "detail", "mid"))
    for r in sorted(ok, key=lambda t: -t["detail"])[:10]:
        print("%-14s %6.1f %7.0f %6.2f %8.1f %8.1f"
              % (r["name"], r["ratio"] * 100, r["face_px"], r["yaw"], r["detail"], r["mid"]))


if __name__ == "__main__":
    main()
