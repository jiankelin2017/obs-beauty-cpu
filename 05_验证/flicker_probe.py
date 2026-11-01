# -*- coding: utf-8 -*-
"""遮罩屏闪诊断（2026-10-25）。

用户报告：2.1.3/2.2.0 装机后，「部分部位依旧遮罩屏闪」。本脚本在测试环境
复现并定位：

场景（同一进程内连续 12 帧，保留 SDK/fuai 的跨帧时序状态）：
  static  —— 同一帧重复 12 次。输出若有帧间差异 = 内部状态抖动（与输入无关）
  noisy   —— 同帧 + 每帧 ±2 传感器噪声。模拟真实摄像头：输入本身在抖
  moving  —— 复用滞后测试的 8 帧运动序列（人脸每帧移 20px）

参数用用户截图同款：磨皮 50 / 美白 50 / 红润 30 / 锐化 50（双边过滤 +
精准美肤开，与 UI 默认一致）。noisy 场景额外跑一组「去掉锐化」对照，
分离 applySharpen 对抖动的放大贡献。

每帧记录（seq_log.txt）：faces / 覆盖率 / 推理次数 / 与上一帧输出的差异。
每次推理记录（infer_log.txt）：掩码有无（mask=0 的帧会走颜色启发式回退）。
每次推理转储（mask_dump_%03d.raw）：fuai 原始掩码 + 软化后掩码。

用法：python flicker_probe.py <scenario> [panel]
"""
import ctypes
import os
import random
import struct
import sys

HERE = os.path.abspath(".")
sys.path.insert(0, HERE)
from measure_whiten_fixed import read_png_rgba

DLL = os.path.join(HERE, "legacy_engine_test.dll")
ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
W, H = 1074, 604
COUNT = 12

# 用户截图同参数
PANEL_USER = "0:50,2:50,3:30,4:50"
# 去掉锐化的对照
PANEL_NOSHARP = "0:50,2:50,3:30"


def prep_static(d):
    os.makedirs(d, exist_ok=True)
    rgba, w, h = read_png_rgba("out/frame_0.png")
    assert (w, h) == (W, H), (w, h)
    for k in range(COUNT):
        open(os.path.join(d, "seq_%03d.raw" % k), "wb").write(rgba)


def prep_noisy(d):
    os.makedirs(d, exist_ok=True)
    rgba, w, h = read_png_rgba("out/frame_0.png")
    assert (w, h) == (W, H), (w, h)
    rnd = random.Random(20261025)
    for k in range(COUNT):
        b = bytearray(rgba)
        for i in range(0, len(b), 4):
            for c in range(3):
                v = b[i + c] + rnd.randint(-2, 2)
                b[i + c] = 0 if v < 0 else (255 if v > 255 else v)
        open(os.path.join(d, "seq_%03d.raw" % k), "wb").write(bytes(b))


def prep_noisy_preblur(d):
    """加噪 + 3x3 box 预模糊（模拟「喂给 fuai 前先削噪」的候选解法）。
    只为测量掩码抖动的下降幅度，不进生产源码。"""
    import io
    from PIL import Image, ImageFilter
    os.makedirs(d, exist_ok=True)
    rgba, w, h = read_png_rgba("out/frame_0.png")
    assert (w, h) == (W, H), (w, h)
    rnd = random.Random(20261025)
    for k in range(COUNT):
        b = bytearray(rgba)
        for i in range(0, len(b), 4):
            for c in range(3):
                v = b[i + c] + rnd.randint(-2, 2)
                b[i + c] = 0 if v < 0 else (255 if v > 255 else v)
        im = Image.frombytes("RGBA", (W, H), bytes(b))
        im = im.filter(ImageFilter.BoxBlur(1))
        open(os.path.join(d, "seq_%03d.raw" % k), "wb").write(im.tobytes())


def run_seq(indir, outdir, panel):
    open(os.path.join(HERE, "panel.txt"), "w").write(panel)
    dll = ctypes.WinDLL(DLL)
    dll.LegacySeqTest.restype = ctypes.c_int
    dll.LegacySeqTest.argtypes = ([ctypes.c_char_p] * 3 + [ctypes.c_int] * 3 +
                                [ctypes.c_double] * 2 +
                                [ctypes.c_char_p, ctypes.c_int])
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySeqTest(ASSET_DIR.encode("ascii"),
                          indir.encode("ascii"), outdir.encode("ascii"),
                          W, H, COUNT, 50.0, 50.0, msg, 2048)
    return ret, msg.value.decode("utf-8", "replace")


def clear_logs():
    for f in ("seq_log.txt", "infer_log.txt"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)
    for f in os.listdir(HERE):
        if f.startswith("mask_dump_"):
            os.remove(os.path.join(HERE, f))


def parse_seq_log():
    rows = []
    p = os.path.join(HERE, "seq_log.txt")
    if not os.path.exists(p):
        return rows
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line.startswith("seq="):
            continue
        d = {}
        for kv in line.split():
            k, _, v = kv.partition("=")
            d[k] = v
        rows.append(d)
    return rows


def parse_infer_log():
    rows = []
    p = os.path.join(HERE, "infer_log.txt")
    if not os.path.exists(p):
        return rows
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line.startswith("frame="):
            continue
        d = {}
        for kv in line.split():
            k, _, v = kv.partition("=")
            d[k] = v
        rows.append(d)
    return rows


def load_masks():
    out = []
    for f in sorted(os.listdir(HERE)):
        if not f.startswith("mask_dump_"):
            continue
        d = open(os.path.join(HERE, f), "rb").read()
        mw, mh = struct.unpack_from("<ii", d, 0)
        n = mw * mh
        out.append((f, mw, mh, d[8:8 + n], d[8 + n:8 + 2 * n]))
    return out


def report(name):
    print("")
    print("=" * 74)
    print("场景 %s" % name)
    print("=" * 74)

    seq = parse_seq_log()
    infer = parse_infer_log()

    print("-- 推理日志（infer_log.txt）--")
    nomask = [r for r in infer if r.get("mask") == "0"]
    print("  推理 %d 次，其中无掩码 %d 次" % (len(infer), len(nomask)))
    if nomask:
        print("  无掩码帧号: %s" % ", ".join(r["frame"] for r in nomask))
    covs = [float(r["cov"]) for r in infer if r.get("mask") == "1"]
    if covs:
        print("  覆盖率: min=%.4f max=%.4f 极差=%.4f"
              % (min(covs), max(covs), max(covs) - min(covs)))

    print("-- 逐帧状态（seq_log.txt）--")
    print("  %-5s %-6s %-8s %-7s %-9s %-8s %-8s"
          % ("帧", "faces", "覆盖率", "推理数", "平均差", "变化px", "最大差"))
    faces_seq = []
    for r in seq:
        faces_seq.append(int(r["faces"]))
        print("  %-5s %-6s %-8s %-7s %-9s %-8s %-8s"
              % (r["seq"], r["faces"], r["cov"], r["infer"],
                 r["meanAbs"], r["chgPx"], r["maxDiff"]))
    flips = sum(1 for a, b in zip(faces_seq, faces_seq[1:]) if a != b)
    print("  faces 跳变次数: %d" % flips)

    print("-- 掩码帧间对比（mask_dump_*.raw）--")
    masks = load_masks()
    if len(masks) >= 2:
        print("  %-22s %-14s %-14s %-10s"
              % ("帧对", "raw变化px", "soft变化px", "soft最大"))
        for i in range(1, len(masks)):
            f0, mw, mh, raw0, soft0 = masks[i - 1]
            f1, _, _, raw1, soft1 = masks[i]
            draw = sum(1 for a, b in zip(raw0, raw1) if a != b)
            dsoft = [abs(a - b) for a, b in zip(soft0, soft1)]
            nsoft = sum(1 for v in dsoft if v > 0)
            print("  %-22s %-14d %-14d %-10d"
                  % ("%s->%s" % (f0[-7:-4], f1[-7:-4]), draw, nsoft,
                     max(dsoft) if dsoft else 0))
        # 变化位置：集中在过渡带（soft 中间值）还是内部
        band = interior = outside = 0
        for i in range(1, len(masks)):
            _, _, _, _, soft0 = masks[i - 1]
            _, _, _, _, soft1 = masks[i]
            for a, b in zip(soft0, soft1):
                if a == b:
                    continue
                if a == 255:
                    interior += 1
                elif a == 0:
                    outside += 1
                else:
                    band += 1
        tot = band + interior + outside
        if tot:
            print("  变化像素位置: 过渡带(中间值) %.1f%% / 皮肤内部 %.1f%% / 掩码外 %.1f%%"
                  % (100.0 * band / tot, 100.0 * interior / tot,
                     100.0 * outside / tot))

    print("-- 掩码质心帧间位移（运动判据验证，单位=掩码像素）--")
    if len(masks) >= 2:
        cents = []
        for f, mw, mh, raw, soft in masks:
            sx = sy = sw = 0.0
            for i, v in enumerate(soft):
                if v:
                    y, x = divmod(i, mw)
                    sx += x * v
                    sy += y * v
                    sw += v
            cents.append((sx / sw, sy / sw) if sw > 0 else (-1.0, -1.0))
        for i in range(1, len(cents)):
            if cents[i][0] < 0 or cents[i - 1][0] < 0:
                print("  %03d->%03d: 质心缺失" % (i - 1, i))
                continue
            dx = cents[i][0] - cents[i - 1][0]
            dy = cents[i][1] - cents[i - 1][1]
            print("  %03d->%03d: 质心位移 %.3f (dx=%+.3f dy=%+.3f)"
                  % (i - 1, i, (dx * dx + dy * dy) ** 0.5, dx, dy))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    scen = sys.argv[1]
    panel = sys.argv[2] if len(sys.argv) > 2 else PANEL_USER

    if scen == "static":
        indir = os.path.join(HERE, "flick", "static")
        prep_static(indir)
    elif scen == "noisy":
        indir = os.path.join(HERE, "flick", "noisy")
        prep_noisy(indir)
    elif scen == "noisy_preblur":
        indir = os.path.join(HERE, "flick", "noisy_preblur")
        prep_noisy_preblur(indir)
    elif scen == "moving":
        indir = os.path.join(HERE, "seq_in")
        if not os.path.exists(os.path.join(indir, "seq_000.raw")):
            print("缺少 seq_in/seq_000.raw")
            return 3
    elif scen == "noisy_nosharp":
        indir = os.path.join(HERE, "flick", "noisy")
        prep_noisy(indir)
        panel = PANEL_NOSHARP
    elif scen == "noisy_whiten":
        # 只开美白+红润：输出帧间差几乎只剩「掩码抖动 → 效果强度振荡」，
        # 是屏闪的直接观测量（SDK 磨皮的噪声传播被排除）。
        indir = os.path.join(HERE, "flick", "noisy")
        prep_noisy(indir)
        panel = "2:50,3:30"
    else:
        print("unknown scenario:", scen)
        return 2

    outdir = os.path.join(HERE, "flick", scen + "_out")
    os.makedirs(outdir, exist_ok=True)
    clear_logs()
    open(os.path.join(HERE, "dump_mask.txt"), "w").write("on")
    ret, msg = run_seq(indir, outdir, panel)
    os.remove(os.path.join(HERE, "dump_mask.txt"))
    print("LegacySeqTest ret=%d  %s" % (ret, msg))
    print("panel=%s" % panel)
    report(scen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
