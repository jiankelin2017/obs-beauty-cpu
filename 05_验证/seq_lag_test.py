# -*- coding: utf-8 -*-
"""端到端验证「掩码滞后」BUG 修复（2.1.1）。

做法：在同一个进程里连续处理 8 帧，每帧人脸向右平移 20 px。然后量每一帧
「被改亮的像素」的质心 —— 那就是美白真正落到的位置。

  * 2.1.0（every=3）：第 1/4/7 帧掩码是新的，其余帧沿用旧掩码，
    质心会停在上一帧人脸的位置上，呈锯齿。
  * 2.1.1（every=1 + 关关键点）：质心应每帧都跟上人脸。

人脸在 probe_in.raw 里位于 x 262..376（中心约 319），整帧 640x394。
"""
import ctypes
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "legacy_engine_test.dll")
# 直接用 OBS 里已装好的那一份资源（只读，不动它）
ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
STEP = int(sys.argv[1]) if len(sys.argv) > 1 else 20
IN_DIR = os.path.join(HERE, "seq_in_s%d" % STEP)
OUT_DIR = os.path.join(HERE, "seq_out_s%d" % STEP)
W, H = 640, 394
N = 8

BASE = open(os.path.join(HERE, "probe_in.raw"), "rb").read()
assert len(BASE) == W * H * 4


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


def build_sequence():
    if os.path.isdir(IN_DIR):
        shutil.rmtree(IN_DIR)
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(IN_DIR)
    os.makedirs(OUT_DIR)
    for k in range(N):
        open(os.path.join(IN_DIR, "seq_%03d.raw" % k), "wb").write(shifted(k * STEP))


def luma(p, i):
    return (p[i * 4 + 0] * 299 + p[i * 4 + 1] * 587 + p[i * 4 + 2] * 114) // 1000


def bright_centroid(src, dst):
    """质心只统计「明显变亮」的像素 —— 美白是唯一的提亮项。"""
    sx = sy = sw = 0.0
    for y in range(H):
        for x in range(W):
            i = y * W + x
            d = luma(dst, i) - luma(src, i)
            if d >= 6:
                sx += d * x
                sy += d * y
                sw += d
    if sw <= 0:
        return None, 0
    return (sx / sw, sy / sw), int(sw)


def main():
    build_sequence()
    # panel.txt: 只开美白（P_WHITEN=3），磨皮关掉，让现象最干净
    open(os.path.join(HERE, "panel.txt"), "w").write("2:55")

    dll = ctypes.WinDLL(DLL)
    dll.LegacySeqTest.restype = ctypes.c_int
    dll.LegacySeqTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int,
    ]
    msg = ctypes.create_string_buffer(1024)
    ret = dll.LegacySeqTest(
        ASSET_DIR.encode("ascii"), IN_DIR.encode("ascii"), OUT_DIR.encode("ascii"),
        W, H, N, 0.0, 55.0, msg, 1024)
    print("ret=%d" % ret)
    print("msg=%s" % msg.value.decode("utf-8", "replace"))
    if ret != 0:
        sys.exit(ret)

    print("")
    print("帧  人脸中心x  美白质心x  偏差   权重")
    print("-" * 46)
    rows = []
    for k in range(N):
        src = open(os.path.join(IN_DIR, "seq_%03d.raw" % k), "rb").read()
        dst = open(os.path.join(OUT_DIR, "seq_%03d.raw" % k), "rb").read()
        (cx, cy), wt = bright_centroid(src, dst)
        face_cx = 319.0 + k * STEP
        dev = (cx - face_cx) if cx is not None else float("nan")
        rows.append((k, face_cx, cx, dev, wt))
        print("%-3d %9.1f %10.1f %+6.1f %8d" % (k, face_cx, cx, dev, wt))

    devs = [abs(r[3]) for r in rows if r[2] is not None]
    print("")
    print("最大偏差 %.1f px，平均 %.1f px" % (max(devs), sum(devs) / len(devs)))
    # 判定：人脸每帧移 20 px，质心偏差应远小于一步位移（<8 px 即视为跟上）
    if max(devs) < 8.0:
        print("结论：PASS —— 美白质心每帧都跟上人脸，无滞后")
        return 0
    print("结论：FAIL —— 仍有滞后")
    return 1


if __name__ == "__main__":
    sys.exit(main())
