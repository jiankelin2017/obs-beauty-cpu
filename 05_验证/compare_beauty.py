# -*- coding: utf-8 -*-
"""Compare two OBS preview screenshots: ours vs the third-party beauty plugin.

Uses the red selection frame to crop the video area, then reports skin-pixel
statistics. Skin is detected with a YCbCr rule so that whitened pixels are not
dropped from the sample (a plain RGB rule does exactly that).

Usage: python compare_beauty.py <ours.jpg> <theirs.jpg>
"""
import os
import sys

from PIL import Image

OUT = r"C:/legacy_e2e/out"

# preview rects found by find_frame.py
CROPS = {
    0: (12, 6, 1102, 622),   # ours (2.0.2)
    1: (0, 14, 1058, 610),   # OBS beauty camera 2.4.2
}


def rgb_to_ycbcr(r, g, b):
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return y, cb, cr


def is_skin(r, g, b):
    y, cb, cr = rgb_to_ycbcr(r, g, b)
    if y < 30:
        return False
    if not (77 <= cb <= 127):
        return False
    if not (133 <= cr <= 173):
        return False
    # drop the mustard towel: it is far more saturated than skin
    mx, mn = max(r, g, b), min(r, g, b)
    if mx > 0 and (mx - mn) / mx > 0.55:
        return False
    return True


def stats(im):
    w, h = im.size
    px = im.load()
    n = 0
    sy = ss = srb = 0.0
    ys = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y][:3]
            if not is_skin(r, g, b):
                continue
            n += 1
            yy = 0.299 * r + 0.587 * g + 0.114 * b
            ys.append(yy)
            sy += yy
            mx, mn = max(r, g, b), min(r, g, b)
            ss += 0.0 if mx == 0 else (mx - mn) / mx
            srb += r - b
    if n == 0:
        return None
    ys.sort()
    return {
        "share": 100.0 * n / (w * h),
        "luma": sy / n,
        "luma_p50": ys[n // 2],
        "luma_p90": ys[int(n * 0.9)],
        "sat": ss / n,
        "redness": srb / n,
    }


def detail(im):
    """Mean |Laplacian| on luma over skin pixels - lower means smoother."""
    w, h = im.size
    px = im.load()
    acc = 0.0
    n = 0

    def luma(x, y):
        r, g, b = px[x, y][:3]
        return 0.299 * r + 0.587 * g + 0.114 * b

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            r, g, b = px[x, y][:3]
            if not is_skin(r, g, b):
                continue
            c = luma(x, y)
            acc += abs(4 * c - luma(x - 1, y) - luma(x + 1, y)
                       - luma(x, y - 1) - luma(x, y + 1))
            n += 1
    return acc / n if n else 0.0


def main():
    paths = sys.argv[1:3]
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB").crop(CROPS[i])
        im.save(os.path.join(OUT, "cmp_%d.png" % i))
        s = stats(im)
        if s is None:
            print("no skin pixels in image %d" % i)
            return 1
        s["detail"] = detail(im)
        s["size"] = "%dx%d" % im.size
        rows.append(s)

    keys = [("luma", "平均亮度"), ("luma_p50", "亮度中位"), ("luma_p90", "亮度P90"),
            ("sat", "饱和度"), ("redness", "红润(R-B)"), ("detail", "细节能量"),
            ("share", "肤色占比%")]
    print("size: ours=%s  theirs=%s" % (rows[0]["size"], rows[1]["size"]))
    print("%-14s %12s %12s %9s %8s" % ("metric", "ours 2.0.2", "beauty 2.4.2", "diff", "ratio"))
    print("-" * 60)
    for k, name in keys:
        a, b = rows[0][k], rows[1][k]
        ratio = (b / a) if a else 0.0
        print("%-14s %12.2f %12.2f %+9.2f %8.2f" % (name, a, b, b - a, ratio))
    return 0


if __name__ == "__main__":
    sys.exit(main())
