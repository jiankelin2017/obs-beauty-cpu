# -*- coding: utf-8 -*-
"""Locate the red selection frame in an OBS screenshot and crop the video area."""
import sys

from PIL import Image

OUT = r"C:/legacy_e2e/out"


def is_red(p):
    r, g, b = p[:3]
    return r > 170 and g < 90 and b < 90


def find_frame(im):
    w, h = im.size
    px = im.load()
    # scan the left half only: the properties panel is on the right
    xmax = int(w * 0.68)
    ymax = int(h * 0.72)

    cols = {}
    rows = {}
    for y in range(0, ymax, 2):
        for x in range(0, xmax, 2):
            if is_red(px[x, y]):
                cols[x] = cols.get(x, 0) + 1
                rows[y] = rows.get(y, 0) + 1
    if not cols or not rows:
        return None
    # the frame edges are the columns/rows with many red pixels
    cx = sorted(cols.items(), key=lambda kv: -kv[1])[:8]
    ry = sorted(rows.items(), key=lambda kv: -kv[1])[:8]
    xs = sorted(x for x, c in cx if c > 5)
    ys = sorted(y for y, c in ry if c > 5)
    if not xs or not ys:
        return None
    return (xs[0], ys[0], xs[-1], ys[-1])


def main():
    for i, p in enumerate(sys.argv[1:3]):
        im = Image.open(p).convert("RGB")
        box = find_frame(im)
        print("%d size=%s frame=%s" % (i, im.size, box))
        if box:
            im.crop(box).save("%s/frame_%d.png" % (OUT, i))


if __name__ == "__main__":
    main()
