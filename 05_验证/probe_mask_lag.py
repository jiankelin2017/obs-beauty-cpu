# -*- coding: utf-8 -*-
"""Probe 4 (DECISIVE): is the skin mask still valid when landmarks are OFF?

Cost breakdown found in probe 3 (image mode, 640x394):
    detection  ~2.6 ms
    landmarks  ~8.9 ms   <- the expensive part
    skin seg   ~0.3 ms   <- nearly free
    landmark OFF => GetNumFromResult()==0, no rect available. Dead end for rect.

But if the skin mask itself stays correct with landmarks OFF, we can run
Process2Result EVERY frame at ~2.6 ms and the lag problem disappears completely.

Test: shift the image horizontally by 60 px, then check whether the produced
192x256 mask centroid shifts by the corresponding amount in both modes.
"""
import ctypes, os, time, struct
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


def shifted(dx):
    """Return a copy of the frame shifted horizontally by dx pixels (wrap-free)."""
    out = bytearray(len(base))
    for y in range(H):
        row = y * W * 4
        for x in range(W):
            sx = x - dx
            if 0 <= sx < W:
                out[row + x * 4: row + x * 4 + 4] = base[row + sx * 4: row + sx * 4 + 4]
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
    t0 = time.perf_counter()
    Process(p, v, r)
    ms = (time.perf_counter() - t0) * 1000.0
    w = I(); h = I(); ex = (I * 256)()
    sk = GetSkin(p, v, byref(w), byref(h), ex)
    m = None
    cov = 0.0
    if sk and w.value > 0:
        n = w.value * h.value
        m = [0] * n
        hit = 0
        for i in range(n):
            q = int(sk[i] * 255.0 + 0.5)
            q = 0 if q < 0 else (255 if q > 255 else q)
            m[i] = q
            if q >= 128:
                hit += 1
        cov = hit / float(n)
    return m, w.value, h.value, cov, ms, GetNum(r)


def centroid(m, w, h):
    if not m:
        return None
    sx = sy = sw = 0.0
    for y in range(h):
        for x in range(w):
            v = m[y * w + x]
            sx += v * x; sy += v * y; sw += v
    if sw <= 0:
        return None
    # convert mask coords back to source pixel coords
    return (sx / sw * W / w, sy / sw * H / h, sw)


def write_bmp_gray(path, m, w, h, scale=3):
    """Upscale a grayscale mask to a viewable BMP."""
    ow, oh = w * scale, h * scale
    rows = []
    for y in range(oh - 1, -1, -1):
        row = bytearray()
        for x in range(ow):
            v = m[(y // scale) * w + (x // scale)]
            row += bytes((v, v, v))
        while len(row) % 4:
            row += b"\x00"
        rows.append(bytes(row))
    pix = b"".join(rows)
    fsz = 54 + len(pix)
    hdr = b"BM" + struct.pack("<IHHI", fsz, 0, 0, 54)
    hdr += struct.pack("<IiiHHIIiiII", 40, ow, oh, 1, 24, 0, len(pix), 2835, 2835, 0, 0)
    open(path, "wb").write(hdr + pix)


print("building shifted frames...")
img0 = bytes(base)            # face at x 262..376
img60 = shifted(60)           # face at x 202..316
imgM60 = shifted(-60)         # face at x 322..436

for lm in (1, 0):
    tag = "landmark=ON " if lm else "landmark=OFF"
    p, r, v = fresh(lm)
    out = {}
    for name, img in (("dx0", img0), ("dx+60", img60), ("dx-60", imgM60)):
        m, w, h, cov, ms, nf = run(p, r, v, img)
        c = centroid(m, w, h) if m else None
        out[name] = (m, w, h, c, cov, ms, nf)
        print("%s %-7s faces=%-2d cov=%.4f %6.2fms  centroid=(%.1f, %.1f) weight=%.0f"
              % (tag, name, nf, cov, ms, c[0], c[1], c[2]))
    # centroid deltas
    c0 = out["dx0"][3]; c1 = out["dx+60"][3]; c2 = out["dx-60"][3]
    if c0 and c1:
        print("   -> dx+60 centroid moved by %+.1f px (expect about +60)" % (c1[0] - c0[0]))
    if c0 and c2:
        print("   -> dx-60 centroid moved by %+.1f px (expect about -60)" % (c2[0] - c0[0]))
    for i, name in enumerate(("dx0", "dx+60", "dx-60")):
        m, w, h = out[name][0], out[name][1], out[name][2]
        if m:
            write_bmp_gray(os.path.join(HERE, "mask_lm%d_%s.bmp" % (lm, name)), m, w, h)
    print("")
