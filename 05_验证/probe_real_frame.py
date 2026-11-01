# -*- coding: utf-8 -*-
"""Probe: 在**真实网络摄像头帧**上对比关键点开/关的皮肤掩码。

probe_in.raw 是干净的单人照，静态序列上两种模式逐比特相同。但用户看到故障的
是真实摄像头画面 —— 噪声、压缩痕迹、复杂背景都可能让「无人脸先验的分割器」
行为完全不同。

同时检查一个致命的可能：GetSkinSegResult 是否在某些帧返回 NULL 或尺寸异常。
一旦返回 NULL，引擎会 hasMask_=false → 整帧改走 v1.4 颜色启发式 applyWhiten，
两条完全不同的算法逐帧交替 = 画面剧烈闪烁。
"""
import ctypes
import os
import sys
from ctypes import c_void_p, c_int, c_float, POINTER, byref

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from measure_whiten_fixed import read_png_rgba  # noqa: E402

DLL = r"D:\插件\obs-beauty-filter\installer\stage\fuai.dll"
BUNDLE = r"D:\插件\LegacyBeauty_v1.51\05_解密模型数据\ai_face_processor_pc\ai_face_processor_pc.bundle"

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

_seed = [777]


def rnd():
    _seed[0] = (_seed[0] * 1103515245 + 12345) & 0x7FFFFFFF
    return _seed[0]


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


def run(p, r, v, img, w, h):
    InitView(v, 3, w, h, 0, None, w * 4, None, 0, None, 0)
    b = ctypes.create_string_buffer(img, len(img))
    SetViewData(v, 0, ctypes.cast(b, P))
    Process(p, v, r)
    mw = I(); mh = I(); ex = (I * 256)()
    sk = GetSkin(p, v, byref(mw), byref(mh), ex)
    null_cnt = 0 if sk else 1
    if not sk or mw.value <= 0 or mh.value <= 0:
        return None, 0, 0, null_cnt, GetNum(r)
    n = mw.value * mh.value
    m = [0] * n
    for i in range(n):
        q = int(sk[i] * 255.0 + 0.5)
        m[i] = 0 if q < 0 else (255 if q > 255 else q)
    return m, mw.value, mh.value, null_cnt, GetNum(r)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "frame_0.png")
    rgba, W, H = read_png_rgba(path)
    print("输入: %s  %dx%d" % (path, W, H))

    # 造一段带真实感噪声的序列
    frames = []
    for k in range(24):
        b = bytearray(rgba)
        for i in range(0, len(b), 4):
            for c in range(3):
                v = b[i + c] + (rnd() % 5) - 2
                b[i + c] = 0 if v < 0 else (255 if v > 255 else v)
        frames.append(bytes(b))

    res = {}
    for lm in (1, 0):
        p, r, v = fresh(lm)
        masks = []
        covs = []
        nulls = 0
        faces = set()
        for k in range(len(frames)):
            m, mw, mh, nc, nf = run(p, r, v, frames[k], W, H)
            nulls += nc
            faces.add(nf)
            if m is None:
                masks.append(None)
                covs.append(0.0)
            else:
                masks.append(m)
                covs.append(sum(1 for q in m if q >= 128) / float(len(m)))
        res[lm] = (masks, covs, nulls, faces)
        print("")
        print("关键点=%s  NULL 帧数=%d  GetNum 取值=%s"
              % ("ON " if lm else "OFF", nulls, sorted(faces)))
        print("   覆盖度 min=%.5f max=%.5f 极差=%.5f"
              % (min(covs), max(covs), max(covs) - min(covs)))
        diffs = []
        for k in range(1, len(masks)):
            a, b = masks[k - 1], masks[k]
            if a is None or b is None or len(a) != len(b):
                diffs.append(float("nan"))
                continue
            diffs.append(sum(abs(a[i] - b[i]) for i in range(len(a))) / float(len(a)))
        ok = [x for x in diffs if x == x]
        if ok:
            print("   相邻帧掩码平均|差| 均=%.3f max=%.3f" % (sum(ok) / len(ok), max(ok)))

    # 直接对比同一帧的掩码
    print("")
    print("=== 同一帧掩码逐像素对比（关键点 ON vs OFF）===")
    p1, r1, v1 = fresh(1)
    p0, r0, v0 = fresh(0)
    m1, w1, h1, _, _ = run(p1, r1, v1, frames[0], W, H)
    m0, w0, h0, _, _ = run(p0, r0, v0, frames[0], W, H)
    if m1 and m0 and (w1, h1) == (w0, h0):
        diff = sum(1 for i in range(len(m1)) if abs(m1[i] - m0[i]) > 32)
        mx = max(abs(m1[i] - m0[i]) for i in range(len(m1)))
        print("   尺寸 %dx%d  差异>32 的像素: %d / %d (%.3f%%)  max diff=%d"
              % (w1, h1, diff, len(m1), 100.0 * diff / len(m1), mx))
        c1 = sum(1 for q in m1 if q >= 128) / float(len(m1))
        c0 = sum(1 for q in m0 if q >= 128) / float(len(m0))
        print("   覆盖度 ON=%.5f  OFF=%.5f  差=%+.5f (%.1f%% 相对)"
              % (c1, c0, c0 - c1, 100.0 * (c0 - c1) / max(c1, 1e-9)))
    else:
        print("   掩码尺寸不一致或为空: ON=%s OFF=%s" % ((w1, h1), (w0, h0)))


if __name__ == "__main__":
    main()
