# -*- coding: utf-8 -*-
"""滑杆曲线对比 v2：用「肤色区细节 ÷ 非肤色背景细节」做曝光归一化。

现场光照/自动曝光会漂移（实测无滤镜帧之间 luma 会跳 19 级），任何绝对细节量都会被它带偏。
磨皮只改肤色区、不改背景，所以拿同一帧的背景当内参可以把这个漂移抵掉。
"""
import os
import numpy as np
import cv2

CLIP = r'C:\Users\<user>\.workbuddy\clipboard-images'
SWEEP = r'C:\btwork\live_check\sweep'

USER = {
    'sdk': {0: 'clipboard-2026-10-29T19-15-22-107Z-3e4159f1.jpg',
            25: 'clipboard-2026-10-29T19-15-22-105Z-bffee012.jpg',
            50: 'clipboard-2026-10-29T19-15-22-103Z-de0b9954.jpg',
            75: 'clipboard-2026-10-29T19-15-22-102Z-30b35884.jpg',
            100: 'clipboard-2026-10-29T19-15-22-101Z-2740d23a.jpg'},
    'ours': {0: 'clipboard-2026-10-29T19-15-22-098Z-01b07f31.jpg',
             25: 'clipboard-2026-10-29T19-15-22-112Z-49b61361.jpg',
             50: 'clipboard-2026-10-29T19-15-22-111Z-a865bbbf.jpg',
             75: 'clipboard-2026-10-29T19-15-22-109Z-dc3c5d26.jpg',
             100: 'clipboard-2026-10-29T19-15-22-109Z-ec847ba0.jpg'},
}


def face_mask(bgr):
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    m = ((cr > 133) & (cr < 178) & (cb > 74) & (cb < 130) & (y > 45)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        m = (lab == k).astype(np.uint8)
    return cv2.erode(m, np.ones((11, 11), np.uint8))


def metrics(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lap = np.abs(cv2.Laplacian(g, cv2.CV_32F, ksize=3))
    mid = np.abs(g - cv2.GaussianBlur(g, (0, 0), 7.0))
    m = face_mask(bgr)
    face = m > 0
    # 背景参考：把脸的外接矩形放大 40% 挖掉，剩下的当内参
    ys, xs = np.where(face)
    if len(ys) == 0:
        return None
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    h, w = g.shape
    py, px = int((y1 - y0) * 0.2), int((x1 - x0) * 0.2)
    bg = np.ones_like(g, np.uint8)
    bg[max(y0 - py, 0):min(y1 + py, h), max(x0 - px, 0):min(x1 + px, w)] = 0
    # 只取有结构的中频足够多的区域（避开纯白墙/纯黑阴影）
    bgm = (bg > 0) & (lap > 0.5)
    return dict(detail=float(lap[face].mean()),
                midfreq=float(mid[face].mean()),
                bg_detail=float(lap[bgm].mean()) if bgm.sum() > 5000 else float('nan'),
                bg_mid=float(mid[bgm].mean()) if bgm.sum() > 5000 else float('nan'),
                luma=float(g[face].mean()),
                face_px=int(face.sum()))


def report(title, items):
    print('\n== %s ==' % title)
    print('%-6s %8s %8s %8s %9s %9s %8s' %
          ('level', 'detail', 'bg', 'd/bg', 'norm_ret', 'mid/bg', 'luma'))
    base = None
    for lv in sorted(items):
        m = items[lv]
        if m is None:
            print('%-6d  检测失败' % lv)
            continue
        d_bg = m['detail'] / m['bg_detail']
        mid_bg = m['midfreq'] / m['bg_mid']
        if base is None:
            base = (d_bg, mid_bg)
        print('%-6d %8.3f %8.3f %8.4f %9.3f %9.4f %8.2f' %
              (lv, m['detail'], m['bg_detail'], d_bg, d_bg / base[0], mid_bg, m['luma']))
    return base


def main():
    for fam in ('sdk', 'ours'):
        items = {}
        for lv, fn in USER[fam].items():
            im = cv2.imread(os.path.join(CLIP, fn))
            items[lv] = metrics(im)
        report('用户截图 %s（曝光归一化）' % fam.upper(), items)

    items = {}
    for lv in (0, 25, 50, 75, 100):
        p = os.path.join(SWEEP, 'ours_%03d.png' % lv)
        if os.path.exists(p):
            items[lv] = metrics(cv2.imread(p))
    report('我方 OBS 现场扫描（曝光归一化）', items)


if __name__ == '__main__':
    main()
