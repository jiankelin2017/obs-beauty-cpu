# -*- coding: utf-8 -*-
"""Probe 3: cost breakdown. Is face-detect-only cheap enough to run per frame?

Goal: if Process2Result with landmark OFF + skin OFF costs only a few ms, we can
run it EVERY frame to get an exact face rect, and toggle skin seg ON every Nth
frame for the mask. That gives a lag-free mask at low amortised cost.
"""
import ctypes, os, time
from ctypes import c_void_p, c_int, c_float, POINTER, byref

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = r"D:\插件\obs-beauty-filter\installer\stage\fuai.dll"
BUNDLE = r"D:\插件\LegacyBeauty_v1.51\05_解密模型数据\ai_face_processor_pc\ai_face_processor_pc.bundle"
RAW = os.path.join(HERE, "probe_in.raw")
W, H = 640, 394

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
SetDetEveryFace = bind("FUAI_FaceProcessorSetDetectEveryNFramesWhenFace", None, [P, I])
SetUseLandmark = bind("FUAI_FaceProcessorSetUseFaceLandmark", None, [P, I])
SetUseHead = bind("FUAI_FaceProcessorSetUseHeadSegmenter", None, [P, I])
SetUseHair = bind("FUAI_FaceProcessorSetUseHairSegmenter", None, [P, I])
SetUseSkin = bind("FUAI_FaceProcessorSetUseSkinSeg", None, [P, I])
GetRect = bind("FUAI_FaceProcessorGetRectFromResult", POINTER(c_float), [P, I])
GetLandmarks = bind("FUAI_FaceProcessorGetLandmarksFromResult", POINTER(c_float), [P, I, POINTER(I)])

raw = open(RAW, "rb").read()
buf = ctypes.create_string_buffer(raw)
bundle = open(BUNDLE, "rb").read()
bbuf = ctypes.create_string_buffer(bundle, len(bundle))


def fresh():
    p = NewProc(ctypes.cast(bbuf, P), len(bundle))
    r = NewResult()
    v = NewView()
    SetMaxFaces(p, 2)
    SetDetectMode(p, 0)
    SetUseLandmark(p, 1)
    SetUseHead(p, 0)
    SetUseHair(p, 0)
    InitView(v, 3, W, H, 0, None, W * 4, None, 0, None, 0)
    SetViewData(v, 0, ctypes.cast(buf, P))
    return p, r, v


def bench(p, r, v, n=30, label=""):
    ts = []
    for k in range(n):
        t0 = time.perf_counter()
        Process(p, v, r)
        ts.append((time.perf_counter() - t0) * 1000.0)
    ts.sort()
    print("%-40s med=%6.2f min=%6.2f max=%6.2f" %
          (label, ts[len(ts) // 2], ts[0], ts[-1]))
    return ts[len(ts) // 2]


def info(p, r, v):
    n = GetNum(r)
    rect = None
    if n > 0:
        q = GetRect(r, 0)
        rect = [round(q[0], 1), round(q[1], 1), round(q[2], 1), round(q[3], 1)]
    w = I(); h = I(); ex = (I * 256)()
    sk = GetSkin(p, v, byref(w), byref(h), ex)
    nl = I()
    lm = GetLandmarks(r, 0, byref(nl)) if n > 0 else None
    print("      faces=%d rect=%s skin=%s %sx%s landmarks=%s" %
          (n, rect, bool(sk) and w.value > 0,
           w.value if sk else 0, h.value if sk else 0, nl.value if lm else 0))


print("=== 1. image mode: skin ON + landmark ON (production) ===")
p, r, v = fresh(); SetUseSkin(p, 1)
bench(p, r, v, 30, "skin=ON landmark=ON"); info(p, r, v)

print("\n=== 2. image mode: skin OFF + landmark ON ===")
p, r, v = fresh(); SetUseSkin(p, 0)
bench(p, r, v, 30, "skin=OFF landmark=ON"); info(p, r, v)

print("\n=== 3. image mode: skin OFF + landmark OFF  (probe crash risk) ===")
try:
    p, r, v = fresh()
    SetUseLandmark(p, 0)
    SetUseSkin(p, 0)
    bench(p, r, v, 30, "skin=OFF landmark=OFF")
    info(p, r, v)
except Exception as e:
    print("   FAILED:", e)

print("\n=== 4. image mode: skin ON + landmark OFF (may crash) ===")
try:
    p, r, v = fresh()
    SetUseLandmark(p, 0)
    SetUseSkin(p, 1)
    bench(p, r, v, 30, "skin=ON landmark=OFF")
    info(p, r, v)
except Exception as e:
    print("   FAILED:", e)

print("\n=== 5. video mode detect-every-3: skin OFF + landmark OFF ===")
try:
    p, r, v = fresh()
    SetDetectMode(p, 1)
    SetDetEveryFace(p, 3)
    SetUseLandmark(p, 0)
    SetUseSkin(p, 0)
    bench(p, r, v, 30, "video skin=OFF landmark=OFF")
    info(p, r, v)
except Exception as e:
    print("   FAILED:", e)
