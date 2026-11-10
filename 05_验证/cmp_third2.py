# -*- coding: utf-8 -*-
"""归一到同一脸宽（400px）后，对比对照实现与 3.0.8 的肤色区指标。"""
import os, struct, sys
sys.path.insert(0, os.path.abspath("."))
import numpy as np
from PIL import Image, ImageFilter

THIRD = os.path.join(os.path.expanduser("~"), ".workbuddy-ai/clipboard-images/clipboard-2026-10-25T06-17-22-186Z-4f596de6.jpg")
CROP  = (0, 30, 1140, 713)
FACE_W = 400

def skin_mask(a):
    Y = 0.299*a[:,:,0] + 0.587*a[:,:,1] + 0.114*a[:,:,2]
    Cr = (a[:,:,0] - Y)*0.713 + 128
    Cb = (a[:,:,2] - Y)*0.564 + 128
    return (Cr > 133) & (Cr < 178) & (Cb > 75) & (Cb < 130) & (Y > 40) & (Y < 250)

def normalize(rgb, mask):
    """按肤色 bbox 宽度归一到 FACE_W，返回 (rgb, mask)。"""
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w = x1 - x0 + 1
    s = FACE_W / float(w)
    nh, nw = int(round(rgb.shape[0]*s)), int(round(rgb.shape[1]*s))
    im = Image.fromarray(rgb.astype(np.uint8)).resize((nw, nh), Image.LANCZOS)
    mm = Image.fromarray((mask*255).astype(np.uint8)).resize((nw, nh), Image.NEAREST)
    a = np.asarray(im).astype(np.float32)
    m = np.asarray(mm) > 127
    return a, (m & skin_mask(a))

def bands(a, m):
    im = Image.fromarray(a.astype(np.uint8))
    b1 = np.asarray(im.filter(ImageFilter.BoxBlur(1))).astype(np.float32)
    b3 = np.asarray(im.filter(ImageFilter.BoxBlur(3))).astype(np.float32)
    b7 = np.asarray(im.filter(ImageFilter.BoxBlur(7))).astype(np.float32)
    Y = 0.299*a[:,:,0] + 0.587*a[:,:,1] + 0.114*a[:,:,2]
    Cr = (a[:,:,0] - Y)*0.713 + 128
    return dict(Y=float(Y[m].mean()), Cr=float(Cr[m].mean()),
                hf=float((a-b1)[m].std()), mid=float((b1-b3)[m].std()),
                low=float((b3-b7)[m].std()), n=int(m.sum()))

th = np.asarray(Image.open(THIRD).convert("RGB").crop(CROP)).astype(np.float32)
H, W, _ = th.shape
box = np.zeros((H, W), bool); box[20:600, 340:860] = True
mt = skin_mask(th) & box
thn, mtn = normalize(th, mt)
rt = bands(thn, mtn)

# 3.0.8
W2, H2 = 1074, 604
our = np.frombuffer(open("flick/wm5050/seq_011.raw","rb").read(),
                    dtype=np.uint8).reshape(H2, W2, 4)[:, :, :3].astype(np.float32)
d = open("mask_keep.raw","rb").read()
mw, mh = struct.unpack_from("<ii", d, 0); n = mw*mh
soft = np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh, mw)
ys2 = np.arange(H2)*mh//H2; xs2 = np.arange(W2)*mw//W2
mo = soft[np.ix_(ys2, xs2)] > 0
on, mon = normalize(our, mo)
ro = bands(on, mon)

print("归一脸宽 %d px 后：" % FACE_W)
print("%-10s %6s %8s %8s %8s %8s %8s" % ("", "像素", "Y", "Cr", "高频std", "中频std", "低频std"))
for name, r in (("对照实现", rt), ("3.0.8", ro)):
    print("%-10s %6d %8.2f %8.2f %8.3f %8.3f %8.3f"
          % (name, r["n"], r["Y"], r["Cr"], r["hf"], r["mid"], r["low"]))
print("%-10s %6s %8s %8s %7.2fx %7.2fx %7.2fx"
      % ("3.0.8/对照实现", "", "", "", ro["hf"]/rt["hf"], ro["mid"]/rt["mid"], ro["low"]/rt["low"]))
