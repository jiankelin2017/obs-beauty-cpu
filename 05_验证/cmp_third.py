# -*- coding: utf-8 -*-
"""3.0.8（磨皮50+美白50）与第三方截图（磨皮50+美白50）的肤色区指标对比。"""
import os, struct, sys
sys.path.insert(0, os.path.abspath("."))
import numpy as np
from PIL import Image, ImageFilter

THIRD = r"C:/Users/<user>/.workbuddy-ai/clipboard-images/clipboard-2026-10-25T06-17-22-186Z-4f596de6.jpg"
CROP  = (0, 30, 1140, 713)      # 预览区（右侧面板与底部黑边已切掉）

def skin_mask(a):
    Y = 0.299*a[:,:,0] + 0.587*a[:,:,1] + 0.114*a[:,:,2]
    Cr = (a[:,:,0] - Y)*0.713 + 128
    Cb = (a[:,:,2] - Y)*0.564 + 128
    return (Cr > 133) & (Cr < 178) & (Cb > 75) & (Cb < 130) & (Y > 40) & (Y < 250)

def bands(a, m):
    def std_of(x):
        v = x[m]
        return float(v.std())
    im = Image.fromarray(a.astype(np.uint8))
    b1 = np.asarray(im.filter(ImageFilter.BoxBlur(1))).astype(np.float32)
    b3 = np.asarray(im.filter(ImageFilter.BoxBlur(3))).astype(np.float32)
    b7 = np.asarray(im.filter(ImageFilter.BoxBlur(7))).astype(np.float32)
    Y = 0.299*a[:,:,0] + 0.587*a[:,:,1] + 0.114*a[:,:,2]
    Cr = (a[:,:,0] - Y)*0.713 + 128
    return dict(Y=float(Y[m].mean()), Cr=float(Cr[m].mean()),
                hf=std_of(a - b1), mid=std_of(b1 - b3), low=std_of(b3 - b7))

# ---- 第三方 ----
th = np.asarray(Image.open(THIRD).convert("RGB").crop(CROP)).astype(np.float32)
H, W, _ = th.shape
box = np.zeros((H, W), bool); box[20:600, 340:860] = True     # 人脸大致范围，排除木柜
mt = skin_mask(th) & box
ys, xs = np.nonzero(mt)
print("第三方：预览 %dx%d，肤色像素 %d，bbox x %d..%d (宽 %d) y %d..%d (高 %d)"
      % (W, H, mt.sum(), xs.min(), xs.max(), xs.max()-xs.min()+1, ys.min(), ys.max(), ys.max()-ys.min()+1))
rt = bands(th, mt)

# ---- 3.0.8 ----
W2, H2 = 1074, 604
def load_raw(p):
    return np.frombuffer(open(p, "rb").read(), dtype=np.uint8).reshape(H2, W2, 4)[:, :, :3].astype(np.float32)
d = open("mask_keep.raw", "rb").read()
mw, mh = struct.unpack_from("<ii", d, 0); n = mw*mh
soft = np.frombuffer(d[8+n:8+2*n], dtype=np.uint8).reshape(mh, mw)
ys2 = np.arange(H2)*mh//H2; xs2 = np.arange(W2)*mw//W2
mo = soft[np.ix_(ys2, xs2)] > 0
our = load_raw("flick/wm5050/seq_011.raw")
ys3, xs3 = np.nonzero(mo)
print("3.0.8：肤色像素 %d，bbox x %d..%d (宽 %d) y %d..%d (高 %d)"
      % (mo.sum(), xs3.min(), xs3.max(), xs3.max()-xs3.min()+1, ys3.min(), ys3.max(), ys3.max()-ys3.min()+1))
ro = bands(our, mo)

print()
print("%-10s %8s %8s %8s %8s %8s" % ("", "Y", "Cr", "高频std", "中频std", "低频std"))
for name, r in (("第三方", rt), ("3.0.8", ro)):
    print("%-10s %8.2f %8.2f %8.3f %8.3f %8.3f" % (name, r["Y"], r["Cr"], r["hf"], r["mid"], r["low"]))
print("%-10s %8s %8s %8.2fx %8.2fx %8.2fx"
      % ("比值", "", "", ro["hf"]/rt["hf"], ro["mid"]/rt["mid"], ro["low"]/rt["low"]))
