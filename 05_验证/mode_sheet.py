# -*- coding: utf-8 -*-
"""把指定 tag 的输出帧裁出同一块脸区，拼成对比图（含 3 倍放大）。"""
import os
import sys

import numpy as np
from PIL import Image

HERE = r'C:\legacy_e2e'
W, H = 1074, 604
OUT = os.path.join(HERE, 'out', 'mode_cmp')


def frame(tag, idx=5):
    d = os.path.join(HERE, 'flick', 'nz_%s_out' % tag)
    f = os.path.join(d, 'seq_%03d.raw' % idx)
    a = np.frombuffer(open(f, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return Image.fromarray(a[:, :, 2::-1])      # BGRA -> RGB


def main():
    tags = sys.argv[1:] or ['md_m0']
    os.makedirs(OUT, exist_ok=True)
    box = (390, 190, 650, 450)                   # 脸中下部：含眼镜框/鼻翼/脸颊
    tiles = []
    for t in tags:
        try:
            im = frame(t).crop(box)
        except FileNotFoundError:
            print('skip', t)
            continue
        tiles.append((t, im))
    if not tiles:
        return
    w, h = tiles[0][1].size
    sheet = Image.new('RGB', (w * len(tiles), h * 2 + 24), (20, 20, 20))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(tiles):
        sheet.paste(im, (i * w, 24))
        sheet.paste(im.resize((w * 2, h * 2), Image.NEAREST).crop((0, 0, w, h)),
                    (i * w, 24 + h))
        dr.text((i * w + 6, 6), t, fill=(255, 255, 255))
    p = os.path.join(OUT, 'mode_sheet.png')
    sheet.save(p)
    print('saved', p)


if __name__ == '__main__':
    main()
