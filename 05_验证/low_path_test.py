# low_path_test.py —— 低频层三条路线的对照（浮点 / 低频参照 各自贡献多少）
#
# 背景：04_文档/开源参考仓库_对照与可复用清单.md §7
#   即「只看局部起伏」。我们原来是绝对差 tap-center。
#   同时它用 RGBA16F 存中间结果，我们原来压回 uint8。
#
# 三组对照：
#   path=0  旧：uint8 双边迭代 + 绝对差
#   path=1  只换浮点：float 双边迭代 + 绝对差
#   path=2  浮点 + 参照：float 双边迭代 + 只看局部起伏  ← 默认
#
# 指标口径与 C4 文档一致：
#   低频保留%  = 区域内 mean|Laplacian(σ=12 低频层)| 相对原图
#   小/中/大%  = |高频| 分层（<6 / 6~30 / >30）后各层的保留率
#   磨皮量     = 区域内 mean|out-src|
# 判据：理想是「低频≈100%，小幅度↓，大幅度≈100%」。
#   「小幅度 > 100%」= 磨皮反而造出新纹理（阶梯效应）。

import ctypes
import os
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')

# face_src 的 YuNet 人脸框（原图坐标）
FACE = (277, 384, 89, 223)


def load(path, w, h):
    return np.fromfile(path, dtype=np.uint8).reshape((h, w, 4))


def gauss_rgb(a, sigma):
    """可分离高斯（float），只在 Python 侧做指标计算，不参与产品路径。"""
    h, w = a.shape[:2]
    r = int(sigma * 3 + 0.5)
    k = np.exp(-(np.arange(-r, r + 1, dtype=np.float32) ** 2) /
               (2.0 * sigma * sigma))
    k /= k.sum()
    f = a.astype(np.float32)
    p = np.pad(f, ((0, 0), (r, r), (0, 0)), mode='edge')
    t = np.zeros_like(f)
    for i, kv in enumerate(k):
        t += p[:, i:i + w, :] * kv
    p2 = np.pad(t, ((r, r), (0, 0), (0, 0)), mode='edge')
    o = np.zeros_like(t)
    for i, kv in enumerate(k):
        o += p2[i:i + h, :, :] * kv
    return o


def laplacian_mean(low_rgb, region_full):
    """区域内 mean|Laplacian|。返回全尺寸数组后再索引，避免 (h-2,w-2) 错位。"""
    g = low_rgb.mean(axis=2)
    lap = np.zeros_like(g)
    lap[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
                             - g[1:-1, :-2] - g[1:-1, 2:])
    return lap[region_full].mean()


def run_path(dll, path, raw, out, w, h, blur=100.0, ref_r=8, iters=2):
    dll.BeautyCoreSetLowPath(path, ref_r)
    dll.BeautyCoreSetFreq(1, float(iters), 6.0, 30.0)     # 高低频开，iters 固定
    dll.BeautyCoreSetGuide(0, 12, 400.0)                  # 关掉引导滤波
    msg = ctypes.create_string_buffer(512)
    for _ in range(4):                                    # 预热（掩码每 4 帧重建）
        dll.BeautyCoreRun(raw.encode(), out.encode(), w, h, blur, 0, 0.0, 0.0, 1,
                          msg, 512)
    best = 1e9
    for _ in range(4):
        t0 = time.perf_counter()
        rc = dll.BeautyCoreRun(raw.encode(), out.encode(), w, h, blur, 0, 0.0,
                               0.0, 1, msg, 512)
        best = min(best, (time.perf_counter() - t0) * 1000.0)
    if rc != 0:
        return None, best, msg.value.decode('utf-8', 'replace')
    return True, best, ''


def main():
    if not os.path.exists(DLL):
        print('[lowpath] missing %s (run build_core_test.bat)' % DLL)
        return 2
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetFreq.argtypes = [ctypes.c_int, ctypes.c_float,
                                      ctypes.c_float, ctypes.c_float]
    dll.BeautyCoreSetGuide.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
    dll.BeautyCoreSetLowPath.argtypes = [ctypes.c_int, ctypes.c_int]

    os.makedirs(OUT, exist_ok=True)
    name = '640x394'
    w, h = 640, 394
    raw = os.path.join(RES, name + '.raw')
    tmp = os.path.join(OUT, '_lowpath.raw')
    src = load(raw, w, h)

    # 参照指标：σ=12 的高斯定义低频（与 C4 文档同口径）
    low_src = gauss_rgb(src[:, :, :3], 12.0)
    high_src = src[:, :, :3].astype(np.float32) - low_src
    hmag = np.abs(high_src).max(axis=2)

    region = np.zeros((h, w), bool)
    x0, x1, y0, y1 = FACE
    region[y0:y1, x0:x1] = True
    bands = [('小幅度(<6)', hmag < 6),
             ('中幅度(6~30)', (hmag >= 6) & (hmag < 30)),
             ('大幅度(>30)', hmag >= 30)]

    lap_src = laplacian_mean(low_src, region)

    rows = []
    for path, tag in ((0, '0 旧：uint8+绝对差'),
                      (1, '1 浮点：float+绝对差'),
                      (2, '2 浮点+参照：只看局部起伏')):
        out_img, ms, note = run_path(dll, path, raw, tmp, w, h)
        if out_img is None and not os.path.exists(tmp):
            rows.append((tag, None, ms, note))
            print('  %-26s FAIL %s' % (tag, note))
            continue
        o = load(tmp, w, h)
        low_o = gauss_rgb(o[:, :, :3], 12.0)
        high_o = o[:, :, :3].astype(np.float32) - low_o
        r = {'tag': tag,
             'ms': ms,
             'low': 100.0 * laplacian_mean(low_o, region) / lap_src,
             'amt': float(np.abs(o[region][:, :3].astype(np.float32)
                                 - src[region][:, :3].astype(np.float32)).mean()),
             'bands': [100.0 * np.abs(high_o[s & region]).mean()
                       / np.abs(high_src[s & region]).mean() for _, s in bands]}
        rows.append((tag, r, ms, note))
        print('  %-26s %6.1f%% %6.1f%% %6.1f%% %6.1f%% %7.3f %6.2f ms'
              % (tag, r['low'], r['bands'][0], r['bands'][1], r['bands'][2],
                 r['amt'], ms))

    # 1080p 计时（只比成本，不算指标：那张图没有对应的人脸基线）
    times = {}
    for path in (0, 1, 2):
        for nm, ww, hh in (('640x394', 640, 394), ('1080p', 1920, 1080)):
            p2 = os.path.join(RES, nm + '.raw')
            if not os.path.exists(p2):
                continue
            _, ms, _ = run_path(dll, path, p2, tmp, ww, hh, blur=50.0)
            times[(path, nm)] = ms
    for k in list(times):
        if os.path.exists(tmp):
            os.remove(tmp)

    # 报告
    md = ['# 低频层三条路线对照（浮点 / 低频参照）\n',
          '> 自动生成：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
          '> 素材：goldens/res/640x394.raw（face_src），区域 = YuNet 人脸框',
          '> 指标口径见 04_文档/C4_高低频磨皮.md\n',
          '| 路线 | 低频保留% | 小幅度% | 中幅度% | 大幅度% | 磨皮量 | 640×394 | 1080p |',
          '|---|---|---|---|---|---|---|---|']
    for tag, r, ms, note in rows:
        if r is None:
            md.append('| %s | FAIL | | | | | | |' % tag)
            continue
        md.append('| %s | %.1f | %.1f | %.1f | %.1f | %.3f | %.2f ms | %s |'
                  % (tag, r['low'], r['bands'][0], r['bands'][1], r['bands'][2],
                     r['amt'], times.get((int(tag[0]), '640x394'), float('nan')),
                     ('%.2f ms' % times[(int(tag[0]), '1080p')])
                     if (int(tag[0]), '1080p') in times else '-'))
    md.append('')
    md.append('判据：低频≈100%（脸不塌）+ 小幅度明显下降（瑕疵磨掉）'
              '+ 大幅度≈100%（五官轮廓保住）。')
    md.append('「小幅度 > 100%」= 磨皮反而造出新纹理，即阶梯效应。')

    out_md = os.path.join(OUT, 'low_path.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('[lowpath] -> %s' % out_md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
