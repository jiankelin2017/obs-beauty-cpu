# -*- coding: utf-8 -*-
"""Probe: 关掉关键点后，皮肤掩码在连续帧之间还稳不稳？

2.1.1 的改动是「SetUseFaceLandmark(0) + 每帧推理」。静态图上掩码逐比特相同，
但真实视频是连续运动的画面 —— 关键点模型可能给分割器提供了人脸先验，
关掉后分割器退化成纯逐帧图像分类，边界会抖。

抖动会直接变成画面故障：掩码边界上的像素在 m=0（逐字节还原输入）和 m>0
（美白/磨皮）之间反复横跳。

做法：造一段「真实感」序列（人脸平移 + 轻微缩放 + 传感器噪声），分别用
关键点开/关跑，统计相邻帧掩码的平均绝对差。
"""
import ctypes
import os
import time
from ctypes import c_void_p, c_int, c_float, POINTER, byref

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = r"D:\插件\obs-beauty-filter\installer\stage\fuai.dll"
BUNDLE = r"D:\插件\LegacyBeauty_v1.51\05_解密模型数据\ai_face_processor_pc\ai_face_processor_pc.bundle"
RAW = os.path.join(HERE, "probe_in.raw")
W, H = 640, 394
N = 40

d = ctypes.CDLL(DLL)
P, I = c_void_p, c_int


def bind(n, rt, at):
    f = getattr(d, n); f.restype = rt; f.argtypes = at; return f


NewProc = bind("FUAI_NewFaceProcessorFromBundle", P, [P, I])
NewResult = bind("FUAI_NewFaceProcessorResult", P, [])
NewView = bind("FUAI_NewImageView", P, [])
InitView = bind("FUAI_ImageViewInit", None, [P, I, I, I, I, P, I, P, I, P, I])
SetViewData = bind("FUAI_ImageViewSetData", None, [P, I, P])
Process = bind("FUAI_FaceProcessorProcess2Result", None, [P, P, P])
GetNum = bind("FUAI_FaceProcessorGetNumFromResult", I, [P])
GetSkin = bind("FUAI_FaceProcessorGetSkinSegResult", POINTER(c_float),
               [P, P, POINTER(I), POINTER(I), POINTER(I)])
SetMaxFaces = bind("FUAI_FaceProcessorSetMaxFaces", None, [P, I])
SetDetectMode = bind("FUAI_FaceProcessorSetDetectMode", None, [P, I])
SetUseLandmark = bind("FUAI_FaceProcessorSetUseFaceLandmark", None, [P, I])
SetUseHead = bind("FUAI_FaceProcessorSetUseHeadSegmenter", None, [P, I])
SetUseHair = bind("FUAI_FaceProcessorSetUseHairSegmenter", None, [P, I])
SetUseSkin = bind("FUAI_FaceProcessorSetUseSkinSeg", None, [P, I])

bundle = open(BUNDLE, "rb").read()
bbuf = ctypes.create_string_buffer(bundle, len(bundle))
base = bytearray(open(RAW, "rb").read())

# 确定性伪随机，保证可复现
_seed = [12345]


def rnd():
    _seed[0] = (_seed[0] * 1103515245 + 12345) & 0x7FFFFFFF
    return _seed[0]


def make_frame(k):
    """第 k 帧：人脸以约 3px/帧 左右移动，带轻微缩放和传感器噪声。"""
    import math
    dx = int(round(18 * math.sin(k * 0.35)))       # ±18 px 往复
    scale = 1.0 + 0.010 * math.sin(k * 0.21)       # ±1% 缩放
    noise = 3                                      # ±3 级传感器噪声
    out = bytearray(len(base))
    for y in range(H):
        row = y * W * 4
        for x in range(W):
            # 以人脸中心为锚点缩放 + 平移
            ax = (x - 319.0) / scale + 319.0 - dx
            ay = (y - 197.0) / scale + 197.0
            sx, sy = int(round(ax)), int(round(ay))
            if 0 <= sx < W and 0 <= sy < H:
                s = (sy * W + sx) * 4
                o = row + x * 4
                for c in range(3):
                    v = base[s + c] + (rnd() % (2 * noise + 1)) - noise
                    out[o + c] = 0 if v < 0 else (255 if v > 255 else v)
                out[o + 3] = 255
            else:
                out[row + x * 4: row + x * 4 + 4] = b"\x00\x00\x00\xff"
    return bytes(out)


def fresh(landmark):
    p = NewProc(ctypes.cast(bbuf, P), len(bundle))
    r = NewResult()
    v = NewView()
    SetMaxFaces(p, 2)
    SetDetectMode(p, 0)
    SetUseLandmark(p, landmark)
    SetUseHead(p, 0)
    SetUseHair(p, 0)
    SetUseSkin(p, 1)
    return p, r, v


def run(p, r, v, img):
    InitView(v, 3, W, H, 0, None, W * 4, None, 0, None, 0)
    b = ctypes.create_string_buffer(img, len(img))
    SetViewData(v, 0, ctypes.cast(b, P))
    Process(p, v, r)
    w = I(); h = I(); ex = (I * 256)()
    sk = GetSkin(p, v, byref(w), byref(h), ex)
    if not sk or w.value <= 0 or h.value <= 0:
        return None, 0, 0
    n = w.value * h.value
    m = [0] * n
    hit = 0
    for i in range(n):
        q = int(sk[i] * 255.0 + 0.5)
        q = 0 if q < 0 else (255 if q > 255 else q)
        m[i] = q
        if q >= 128:
            hit += 1
    return m, w.value, h.value


def main():
    print("生成 %d 帧真实感序列..." % N)
    frames = [make_frame(k) for k in range(N)]

    for lm in (1, 0):
        tag = "关键点=ON " if lm else "关键点=OFF"
        p, r, v = fresh(lm)
        masks = []
        covs = []
        t0 = time.perf_counter()
        for k in range(N):
            m, w, h = run(p, r, v, frames[k])
            if m is None:
                masks.append(None)
                covs.append(0.0)
                continue
            masks.append(m)
            covs.append(sum(1 for q in m if q >= 128) / float(len(m)))
        dt = (time.perf_counter() - t0) / N * 1000.0

        # 相邻帧掩码差异
        diffs = []
        flips = 0
        tot = 0
        for k in range(1, N):
            a, b = masks[k - 1], masks[k]
            if a is None or b is None or len(a) != len(b):
                continue
            s = 0
            for i in range(len(a)):
                dd = abs(a[i] - b[i])
                s += dd
                if dd > 64:
                    flips += 1
                tot += 1
            diffs.append(s / float(len(a)))
        nz = [d for d in diffs]
        print("")
        print("%s 平均 %.2f ms/帧" % (tag, dt))
        print("  掩码覆盖度 min=%.5f max=%.5f 极差=%.5f"
              % (min(covs), max(covs), max(covs) - min(covs)))
        print("  相邻帧掩码平均|差|: min=%.2f  均=%.2f  max=%.2f"
              % (min(nz), sum(nz) / len(nz), max(nz)))
        print("  相邻帧差异>64 的像素占比: %.4f%%（掩码边界抖动程度）"
              % (100.0 * flips / max(tot, 1)))
        if lm == 1:
            ref = (sum(nz) / len(nz), 100.0 * flips / max(tot, 1))
        else:
            print("")
            print("  >>> 与关键点=ON 相比：平均|差| %.2f 倍，边界抖动 %.2f 倍"
                  % ((sum(nz) / len(nz)) / max(ref[0], 1e-9),
                     (100.0 * flips / max(tot, 1)) / max(ref[1], 1e-9)))


if __name__ == "__main__":
    main()
