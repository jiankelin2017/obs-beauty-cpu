# -*- coding: utf-8 -*-
"""Probe 2: can we get a per-frame face rect cheaply from fuai?

Findings so far:
  - fuGetFaceInfo(item, "face_rect", ...) -> cert denied, all zeros. DEAD END.
  - Process2Result(image mode, skin on/off) = 12.4ms either way -> skin seg is
    NOT the cost driver; face detect + landmarks is.
  - GetRectFromResult(res, i) -> float[4] (x1,y1,x2,y2) in source pixels, works.

This probe tests video mode + detect-every-N: if the tracking-only frames get
cheap, we can run Process2Result every frame (cheap) and toggle skin seg on
only every Nth frame -> exact per-frame rect, amortised mask cost.
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


def bind(name, restype, argtypes):
    f = getattr(d, name)
    f.restype = restype
    f.argtypes = argtypes
    return f


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

raw = open(RAW, "rb").read()
assert len(raw) == W * H * 4
buf = ctypes.create_string_buffer(raw)
bundle = open(BUNDLE, "rb").read()
bbuf = ctypes.create_string_buffer(bundle, len(bundle))


def fresh():
    proc = NewProc(ctypes.cast(bbuf, P), len(bundle))
    res = NewResult()
    view = NewView()
    SetMaxFaces(proc, 2)
    SetDetectMode(proc, 1)              # 1 = video mode
    SetDetEveryFace(proc, 3)
    SetUseLandmark(proc, 1)
    SetUseHead(proc, 0)
    SetUseHair(proc, 0)
    InitView(view, 3, W, H, 0, None, W * 4, None, 0, None, 0)
    SetViewData(view, 0, ctypes.cast(buf, P))
    return proc, res, view


def bench(proc, res, view, n=40, label=""):
    ts = []
    for k in range(n):
        t0 = time.perf_counter()
        Process(proc, view, res)
        ts.append((time.perf_counter() - t0) * 1000.0)
    ts.sort()
    print("%-46s med=%6.2f min=%6.2f max=%6.2f" %
          (label, ts[len(ts) // 2], ts[0], ts[-1]))
    return ts[len(ts) // 2]


def rectof(res):
    n = GetNum(res)
    if n <= 0:
        return None
    p = GetRect(res, 0)
    return [round(p[0], 1), round(p[1], 1), round(p[2], 1), round(p[3], 1)]


def skinok(proc, view):
    w = I(); h = I(); extra = (I * 256)()
    p = GetSkin(proc, view, byref(w), byref(h), extra)
    return bool(p) and w.value > 0


print("=== A: video mode, detect-every-3, skin OFF, steady state ===")
proc, res, view = fresh()
SetUseSkin(proc, 0)
bench(proc, res, view, 40, "video/skinOFF steady")
print("   rect:", rectof(res), " skin:", skinok(proc, view))

print("\n=== B: video mode, detect-every-3, skin ON, steady state ===")
proc2, res2, view2 = fresh()
SetUseSkin(proc2, 1)
bench(proc2, res2, view2, 40, "video/skinON steady")
print("   rect:", rectof(res2), " skin:", skinok(proc2, view2))

print("\n=== C: interleaved - toggle skin ON every 3rd frame (the plan) ===")
proc3, res3, view3 = fresh()
SetUseSkin(proc3, 1)
ts = []
rects = []
skins = []
for k in range(30):
    want_skin = (k % 3 == 0)
    SetUseSkin(proc3, 1 if want_skin else 0)
    t0 = time.perf_counter()
    Process(proc3, view3, res3)
    ts.append((time.perf_counter() - t0) * 1000.0)
    rects.append(rectof(res3))
    skins.append(skinok(proc3, view3))
tss = sorted(ts)
print("   med=%6.2f min=%6.2f max=%6.2f" % (tss[len(tss) // 2], tss[0], tss[-1]))
print("   first 9 rects:", rects[:9])
print("   first 9 skin:", skins[:9])
print("   avg of 30   : %.2f ms" % (sum(ts) / len(ts)))

print("\n=== D: image mode baseline for reference (current production) ===")
proc4 = NewProc(ctypes.cast(bbuf, P), len(bundle))
res4 = NewResult()
view4 = NewView()
SetMaxFaces(proc4, 2)
SetDetectMode(proc4, 0)
SetUseLandmark(proc4, 1)
SetUseHead(proc4, 0)
SetUseHair(proc4, 0)
SetUseSkin(proc4, 1)
InitView(view4, 3, W, H, 0, None, W * 4, None, 0, None, 0)
SetViewData(view4, 0, ctypes.cast(buf, P))
bench(proc4, res4, view4, 40, "image/skinON (production)")
print("   rect:", rectof(res4), " skin:", skinok(proc4, view4))
