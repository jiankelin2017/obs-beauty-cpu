# -*- coding: utf-8 -*-
"""把 src / 产品金标 / 自研引擎 三方拼成一张对比图（脸部裁切 + 局部放大）。"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
WORK = R.WORK
OUT = r'C:\btwork\live_check'
tag = sys.argv[1] if len(sys.argv) > 1 else 'm00'

src = R.load_raw(os.path.join(WORK, '%s_in.raw' % tag), W, H)
gold = R.load_raw(R.gold_path(tag, -1), W, H)
our = R.load_raw(os.path.join(WORK, '_ft_%s.raw' % tag), W, H)
mask = R.upscale_mask(R.read_mask(os.path.join(WORK, '%s_fuai.mask' % tag)), W, H)

ys, xs = np.where(mask)
x0, x1 = max(xs.min() - 40, 0), min(xs.max() + 40, W)
y0, y1 = max(ys.min() - 60, 0), min(ys.max() + 40, H)
print('face bbox', x0, y0, x1, y1)


def crop(a, box):
    return a[box[1]:box[3], box[0]:box[2], :3]


box = (x0, y0, x1, y1)
imgs = [crop(src, box), crop(gold, box), crop(our, box)]
th = 520
w0 = int(imgs[0].shape[1] * th / imgs[0].shape[0])
row = [Image.fromarray(np.asarray(im).astype(np.uint8)).resize((w0, th), Image.LANCZOS) for im in imgs]
pad = 10
label_h = 34
canvas = Image.new('RGB', (w0 * 3 + pad * 4, th + label_h + pad * 2), (24, 24, 24))
for i, im in enumerate(row):
    canvas.paste(im, (pad + i * (w0 + pad), label_h + pad))
d = ImageDraw.Draw(canvas)
try:
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 22)
except Exception:
    font = ImageFont.load_default()
for i, t in enumerate(['原始（关滤镜）', '产品 SDK 金标 blur=100', '我们 v3.1.17 blur=100']):
    d.text((pad + i * (w0 + pad) + 8, 6), t, fill=(235, 235, 235), font=font)
p1 = os.path.join(OUT, 'ab_%s_full.png' % tag)
canvas.save(p1)
print('saved', p1, canvas.size)

# 局部放大：取脸颊一块固定纹理区
cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
px, py, pw, ph = cx - 110, cy - 40, 220, 220
zoom = []
for im in imgs:
    # imgs 是 box 裁后的图
    zx, zy = px - box[0], py - box[1]
    patch = im[max(zy, 0):max(zy, 0) + ph, max(zx, 0):max(zx, 0) + pw]
    zoom.append(Image.fromarray(np.asarray(patch).astype(np.uint8)).resize((440, 440), Image.NEAREST))
c2 = Image.new('RGB', (440 * 3 + pad * 4, 440 + label_h + pad * 2), (24, 24, 24))
for i, im in enumerate(zoom):
    c2.paste(im, (pad + i * (440 + pad), label_h + pad))
d2 = ImageDraw.Draw(c2)
for i, t in enumerate(['原始', '产品 SDK', '我们']):
    d2.text((pad + i * (440 + pad) + 8, 6), t, fill=(235, 235, 235), font=font)
p2 = os.path.join(OUT, 'ab_%s_zoom.png' % tag)
c2.save(p2)
print('saved', p2, c2.size)
