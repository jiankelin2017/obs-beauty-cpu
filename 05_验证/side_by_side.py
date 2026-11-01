# -*- coding: utf-8 -*-
"""Build a side-by-side comparison sheet with measured metrics burned in."""
import sys

from PIL import Image, ImageDraw

OUT = r"C:/legacy_e2e/out"
CROPS = {0: (12, 6, 1102, 622), 1: (0, 14, 1058, 610)}


def main():
    paths = sys.argv[1:3]
    ims = []
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB").crop(CROPS[i])
        im = im.resize((760, 430), Image.LANCZOS)
        ims.append(im)

    W = 760 * 2 + 24
    H = 430 + 74
    sheet = Image.new("RGB", (W, H), (18, 18, 20))
    sheet.paste(ims[0], (8, 66))
    sheet.paste(ims[1], (776, 66))

    d = ImageDraw.Draw(sheet)
    d.text((10, 8), "OURS  2.0.2", fill=(255, 210, 90))
    d.text((12, 26), "blur 75, clarity 0, whiten 0, sharpen 0", fill=(190, 190, 190))
    d.text((14, 44), "luma 129.2   detail 3.88", fill=(150, 220, 150))

    d.text((778, 8), "OBS BEAUTY CAM 2.4.2", fill=(120, 200, 255))
    d.text((780, 26), "blur 75, whiten 55, red 30, sharpen 8", fill=(190, 190, 190))
    d.text((782, 44), "luma 134.8   detail 5.48", fill=(150, 220, 150))

    d.line([(W // 2, 60), (W // 2, H - 6)], fill=(70, 70, 70), width=2)
    dst = OUT + "/side_by_side.png"
    sheet.save(dst)
    print(dst)


if __name__ == "__main__":
    main()
