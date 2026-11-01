# -*- coding: utf-8 -*-
"""Probe: fuai.dll Process2Result cost with/without skin seg.

Decides the mask-lag fix design:
  A) every frame run tracking-only Process2Result (skin seg off) + GetRectFromResult
     -> shift the cached 192x256 mask by the rect delta. Cheap, exact.
  B) probe CNamaSDK fuGetFaceInfo (free per-frame face rect from the beauty SDK).
"""
import ctypes, os, sys, time
from ctypes import c_void_p, c_int, c_float, POINTER, byref

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = r"D:\插件\obs-beauty-filter\installer\stage\fuai.dll"
BUNDLE = r"D:\插件\LegacyBeauty_v1.51\05_解密模型数据\ai_face_processor_pc\ai_face_processor_pc.bundle"
RAW = os.path.join(HERE, "probe_in.raw")          # 640x394 RGBA

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
SetUseLandmark = bind("FUAI_FaceProcessorSetUseFaceLandmark", None, [P, I])
SetUseHead = bind("FUAI_FaceProcessorSetUseHeadSegmenter", None, [P, I])
SetUseHair = bind("FUAI_FaceProcessorSetUseHairSegmenter", None, [P, I])
SetUseSkin = bind("FUAI_FaceProcessorSetUseSkinSeg", None, [P, I])
GetRect = bind("FUAI_FaceProcessorGetRectFromResult", POINTER(c_float), [P, I])

raw = open(RAW, "rb").read()
assert len(raw) == W * H * 4, len(raw)
buf = ctypes.create_string_buffer(raw)

bundle = open(BUNDLE, "rb").read()
bbuf = ctypes.create_string_buffer(bundle, len(bundle))

proc = NewProc(ctypes.cast(bbuf, P), len(bundle))
res = NewResult()
view = NewView()
print("proc=%s res=%s view=%s" % (proc, res, view))
assert proc and res and view

SetMaxFaces(proc, 2)
SetDetectMode(proc, 0)
SetUseLandmark(proc, 1)
SetUseHead(proc, 0)
SetUseHair(proc, 0)

InitView(view, 3, W, H, 0, None, W * 4, None, 0, None, 0)
SetViewData(view, 0, ctypes.cast(buf, P))


def run(tag, n=20):
    ts = []
    for k in range(n):
        t0 = time.perf_counter()
        Process(proc, view, res)
        ts.append((time.perf_counter() - t0) * 1000.0)
    ts.sort()
    print("%-28s n=%2d  med=%6.2f  min=%6.2f  max=%6.2f" %
          (tag, n, ts[len(ts) // 2], ts[0], ts[-1]))
    return ts[len(ts) // 2]


def rects(tag):
    n = GetNum(res)
    out = []
    for i in range(max(n, 0)):
        p = GetRect(res, i)
        out.append([round(p[0], 1), round(p[1], 1), round(p[2], 1), round(p[3], 1)])
    print("%-28s faces=%d rects=%s" % (tag, n, out))
    return out


def skin(tag):
    w = I(); h = I(); extra = (I * 256)()
    p = GetSkin(proc, view, byref(w), byref(h), extra)
    print("%-28s skin ptr=%s %dx%d" % (tag, bool(p), w.value, h.value))
    return bool(p)


print("\n=== skin seg ON ===")
SetUseSkin(proc, 1)
run("skin=ON")
rects("skin=ON")
skin("skin=ON")

print("\n=== skin seg OFF ===")
SetUseSkin(proc, 0)
run("skin=OFF")
rects("skin=OFF")
skin("skin=OFF")

print("\n=== toggle ON again (does it reset tracking?) ===")
SetUseSkin(proc, 1)
run("skin=ON again")
rects("skin=ON again")
skin("skin=ON again")

print("\n=== toggle OFF again ===")
SetUseSkin(proc, 0)
run("skin=OFF again")
rects("skin=OFF again")
