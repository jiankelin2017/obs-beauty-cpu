# -*- coding: utf-8 -*-
"""验证 2.1.2 的核心修复：皮肤边界从「硬台阶」变成「渐变」。

台阶之所以是故障：applyRegionEffects 对 m=0 逐字节还原原始帧、对 m=255 全额
美颜，中间没有过渡；applySharpen 的 3x3 高频叠回专门放大这种不连续，把它变成
亮/暗边线。掩码每帧跟踪人脸后，这条线就跟着在皮肤上扫。

做法：静态帧 + 只开美白，沿着穿过皮肤边界的一条水平线打印「每像素被提亮的
亮度值」。台阶 = 相邻像素差几十级且只持续 1~2 像素；渐变 = 平缓铺开十几像素。
"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from measure_whiten_fixed import read_png_rgba  # noqa: E402

DLL = os.path.join(HERE, "legacy_engine_test.dll")
ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
OUT = os.path.join(HERE, "out")

# 用 probe_in.raw（640x394，脸在 x 262..376），人脸右缘是我们要看的边界
W, H = 640, 394
RAW = os.path.join(HERE, "probe_in.raw")


def luma(b, i):
    return (b[i * 4] * 299 + b[i * 4 + 1] * 587 + b[i * 4 + 2] * 114) // 1000


def main():
    rgba = open(RAW, "rb").read()
    assert len(rgba) == W * H * 4
    raw_in = os.path.join(OUT, "_b_in.raw")
    raw_out = os.path.join(OUT, "_b_out.raw")
    open(raw_in, "wb").write(rgba)

    # 只开美白 100，把效果拉到最明显，边界最好看
    open(os.path.join(HERE, "panel.txt"), "w").write("2:100")

    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int]
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySelfTest(ASSET_DIR.encode(), raw_in.encode(), raw_out.encode(),
                           W, H, 0.0, 0.0, msg, 2048)
    print("ret=%d  %s" % (ret, msg.value.decode("utf-8", "replace")[:90]))
    if ret != 0:
        return 1
    b = open(raw_out, "rb").read()

    # 找提亮幅度最大的一行（人脸中部）
    best = None
    for y in range(60, H - 60, 4):
        s = 0
        for x in range(W):
            i = y * W + x
            s += max(0, luma(b, i) - luma(rgba, i))
        if best is None or s > best[0]:
            best = (s, y)
    y = best[1]
    print("取样行 y=%d（该行总提亮 %d 级）" % (y, best[0]))

    # 打印该行 x 250..400 的每像素提亮量
    prof = []
    for x in range(250, 400):
        i = y * W + x
        prof.append((x, luma(b, i) - luma(rgba, i)))

    print("")
    print("   x : 提亮级数")
    line = ""
    for x, d in prof:
        line += "%d:%d " % (x, d)
    # 每 10 个换行
    for i in range(0, len(line), 100):
        print("   " + line[i:i + 100])

    # 判定：统计「相邻像素提亮量跳变 > 20 级」的次数
    jumps = 0
    maxjump = 0
    for k in range(1, len(prof)):
        d = abs(prof[k][1] - prof[k - 1][1])
        if d > 20:
            jumps += 1
        maxjump = max(maxjump, d)
    nz = [d for _, d in prof if d != 0]
    print("")
    print("相邻像素跳变 >20 级的次数: %d" % jumps)
    print("相邻像素最大跳变: %d 级" % maxjump)
    if nz:
        print("提亮区间: %d .. %d（跨度 %d 帧像素）"
              % (min(x for x, d in prof if d != 0),
                 max(x for x, d in prof if d != 0),
                 max(x for x, d in prof if d != 0) - min(x for x, d in prof if d != 0) + 1))
    if jumps == 0 and maxjump <= 20:
        print("")
        print("结论：PASS —— 边界是渐变，没有硬台阶")
    else:
        print("")
        print("结论：仍有硬跳变（%d 处 >20 级）" % jumps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
