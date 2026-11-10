# -*- coding: utf-8 -*-
"""3.0.9（磨皮50+美白50）与对照实现 2.4.2（磨皮50+美白50+锐化8）对比。

脸宽不同（自制 255 px / 对照实现 210 px），固定像素带宽会失真，
因此同时给三种口径：原生、归一到 210（只缩不放）、归一到 400。
"""
import os
import numpy as np
from PIL import Image, ImageFilter

OURS = os.path.join(os.path.expanduser("~"), ".workbuddy-ai/clipboard-images/clipboard-2026-10-25T08-55-18-506Z-2220bebf.jpg")
THRD = os.path.join(os.path.expanduser("~"), ".workbuddy-ai/clipboard-images/clipboard-2026-10-25T08-55-18-507Z-7ed7adbf.jpg")
BOX_O = (565, 195, 820, 430)
BOX_T = (440, 190, 650, 400)

def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
def luma(a): return 0.299*a[:,:,0]+0.587*a[:,:,1]+0.114*a[:,:,2]
def cr(a):   return (a[:,:,0]-luma(a))*0.713+128
def cb(a):   return (a[:,:,2]-luma(a))*0.564+128
def skin(a):
    Y, R, B = luma(a), cr(a), cb(a)
    return (R>133)&(R<178)&(B>75)&(B<130)&(Y>40)&(Y<250)

def region(a, box):
    x0, y0, x1, y1 = box
    m = np.zeros(a.shape[:2], bool)
    m[y0:y1, x0:x1] = True
    return m & skin(a), (x0, y0, x1, y1)

def crop(a, m, box):
    x0, y0, x1, y1 = box
    return a[y0:y1, x0:x1], m[y0:y1, x0:x1]

def resize(a, m, fw):
    ys, xs = np.nonzero(m)
    w = xs.max()-xs.min()+1
    s = fw/float(w)
    nh, nw = int(round(a.shape[0]*s)), int(round(a.shape[1]*s))
    b = np.asarray(Image.fromarray(a.astype(np.uint8)).resize((nw, nh), Image.LANCZOS)).astype(np.float32)
    mb = np.asarray(Image.fromarray((m*255).astype(np.uint8)).resize((nw, nh), Image.NEAREST)) > 127
    return b, (mb & skin(b))

def stats(b, mb):
    im = Image.fromarray(b.astype(np.uint8))
    b1 = np.asarray(im.filter(ImageFilter.BoxBlur(1))).astype(np.float32)
    b3 = np.asarray(im.filter(ImageFilter.BoxBlur(3))).astype(np.float32)
    b7 = np.asarray(im.filter(ImageFilter.BoxBlur(7))).astype(np.float32)
    return dict(Y=float(luma(b)[mb].mean()), Cr=float(cr(b)[mb].mean()),
                hf=float((b-b1)[mb].std()), mid=float((b1-b3)[mb].std()),
                low=float((b3-b7)[mb].std()), n=int(mb.sum()))

ao, at = load(OURS), load(THRD)
mo, bo = region(ao, BOX_O); mt, bt = region(at, BOX_T)
co, cmo = crop(ao, mo, BOX_O); ct, cmt = crop(at, mt, BOX_T)

print("人脸宽度：自制 %d px，对照实现 %d px（比 %.2f）\n"
      % (bo[2]-bo[0], bt[2]-bt[0], (bo[2]-bo[0])/float(bt[2]-bt[0])))

for label, fw in (("原生（不缩放）", None), ("归一到 210 px", 210), ("归一到 400 px", 400)):
    if fw is None:
        po, pmo = co, cmo
        pt, pmt = ct, cmt
    else:
        po, pmo = resize(co, cmo, fw)
        pt, pmt = resize(ct, cmt, fw)
    ro, rt = stats(po, pmo), stats(pt, pmt)
    print("[%s]" % label)
    print("  %-9s %6s %7s %7s %8s %8s %8s" % ("", "像素", "Y", "Cr", "高频", "中频", "低频"))
    print("  %-9s %6d %7.2f %7.2f %8.3f %8.3f %8.3f" % ("自制", ro["n"], ro["Y"], ro["Cr"], ro["hf"], ro["mid"], ro["low"]))
    print("  %-9s %6d %7.2f %7.2f %8.3f %8.3f %8.3f" % ("对照实现", rt["n"], rt["Y"], rt["Cr"], rt["hf"], rt["mid"], rt["low"]))
    print("  %-9s %6s %+7.2f %+7.2f %7.2fx %7.2fx %7.2fx\n"
          % ("自制/对照实现", "", ro["Y"]-rt["Y"], ro["Cr"]-rt["Cr"],
             ro["hf"]/rt["hf"], ro["mid"]/rt["mid"], ro["low"]/rt["low"]))
