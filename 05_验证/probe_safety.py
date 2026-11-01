# -*- coding: utf-8 -*-
"""Probe 5 (SAFETY): landmark=OFF skin seg must not fire when there is no face.

probe_mask_lag.py proved landmark=OFF keeps the mask identical and costs ~3 ms
instead of ~12 ms. But the risk is the opposite direction: with the landmark
model disabled the skin segmenter may no longer be gated on "a face is present",
so wooden tables / beige walls could get segmented as skin.

Checks:
  1. pixel-exact equality of the landmark ON vs OFF masks on the same frame
  2. no-face frames: coverage must stay ~0, not explode
  3. cost at the user's real resolution
  4. a frame where the face leaves entirely mid-sequence
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
SetUseLandmark = bind("FUAI_FaceProcessorSetUseFaceLandmark", None, [P, I])
SetUseHead = bind("FUAI_FaceProcessorSetUseHeadSegmenter", None, [P, I])
SetUseHair = bind("FUAI_FaceProcessorSetUseHairSegmenter", None, [P, I])
SetUseSkin = bind("FUAI_FaceProcessorSetUseSkinSeg", None, [P, I])
GetRect = bind("FUAI_FaceProcessorGetRectFromResult", POINTER(c_float), [P, I])

bundle = open(BUNDLE, "rb").read()
bbuf = ctypes.create_string_buffer(bundle, len(bundle))
base = bytearray(open(RAW, "rb").read())


def make_no_face():
    """Crop away the face: keep only the right 40% of the frame, upscaled back."""
    out = bytearray(len(base))
    for y in range(H):
        row = y * W * 4
        for x in range(W):
            sx = int(W * 0.62 + (x / float(W)) * W * 0.38)
            if sx >= W:
                sx = W - 1
            out[row + x * 4: row + x * 4 + 4] = base[row + sx * 4: row + sx * 4 + 4]
    return bytes(out)


def make_skinlike_no_face():
    """A flat tan/beige field - the classic false-positive colour for skin."""
    out = bytearray(len(base))
    for y in range(H):
        row = y * W * 4
        for x in range(W):
            i = row + x * 4
            out[i + 0] = 200      # R
            out[i + 1] = 160      # G
            out[i + 2] = 130      # B
            out[i + 3] = 255
    return bytes(out)


def fresh(landmark, maxfaces=2):
    p = NewProc(ctypes.cast(bbuf, P), len(bundle))
    r = NewResult()
    v = NewView()
    SetMaxFaces(p, maxfaces)
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
    t0 = time.perf_counter()
    Process(p, v, r)
    ms = (time.perf_counter() - t0) * 1000.0
    mw = I(); mh = I(); ex = (I * 256)()
    sk = GetSkin(p, v, byref(mw), byref(mh), ex)
    m = None
    cov = 0.0
    if sk and mw.value > 0 and mh.value > 0:
        n = mw.value * mh.value
        m = [0] * n
        hit = 0
        for i in range(n):
            q = int(sk[i] * 255.0 + 0.5)
            q = 0 if q < 0 else (255 if q > 255 else q)
            m[i] = q
            if q >= 128:
                hit += 1
        cov = hit / float(n)
    return m, mw.value, mh.value, cov, ms, GetNum(r)


print("=== 1. pixel-exact equality, face present ===")
pA, rA, vA = fresh(1)
pB, rB, vB = fresh(0)
img = bytes(base)
mA, wa, ha, ca, ta, na = run(pA, rA, vA, img, W, H)
mB, wb, hb, cb, tb, nb = run(pB, rB, vB, img, W, H)
print("   landmark=ON  faces=%d %dx%d cov=%.5f %.2fms" % (na, wa, ha, ca, ta))
print("   landmark=OFF faces=%d %dx%d cov=%.5f %.2fms" % (nb, wb, hb, cb, tb))
if mA and mB and (wa, ha) == (wb, hb):
    diff = sum(1 for i in range(len(mA)) if abs(mA[i] - mB[i]) > 2)
    mx = max(abs(mA[i] - mB[i]) for i in range(len(mA)))
    print("   pixels differing >2: %d / %d (%.4f%%), max abs diff = %d"
          % (diff, len(mA), 100.0 * diff / len(mA), mx))
else:
    print("   !! mask sizes differ or one is null")

print("\n=== 2. NO-FACE frames: coverage must stay tiny ===")
for name, img in (("face cropped out", make_no_face()),
                  ("flat tan field", make_skinlike_no_face())):
    mA, wa, ha, ca, ta, na = run(pA, rA, vA, img, W, H)
    mB, wb, hb, cb, tb, nb = run(pB, rB, vB, img, W, H)
    print("   %-18s landmark=ON  faces=%d cov=%.5f %.2fms" % (name, na, ca, ta))
    print("   %-18s landmark=OFF faces=%d cov=%.5f %.2fms" % ("", nb, cb, tb))

print("\n=== 3. face leaves the frame entirely (3 consecutive no-face frames) ===")
img_no = make_no_face()
for k in range(3):
    mA, wa, ha, ca, ta, na = run(pA, rA, vA, img_no, W, H)
    mB, wb, hb, cb, tb, nb = run(pB, rB, vB, img_no, W, H)
    print("   frame %d  landmark=ON faces=%d cov=%.5f | landmark=OFF faces=%d cov=%.5f"
          % (k, na, ca, nb, cb))

print("\n=== 4. timing at user resolution 1074x604 (upscaled from probe frame) ===")
W2, H2 = 1074, 604
big = bytearray(W2 * H2 * 4)
for y in range(H2):
    sy = y * H // H2
    for x in range(W2):
        sx = x * W // W2
        big[(y * W2 + x) * 4:(y * W2 + x) * 4 + 4] = base[(sy * W + sx) * 4:(sy * W + sx) * 4 + 4]
big = bytes(big)
for lm in (1, 0):
    p, r, v = fresh(lm)
    ts = []
    for k in range(15):
        m, w, h, c, ms, n = run(p, r, v, big, W2, H2)
        ts.append(ms)
    ts.sort()
    print("   landmark=%d  %dx%d  med=%6.2f min=%6.2f max=%6.2f  cov=%.5f faces=%d"
          % (lm, W2, H2, ts[len(ts) // 2], ts[0], ts[-1], c, n))
