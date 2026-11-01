# -*- coding: utf-8 -*-
"""脸部屏闪 / 瞬间失效探针（2026-10-25）。

用户报告：「开启效果后，脸部出现屏闪，难道是瞬间失效？」

现有回归（静态 12 帧、噪声、平移、阶跃）都测不出「某帧整脸效果归零」这种
二值化失效，因为静态序列里掩码一直稳。本脚本换三个口径：

  1) 脸内亮度逐帧序列 fy[k] —— 美白/磨皮效果若某帧消失，fy 会阶跃跳一下。
     std(fy) 就是「肉眼看到的明暗呼吸」。
  2) 脸内帧间差 dprev[k] —— 同一张静图 + 噪声，输出本应只随噪声小幅变；
     若某帧走了别的分支（整帧还原 / 丢掉掩码），dprev 会尖峰。
  3) 脸外帧间差 —— 掩码外本该逐字节等于输入（背景零改动），出现非零即
     「mask 限制失效」，也就是整屏闪。

用法：
  python nz_probe.py prep [noise] [count]        生成共享噪声序列（只做一次）
  python nz_probe.py run <dll> <tag> <panel>     跑一组，输出 flick/nz_<tag>_out
  python nz_probe.py cmp <tagA> <tagB> ...       对比若干组
"""
import ctypes
import os
import random
import struct
import sys

HERE = os.path.abspath(".")
sys.path.insert(0, HERE)
from measure_whiten_fixed import read_png_rgba

ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
W, H = 1074, 604
BASE_PNG = "out/frame_0.png"
INDIR = os.path.join(HERE, "flick", "nz_in")
MARK = os.path.join(INDIR, "meta.txt")


# ---------------------------------------------------------------- 输入准备
def prep(noise=5, count=10):
    os.makedirs(INDIR, exist_ok=True)
    if os.path.exists(MARK):
        meta = open(MARK).read().split()
        if len(meta) == 2 and int(meta[0]) == noise and int(meta[1]) == count:
            if all(os.path.exists(os.path.join(INDIR, "seq_%03d.raw" % k))
                   for k in range(count)):
                print("复用已有序列 noise=±%d count=%d" % (noise, count))
                return
    rgba, w, h = read_png_rgba(BASE_PNG)
    assert (w, h) == (W, H), (w, h)
    # 加法查表：ADD[a][b] = clamp(a + b - 128)，b 是噪声字节
    ADD = []
    for a in range(256):
        row = bytearray(256)
        for b in range(256):
            v = a + b - 128
            row[b] = 0 if v < 0 else (255 if v > 255 else v)
        ADD.append(bytes(row))
    rnd = random.Random(20261025)
    lo, hi = 128 - noise, 128 + noise
    # randbytes 给的是 0..255 全幅，必须压到 [lo, hi]，否则不是「传感器噪声」
    # 而是把画面打烂（±127 会把 fuai 的人脸检测直接打掉，实测 faces=0）。
    SCALE = bytes(lo + (b * (2 * noise + 1)) // 256 for b in range(256))
    n = len(rgba)
    for k in range(count):
        nz = rnd.randbytes(n).translate(SCALE)   # 全通道白噪，含 alpha
        out = bytearray(n)
        for i in range(n):
            out[i] = ADD[rgba[i]][nz[i]]
        # alpha 复原（噪声不该动 alpha）
        for i in range(3, n, 4):
            out[i] = rgba[i]
        open(os.path.join(INDIR, "seq_%03d.raw" % k), "wb").write(bytes(out))
    open(MARK, "w").write("%d %d" % (noise, count))
    print("生成 noise=±%d count=%d -> %s" % (noise, count, INDIR))


# ---------------------------------------------------------------- 跑一组
def clear_dump():
    for f in os.listdir(HERE):
        if f.startswith("mask_dump_"):
            os.remove(os.path.join(HERE, f))


def run(dll, tag, panel):
    count = int(open(MARK).read().split()[1]) if os.path.exists(MARK) else 10
    outdir = os.path.join(HERE, "flick", "nz_%s_out" % tag)
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(HERE, "panel.txt"), "w").write(panel)
    open(os.path.join(HERE, "dump_mask.txt"), "w").write("on")
    clear_dump()
    d = ctypes.WinDLL(os.path.abspath(dll))
    d.LegacySeqTest.restype = ctypes.c_int
    d.LegacySeqTest.argtypes = ([ctypes.c_char_p] * 3 + [ctypes.c_int] * 3 +
                              [ctypes.c_double] * 2 +
                              [ctypes.c_char_p, ctypes.c_int])
    msg = ctypes.create_string_buffer(2048)
    ret = d.LegacySeqTest(ASSET_DIR.encode("ascii"),
                        INDIR.encode("ascii"), outdir.encode("ascii"),
                        W, H, count, 50.0, 50.0, msg, 2048)
    if os.path.exists(os.path.join(HERE, "dump_mask.txt")):
        os.remove(os.path.join(HERE, "dump_mask.txt"))
    # 把本次掩码存到输出目录旁，供 cmp 用
    dumps = sorted(f for f in os.listdir(HERE) if f.startswith("mask_dump_"))
    if dumps:
        src = os.path.join(HERE, dumps[-1])
        open(os.path.join(HERE, "flick", "mask_%s.raw" % tag), "wb").write(
            open(src, "rb").read())
    print("%-10s dll=%s panel=%s ret=%d %s"
          % (tag, os.path.basename(dll), panel, ret,
             msg.value.decode("utf-8", "replace")))
    return ret


# ---------------------------------------------------------------- 分析
def load_mask(tag):
    p = os.path.join(HERE, "flick", "mask_%s.raw" % tag)
    if not os.path.exists(p):
        return None
    d = open(p, "rb").read()
    mw, mh = struct.unpack_from("<ii", d, 0)
    n = mw * mh
    soft = d[8 + n:8 + 2 * n]
    return mw, mh, soft


def mask_index(tag):
    """把掩码上采样到全帧，返回 (脸内像素偏移列表, 脸外抽样偏移列表)。"""
    m = load_mask(tag)
    if not m:
        return None, None
    mw, mh, soft = m
    inside, outside = [], []
    for y in range(H):
        my = min(mh - 1, y * mh // H)
        for x in range(W):
            mx = min(mw - 1, x * mw // W)
            off = (y * W + x) * 4
            if soft[my * mw + mx] >= 200:
                inside.append(off)
            elif soft[my * mw + mx] == 0 and (x % 7 == 0):
                outside.append(off)      # 抽样，背景区 1/7
    return inside, outside


def lum(buf, offs):
    n = len(offs)
    if n == 0:
        return 0.0
    s = 0
    for o in offs:
        s += buf[o] * 299 + buf[o + 1] * 587 + buf[o + 2] * 114
    return s / (1000.0 * n)


def diff(bufA, bufB, offs):
    n = len(offs)
    if n == 0:
        return 0.0
    s = 0
    for o in offs:
        s += abs(bufA[o] - bufB[o]) + abs(bufA[o + 1] - bufB[o + 1]) + \
             abs(bufA[o + 2] - bufB[o + 2])
    return s / (3.0 * n)


def std(v):
    if len(v) < 2:
        return 0.0
    m = sum(v) / len(v)
    return (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5


def analyze(tag):
    outdir = os.path.join(HERE, "flick", "nz_%s_out" % tag)
    files = sorted(f for f in os.listdir(outdir) if f.endswith(".raw"))
    if not files:
        return None
    ins, outs = mask_index(tag)
    if ins is None:
        return None
    ins = ins[::3]          # 抽样，够用且快
    outs = outs[::3]
    ins_src = ins           # src 与 out 同尺寸同布局
    fy, dp_in, dp_out, ds_in = [], [], [], []
    prev = None
    for f in files:
        buf = open(os.path.join(outdir, f), "rb").read()
        src = open(os.path.join(INDIR, f), "rb").read()
        fy.append(lum(buf, ins))
        ds_in.append(diff(buf, src, ins_src))
        if prev is not None:
            dp_in.append(diff(buf, prev, ins))
            dp_out.append(diff(buf, prev, outs))
        prev = buf
    return {
        "tag": tag, "n": len(files),
        "fy": fy, "fy_std": std(fy),
        "fy_range": max(fy) - min(fy),
        "dp_in": dp_in, "dp_in_max": max(dp_in) if dp_in else 0.0,
        "dp_in_mean": sum(dp_in) / len(dp_in) if dp_in else 0.0,
        "dp_out_max": max(dp_out) if dp_out else 0.0,
        "ds_in": sum(ds_in) / len(ds_in),
        "npix": len(ins),
    }


def cmp(tags):
    rows = []
    for t in tags:
        r = analyze(t)
        if r:
            rows.append(r)
    print("")
    print("=" * 88)
    print("%-12s %-5s %-8s %-8s %-10s %-10s %-9s %-8s"
          % ("组", "帧", "脸Y均值", "脸Y极差", "脸内帧间差", "帧间差峰值",
             "脸外峰值", "效果量"))
    print("-" * 88)
    for r in rows:
        print("%-12s %-5d %-8.2f %-8.2f %-10.3f %-10.3f %-9.3f %-8.2f"
              % (r["tag"], r["n"], sum(r["fy"]) / len(r["fy"]), r["fy_range"],
                 r["dp_in_mean"], r["dp_in_max"], r["dp_out_max"], r["ds_in"]))
    print("-" * 88)
    for r in rows:
        print("%-12s 脸Y逐帧: %s" % (r["tag"],
              " ".join("%.1f" % v for v in r["fy"])))
    for r in rows:
        print("%-12s 脸内帧间: %s" % (r["tag"],
              " ".join("%.2f" % v for v in r["dp_in"])))
    print("=" * 88)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "prep":
        noise = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        prep(noise, count)
    elif cmd == "run":
        run(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "cmp":
        cmp(sys.argv[2:])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
