# -*- coding: utf-8 -*-
"""输出层时序稳定性 A/B：2.1.0 配置 vs 2.1.1 配置。

掩码已经证明在两种配置下逐比特相同、零 NULL、帧间抖动极小，所以如果用户看到
「黑白灰快速跳」，问题一定出在**输出**上。

做法：同一段人脸移动序列，用用户的真实参数（磨皮75/美白55/红润30/锐化75）
分别跑 2.1.0 配置（关键点ON + every=3）和 2.1.1 配置（关键点OFF + every=1），
然后统计：
  1) 相邻帧输出的平均|差| —— 画面闪烁程度
  2) 纯黑(0,0,0)/纯白(255,255,255)像素数及其帧间变化
  3) 皮肤像素的亮度标准差随帧号的波动
"""
import ctypes
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "legacy_engine_test.dll")
ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
IN_DIR = os.path.join(HERE, "tb_in")
OUT_DIR = os.path.join(HERE, "tb_out")
W, H = 640, 394
N = 24
STEP = 8          # 每帧 8px，30fps 下 240px/s，比真实头部晃动快一些，放大问题

BASE = open(os.path.join(HERE, "probe_in.raw"), "rb").read()
assert len(BASE) == W * H * 4

PANEL = "0:75,2:55,3:30,4:75"   # 磨皮75 美白55 红润30 锐化75


def shifted(dx):
    out = bytearray(len(BASE))
    for y in range(H):
        row = y * W * 4
        for x in range(W):
            sx = x - dx
            if 0 <= sx < W:
                out[row + x * 4: row + x * 4 + 4] = BASE[row + sx * 4: row + sx * 4 + 4]
            else:
                out[row + x * 4: row + x * 4 + 4] = b"\x00\x00\x00\xff"
    return bytes(out)


def build_seq():
    for d in (IN_DIR, OUT_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    for k in range(N):
        open(os.path.join(IN_DIR, "seq_%03d.raw" % k), "wb").write(shifted(k * STEP))


def luma(b, i):
    return (b[i * 4] * 299 + b[i * 4 + 1] * 587 + b[i * 4 + 2] * 114) // 1000


def is_skin(b, i):
    r, g, bl = b[i * 4], b[i * 4 + 1], b[i * 4 + 2]
    y = 0.299 * r + 0.587 * g + 0.114 * bl
    cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * bl
    cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * bl
    if y < 30 or not (77 <= cb <= 127) or not (133 <= cr <= 173):
        return False
    mx, mn = max(r, g, bl), min(r, g, bl)
    if mx > 0 and (mx - mn) / mx > 0.55:
        return False
    return True


def run_seq():
    open(os.path.join(HERE, "panel.txt"), "w").write(PANEL)
    dll = ctypes.WinDLL(DLL)
    dll.LegacySeqTest.restype = ctypes.c_int
    dll.LegacySeqTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int]
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySeqTest(ASSET_DIR.encode(), IN_DIR.encode(), OUT_DIR.encode(),
                          W, H, N, 75.0, 55.0, msg, 2048)
    if ret != 0:
        print("FAIL", msg.value.decode("utf-8", "replace"))
        return None
    print("  engine:", msg.value.decode("utf-8", "replace")[:110])
    outs = []
    for k in range(N):
        outs.append(open(os.path.join(OUT_DIR, "seq_%03d.raw" % k), "rb").read())
    return outs


def analyse(outs, tag):
    print("")
    print("--- %s ---" % tag)
    # 1) 相邻帧输出的平均|差|（只看皮肤像素）
    skin = [i for i in range(W * H) if is_skin(outs[0], i)]
    print("  皮肤像素（按第 0 帧判据）: %d" % len(skin))
    diffs = []
    for k in range(1, len(outs)):
        a, b = outs[k - 1], outs[k]
        s = 0
        for i in skin:
            s += abs(luma(b, i) - luma(a, i))
        diffs.append(s / float(len(skin)))
    print("  相邻帧皮肤亮度平均|差|: 均=%.3f  max=%.3f" %
          (sum(diffs) / len(diffs), max(diffs)))

    # 2) 纯黑/纯白像素
    for name, pred in (("纯黑(0,0,0)", lambda b, i: b[i*4] == 0 and b[i*4+1] == 0 and b[i*4+2] == 0),
                       ("纯白(255,255,255)", lambda b, i: b[i*4] == 255 and b[i*4+1] == 255 and b[i*4+2] == 255)):
        cnt = [sum(1 for i in range(W * H) if pred(b, i)) for b in outs]
        print("  %s 每帧数量: min=%d max=%d  （第0帧=%d 末帧=%d）"
              % (name, min(cnt), max(cnt), cnt[0], cnt[-1]))

    # 3) 皮肤亮度均值随帧波动
    means = []
    for b in outs:
        s = sum(luma(b, i) for i in skin) / float(len(skin))
        means.append(s)
    print("  皮肤平均亮度: min=%.2f max=%.2f 极差=%.2f"
          % (min(means), max(means), max(means) - min(means)))
    # 4) 逐帧亮度的帧间跳变最大值
    jumps = [abs(means[k] - means[k - 1]) for k in range(1, len(means))]
    print("  皮肤平均亮度帧间跳变: max=%.2f" % max(jumps))
    return diffs, means


def main():
    build_seq()
    print("=== 2.1.1 配置（当前：关键点OFF + every=1）===")
    a = run_seq()
    if a is None:
        return 1
    analyse(a, "2.1.1 关键点OFF + every=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
