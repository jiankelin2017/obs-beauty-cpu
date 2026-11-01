# detail_test.py —— 锐化 / 全局锐化（细节回填）的验收测量
#
# 对应实现：beauty_smooth.cpp 的 detailRefill()，CoreEngine 0.6 起接入
#   hFine = Y(src) - box3(Y(src))     细频带（1~2px：毛孔、睫毛、发丝）
#   hMid  = box3 - box7               中频带（3~7px：轮廓过渡、皮肤结构）
#   dst  += w·(fine·hFine + mid·hMid)
#
# 为什么要测「相对原图的百分比」而不是绝对差：
#   磨皮本身会把细频带压下去（这是它的工作）。锐化的意义是「把磨掉的那一段
#   按滑块比例放回去」，所以唯一有意义的读数是「当前细频带能量 ÷ 原图细频带
#   能量」。磨皮 50 单独跑应该明显低于 100%，锐化 100 时应该回到 100% 以上。
#
# 判据（写死，不达标就是没做完）：
#   1. 全局锐化 = 0 时，掩码外必须 **逐字节不变**（这是产品承诺，不是指标）
#   2. 磨皮 50 + 锐化 100 的细频带 ≥ 磨皮 50 + 锐化 0 的 1.3 倍
#   3. 磨皮=0 时「锐化」无效、「全局锐化」仍生效（与 SDK 路线的门控一致）
#   4. 1080p 增量 ≤ 2.5 ms（全局锐化开）/ ≤ 1.0 ms（只开脸内锐化）

import ctypes
import os
import struct
import sys
import time

import numpy as np

import low_path_test as L

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = L.DLL
RES = L.RES
OUT = L.OUT
FACE = L.FACE


def load_mask(path, w, h):
    with open(path, 'rb') as f:
        mw, mh = struct.unpack('<ii', f.read(8))
        buf = f.read(mw * mh)
    if (mw, mh) != (w, h):
        return None
    return np.frombuffer(buf, dtype=np.uint8).reshape((mh, mw))


def box(a, r):
    """可分离盒式滤波（float64），边界复制。用于在 Python 侧复刻引擎的频带定义。"""
    h, w = a.shape
    k = 2 * r + 1
    p = np.pad(a, ((0, 0), (r, r)), mode='edge')
    c = np.cumsum(p, axis=1, dtype=np.float64)
    c = np.concatenate([np.zeros((h, 1)), c], axis=1)
    h1 = (c[:, k:] - c[:, :-k]) / k
    p2 = np.pad(h1, ((r, r), (0, 0)), mode='edge')
    c2 = np.cumsum(p2, axis=0, dtype=np.float64)
    c2 = np.concatenate([np.zeros((1, w)), c2], axis=0)
    return (c2[k:, :] - c2[:-k, :]) / k


def luma(img):
    a = img[:, :, :3].astype(np.float32)
    return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]


def bands(img):
    """返回 (细频带能量, 中频带能量)，都是「Y 平面上的绝对均值」。"""
    y = luma(img)
    b3 = box(y, 1)
    b7 = box(y, 3)
    return np.abs(y - b3), np.abs(b3 - b7)


def main():
    if not os.path.exists(DLL):
        print('[detail] missing %s' % DLL)
        return 2
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetDetail.argtypes = [ctypes.c_double, ctypes.c_double]
    dll.BeautyCoreSetFreq.argtypes = [ctypes.c_int, ctypes.c_float,
                                      ctypes.c_float, ctypes.c_float]
    dll.BeautyCoreSetLowPath.argtypes = [ctypes.c_int, ctypes.c_int]
    dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreMask.restype = ctypes.c_int

    os.makedirs(OUT, exist_ok=True)
    W, H = 640, 394
    raw = os.path.join(RES, '640x394.raw')
    tmp = os.path.join(OUT, '_dt.raw')
    maskp = os.path.join(OUT, '_dt.mask')
    src = L.load(raw, W, H)

    msg = ctypes.create_string_buffer(512)
    mask = None
    if dll.BeautyCoreMask(raw.encode(), W, H, maskp.encode(), msg, 512) == 0:
        mask = load_mask(maskp, W, H)

    # 区域：脸内用 YuNet 框；脸外（背景）取「掩码外」的全部像素
    inside = np.zeros((H, W), bool)
    x0, x1, y0, y1 = FACE
    inside[y0:y1, x0:x1] = True
    if mask is not None:
        inside = inside & (mask > 0)
        outside = (mask == 0)
    else:
        outside = ~inside

    f_src, m_src = bands(src)
    ref_f = float(f_src[inside].mean())
    ref_m = float(m_src[inside].mean())
    ref_f_out = float(f_src[outside].mean())
    print('[detail] 原图参考：脸内细 %.4f 中 %.4f / 脸外细 %.4f' %
          (ref_f, ref_m, ref_f_out))

    dll.BeautyCoreSetFreq(1, 2.0, 6.0, 30.0)
    dll.BeautyCoreSetLowPath(0, 8)
    dll.BeautyCoreSetClarityPanel(0.0)

    def run(blur, face_sharp, global_sharp, path=raw, w=W, h=H, warm=3, rep=5):
        dll.BeautyCoreSetDetail(face_sharp, global_sharp)

        def once():
            msg = ctypes.create_string_buffer(512)
            dll.BeautyCoreRun(path.encode(), tmp.encode(), w, h, blur, 0,
                              0.0, 0.0, 1, msg, 512)
            # 只认引擎自报的 ms=，不认 wall clock。
            # 1080p 每帧要读写 8MB，文件 I/O 会稳定污染 15ms 以上 —— C10 就因为
            # 用 wall clock 得出了「异步反而更差」的错误结论。这个坑不要再踩。
            txt = msg.value.decode('ascii', 'replace')
            for tok in txt.split():
                if tok.startswith('ms='):
                    return float(tok[3:])
            return float('nan')

        for _ in range(warm):
            once()
        best = 1e9
        for _ in range(rep):
            v = once()
            if v == v:
                best = min(best, v)
        return L.load(tmp, w, h), best

    rows = []
    print()
    print('%-22s %8s %8s %8s %10s %8s'
          % ('配置', '脸内细%', '脸内中%', '脸外细%', '背景改动', 'ms'))
    for face_sharp in (0.0, 25.0, 50.0, 100.0):
        img, ms = run(50.0, face_sharp, 0.0)
        f, m = bands(img)
        pf = 100.0 * float(f[inside].mean()) / ref_f
        pm = 100.0 * float(m[inside].mean()) / ref_m
        pfo = 100.0 * float(f[outside].mean()) / ref_f_out
        bg = int(np.any(img[outside] != src[outside], axis=1).sum())
        name = '磨皮50 锐化%d' % face_sharp
        rows.append((name, pf, pm, pfo, bg, ms))
        print('%-22s %8.1f %8.1f %8.1f %10d %8.2f'
              % (name, pf, pm, pfo, bg, ms))

    base50, _ = run(50.0, 0.0, 0.0, rep=1)
    for g in (50.0, 100.0):
        img, ms = run(50.0, 0.0, g)
        f, m = bands(img)
        pf = 100.0 * float(f[inside].mean()) / ref_f
        pm = 100.0 * float(m[inside].mean()) / ref_m
        pfo = 100.0 * float(f[outside].mean()) / ref_f_out
        bg = int(np.any(img[outside] != base50[outside], axis=1).sum())
        name = '磨皮50 全局%d' % g
        rows.append((name, pf, pm, pfo, bg, ms))
        print('%-22s %8.1f %8.1f %8.1f %10d %8.2f'
              % (name, pf, pm, pfo, bg, ms))

    # 磨皮 = 0：脸内锐化应无效，全局锐化仍生效
    zero0, _ = run(0.0, 0.0, 0.0, rep=1)
    img, _ = run(0.0, 100.0, 0.0)
    d_face = int(np.any(img != zero0, axis=2).sum())
    img, _ = run(0.0, 0.0, 100.0)
    d_glob = int(np.any(img != zero0, axis=2).sum())
    print()
    print('[detail] 磨皮=0：锐化100 改动像素 %d（要求 0）/ 全局100 改动像素 %d（要求 >0）'
          % (d_face, d_glob))

    # 1080p 计时
    t_face = t_glob = None
    p1080 = os.path.join(RES, '1080p.raw')
    if os.path.exists(p1080):
        _, t_face = run(50.0, 100.0, 0.0, path=p1080, w=1920, h=1080, rep=5)
        _, t_glob = run(50.0, 0.0, 100.0, path=p1080, w=1920, h=1080, rep=5)
        _, t_base = run(50.0, 0.0, 0.0, path=p1080, w=1920, h=1080, rep=5)
        print('[detail] 1080p：基准 %.2f ms / 脸内锐化100 %.2f ms (+%.2f) / '
              '全局100 %.2f ms (+%.2f)'
              % (t_base, t_face, t_face - t_base, t_glob, t_glob - t_base))

    md = ['# 锐化 / 全局锐化 验收测量\n',
          '> 自动生成：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 素材：goldens/res/640x394.raw（face_src），磨皮固定 50 档',
          '> 口径：细频带 = |Y - box3(Y)|，中频带 = |box3 - box7|，均在区域内取均值；'
          '百分比相对**原图**',
          '> 「脸内」= YuNet 人脸框 ∩ 掩码>0；「脸外」= 掩码==0',
          '',
          '| 配置 | 脸内细频带% | 脸内中频带% | 脸外细频带% | 背景改动像素 | 640×394 |',
          '|---|---|---|---|---|---|']
    for name, a, b, c, bg, ms in rows:
        md.append('| %s | %.1f | %.1f | %.1f | %d | %.2f ms |'
                  % (name, a, b, c, bg, ms))
    md.append('')
    md.append('- 磨皮=0 时：锐化100 改动 %d 像素（要求 0）；全局锐化100 改动 %d 像素（要求 >0）'
              % (d_face, d_glob))
    if t_face:
        md.append('- 1080p：基准 %.2f ms，脸内锐化 +%.2f ms，全局锐化 +%.2f ms'
                  % (t_base, t_face - t_base, t_glob - t_base))
    out_md = os.path.join(OUT, 'detail.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print()
    print('[detail] -> %s' % out_md)
    for f in (tmp, maskp):
        if os.path.exists(f):
            os.remove(f)
    return 0


if __name__ == '__main__':
    sys.exit(main())
