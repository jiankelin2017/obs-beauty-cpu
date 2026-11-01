# -*- coding: utf-8 -*-
"""档位曲线三方对比图：产品真值 / 旧映射（I 饱和）/ 新映射（查表）。"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

LV = [0, 25, 50, 75, 100]
SDK = [0.000, 0.010, 0.403, 1.121, 1.901]
OLD = [0.000, 0.459, 1.125, 1.963, 1.963]
NEW = [0.000, 0.000, 0.423, 1.118, 1.915]

OUT = r'D:\插件\OBS美颜\06_离线验证\档位曲线_20261030'
os.makedirs(OUT, exist_ok=True)

W, H = 1020, 620
L, R, T, B = 105, 175, 78, 88
im = Image.new('RGB', (W, H), (255, 255, 255))
d = ImageDraw.Draw(im)
FS = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16)
FB = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 22)
YMAX = 2.15
X = lambda v: L + (W - L - R) * (v / 100.0)
Y = lambda v: H - B - (H - T - B) * (v / YMAX)

for v in [0, 0.5, 1.0, 1.5, 2.0]:
    d.line([(L, Y(v)), (W - R, Y(v))], fill=(232, 232, 232))
    d.text((L - 52, Y(v) - 9), '%.1f' % v, font=FS, fill=(95, 95, 95))
for v in LV:
    d.line([(X(v), T), (X(v), H - B)], fill=(240, 240, 240))
    d.text((X(v) - 10, H - B + 10), str(v), font=FS, fill=(95, 95, 95))
d.line([(L, H - B), (W - R, H - B)], fill=(70, 70, 70), width=2)
d.line([(L, T), (L, H - B)], fill=(70, 70, 70), width=2)

C_SDK, C_OLD, C_NEW = (31, 119, 180), (150, 150, 150), (214, 39, 40)


def plot(ys, color, width=3, dash=False):
    pts = [(X(x), Y(y)) for x, y in zip(LV, ys)]
    if dash:
        for a, b in zip(pts[:-1], pts[1:]):
            n = 12
            for i in range(0, n, 2):
                p0 = (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
                p1 = (a[0] + (b[0] - a[0]) * (i + 1) / n, a[1] + (b[1] - a[1]) * (i + 1) / n)
                d.line([p0, p1], fill=color, width=width)
    else:
        d.line(pts, fill=color, width=width)
    for p in pts:
        d.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], fill=color,
                  outline=(255, 255, 255))
    return pts


p_old = plot(OLD, C_OLD, 3, dash=True)
p_sdk = plot(SDK, C_SDK, 4)
p_new = plot(NEW, C_NEW, 4)

d.text((L, T - 52), '磨皮档位 → 肤色区改动量（8 帧真机均值，同帧离线）', font=FB, fill=(25, 25, 25))

# 右侧标签（避开折线）
d.text((p_old[-1][0] + 14, p_old[-1][1] - 26), '旧映射 v3.1.17', font=FS, fill=(120, 120, 120))
d.text((p_new[-1][0] + 14, p_new[-1][1] + 6), '新映射 v3.1.18', font=FS, fill=(200, 30, 30))
d.text((p_sdk[-1][0] + 14, p_sdk[-1][1] + 34), '产品 SDK 真值', font=FS, fill=(20, 100, 160))

# 注释
# 注释放在左上空白区（数据在 0–25 档几乎贴底，那块区域是空的）
d.text((L + 14, Y(2.06) - 10), '旧：25 档就磨到 0.459（产品 0.010，46 倍）', font=FS, fill=(110, 110, 110))
d.text((L + 14, Y(1.90) - 10), '旧：75/100 输出逐字节相同（死区）', font=FS, fill=(110, 110, 110))

d.text((L, H - 34), '横轴：面板磨皮档位 0–100　　纵轴：肤色掩码内平均 |Δ|（0 = 完全不变）',
       font=FS, fill=(110, 110, 110))

p = os.path.join(OUT, 'curve_v318.png')
im.save(p)
json.dump({'level': LV, 'sdk': SDK, 'old': OLD, 'new': NEW},
          open(os.path.join(OUT, 'curve_v318.json'), 'w'), indent=1)
print(p)
