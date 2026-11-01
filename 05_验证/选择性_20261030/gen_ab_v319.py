# -*- coding: utf-8 -*-
"""生成 v3.1.19（T=6.5/e=0.95）与产品金标的三方对比图：全脸 + 脸颊 2x 放大。"""
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
WORK = R.WORK
OUT = r'C:\btwork\live_check'
TAG = sys.argv[1] if len(sys.argv) > 1 else 'm00'

for k in list(os.environ):
    if k.startswith('BEAUTY_'):
        del os.environ[k]
os.environ['BEAUTY_SMOOTH_MODEL'] = 'surface3'
os.environ['BEAUTY_S3_BAND'] = '1'

src = R.load_raw(os.path.join(WORK, '%s_in.raw' % TAG), W, H)
gold = R.load_raw(R.gold_path(TAG, -1), W, H)
raw_in = os.path.join(WORK, '%s_in.raw' % TAG)
our_path = os.path.join(OUT, 'ab_v319_%s.raw' % TAG)
R.run_core(raw_in, our_path, W, H, 100.0)
our = R.load_raw(our_path, W, H)
mask = R.upscale_mask(R.read_mask(os.path.join(WORK, '%s_fuai.mask' % TAG)), W, H)

ys, xs = np.where(mask)
x0, x1 = max(xs.min() - 40, 0), min(xs.max() + 40, W)
y0, y1 = max(ys.min() - 60, 0), min(ys.max() + 40, H)
print('face bbox', x0, y0, x1, y1)

FONT = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 22)
FONT_S = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)


def montage(box, titles, out_name, scale=1, th=520):
    imgs = [a[box[1]:box[3], box[0]:box[2], :3] for a in (src, gold, our)]
    if scale != 1:
        imgs = [np.asarray(Image.fromarray(np.asarray(im).astype(np.uint8))
                           .resize((int(im.shape[1] * scale), int(im.shape[0] * scale)),
                                   Image.LANCZOS)) for im in imgs]
        th = imgs[0].shape[0]
    w0 = int(imgs[0].shape[1] * th / imgs[0].shape[0])
    row = [Image.fromarray(np.asarray(im).astype(np.uint8)).resize((w0, th), Image.LANCZOS)
           for im in imgs]
    pad, lh = 10, 34
    canvas = Image.new('RGB', (w0 * 3 + pad * 4, th + lh + pad * 2), (24, 24, 24))
    for i, im in enumerate(row):
        canvas.paste(im, (pad + i * (w0 + pad), lh + pad))
    d = ImageDraw.Draw(canvas)
    for i, t in enumerate(titles):
        d.text((pad + i * (w0 + pad) + 8, 6), t, fill=(235, 235, 235), font=FONT)
    p = os.path.join(OUT, out_name)
    canvas.save(p)
    print('saved', p, canvas.size)


TITLES = ['原始（关滤镜）', '产品 SDK blur=100', 'v3.1.19 blur=100']

# 全脸
montage((x0, y0, x1, y1), TITLES, 'ab_v319_%s_full.png' % TAG, scale=1, th=520)

# 脸颊放大：取 mask 左半侧（脸颊通常在这），2x
bw = int((x1 - x0) * 0.20)
bh = int(bw * 0.80)
cx = x1 - int((x1 - x0) * 0.26)      # 右脸颊
cy = y0 + int((y1 - y0) * 0.46)
box = (max(cx - bw // 2, 0), max(cy - bh // 2, 0),
       min(cx + bw // 2, W), min(cy + bh // 2, H))
print('zoom box', box)
montage(box, TITLES, 'ab_v319_%s_zoom.png' % TAG, scale=3.2)
