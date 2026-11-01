# -*- coding: utf-8 -*-
"""四联对比：原始 / 产品 / 3.1.18(T8.3,e0.7) / 3.1.19(T6.5,e0.95)。"""
import os
import sys
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R

W, H = 1920, 1080
WORK = R.WORK
OUT = r'C:\btwork\live_check'
TAG = sys.argv[1] if len(sys.argv) > 1 else 'm00'
HERE = os.path.dirname(os.path.abspath(__file__))

WORKER = r'''
import os, sys
for k in list(os.environ):
    if k.startswith('BEAUTY_'): del os.environ[k]
os.environ['BEAUTY_SMOOTH_MODEL']='surface3'
os.environ['BEAUTY_S3_BAND']='1'
if os.environ.get('SET_T'):
    os.environ['BEAUTY_S3_LV_T'] = ','.join([os.environ['SET_T']]*5)
    os.environ['BEAUTY_S3_LV_E'] = ','.join([os.environ['SET_E']]*5)
sys.path.insert(0, r'D:\插件\OBS美颜\06_离线验证')
import real_frame_eval as R
raw, out = sys.argv[1], sys.argv[2]
R.run_core(raw, out, 1920, 1080, 100.0)
print('OK', out)
'''

raw_in = os.path.join(WORK, '%s_in.raw' % TAG)
src = R.load_raw(raw_in, W, H)
gold = R.load_raw(R.gold_path(TAG, -1), W, H)

variants = [('v318', '8.3', '0.70'), ('v319', '6.5', '0.95')]
paths = {}
for name, T, E in variants:
    outp = os.path.join(OUT, 'ab4_%s_%s.raw' % (TAG, name))
    env = dict(os.environ)
    env.update({'SET_T': T, 'SET_E': E, 'PYTHONIOENCODING': 'utf-8'})
    r = subprocess.run([sys.executable, '-c', WORKER, raw_in, outp],
                       capture_output=True, text=True, env=env,
                       encoding='utf-8', errors='replace')
    if not os.path.exists(outp):
        print(name, 'FAILED', (r.stderr or '')[-300:])
        sys.exit(1)
    paths[name] = R.load_raw(outp, W, H)

mask = R.upscale_mask(R.read_mask(os.path.join(WORK, '%s_fuai.mask' % TAG)), W, H)
ys, xs = np.where(mask)
x0, x1 = max(xs.min() - 40, 0), min(xs.max() + 40, W)
y0, y1 = max(ys.min() - 60, 0), min(ys.max() + 40, H)

FONT = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20)
imgs = [src, gold, paths['v318'], paths['v319']]
TITLES = ['原始（关滤镜）', '产品 SDK 100', 'v3.1.18  T8.3 e0.70', 'v3.1.19  T6.5 e0.95']

th = 500
w0 = int((x1 - x0) * th / (y1 - y0))
pad, lh = 8, 30
canvas = Image.new('RGB', (w0 * 4 + pad * 5, th + lh + pad * 2), (24, 24, 24))
for i, a in enumerate(imgs):
    im = Image.fromarray(np.asarray(a[y0:y1, x0:x1, :3]).astype(np.uint8)).resize(
        (w0, th), Image.LANCZOS)
    canvas.paste(im, (pad + i * (w0 + pad), lh + pad))
d = ImageDraw.Draw(canvas)
for i, t in enumerate(TITLES):
    d.text((pad + i * (w0 + pad) + 6, 5), t, fill=(235, 235, 235), font=FONT)
p = os.path.join(OUT, 'ab4_%s_full.png' % TAG)
canvas.save(p)
print('saved', p, canvas.size)

# 法令纹/眼下区域放大（脸中线偏左，鼻翼上方）
bw = int((x1 - x0) * 0.22)
bh = int(bw * 0.85)
cx = x0 + int((x1 - x0) * 0.40)
cy = y0 + int((y1 - y0) * 0.50)
box = (max(cx - bw // 2, 0), max(cy - bh // 2, 0),
       min(cx + bw // 2, W), min(cy + bh // 2, H))
sc = 3.0
canvas2 = None
ims = []
for a in imgs:
    im = Image.fromarray(np.asarray(a[box[1]:box[3], box[0]:box[2], :3]).astype(np.uint8))
    ims.append(im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS))
w1, h1 = ims[0].size
canvas2 = Image.new('RGB', (w1 * 4 + pad * 5, h1 + lh + pad * 2), (24, 24, 24))
for i, im in enumerate(ims):
    canvas2.paste(im, (pad + i * (w1 + pad), lh + pad))
d = ImageDraw.Draw(canvas2)
for i, t in enumerate(['原始', '产品 SDK', 'v3.1.18', 'v3.1.19']):
    d.text((pad + i * (w1 + pad) + 6, 5), t, fill=(235, 235, 235), font=FONT)
p2 = os.path.join(OUT, 'ab4_%s_zoom.png' % TAG)
canvas2.save(p2)
print('saved', p2, canvas2.size, 'box', box)
