# -*- coding: utf-8 -*-
"""验证 3.0.5 的「掩码丢失保持」：前 6 帧有人脸，后 6 帧换成纯灰（无人脸）。

判据看 infer_log.txt（钩子只写在「真正关掉效果」的那条分支上）：
  正常帧        mask=1
  第 1~2 帧丢失  什么都不写（沿用上一帧掩码）
  第 3 帧起      mask=0
所以日志里应当只出现 2 条 mask=0，且出现在第 8、9 帧（0 基）之后。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath("."))
import flicker_probe as fp

W, H = fp.W, fp.H
SCENE = os.path.join("flick", "noface")
OUT = os.path.join("flick", "noface_out")
SWITCH = 6
COUNT = 12


def main():
    os.makedirs(SCENE, exist_ok=True)
    src = np.frombuffer(open(os.path.join("flick", "static", "seq_000.raw"), "rb").read(),
                        dtype=np.uint8).reshape(H, W, 4).copy()
    gray = np.zeros_like(src)
    gray[:, :, :3] = 128
    gray[:, :, 3] = 255
    for i in range(COUNT):
        (src if i < SWITCH else gray).tofile(os.path.join(SCENE, "seq_%03d.raw" % i))

    os.makedirs(OUT, exist_ok=True)
    fp.clear_logs()
    open("dump_mask.txt", "w").write("on")
    ret, msg = fp.run_seq(SCENE, OUT, "0:50,2:50,3:30,4:50")
    if os.path.exists("dump_mask.txt"):
        os.remove("dump_mask.txt")
    print("LegacySeqTest ret=%d  %s" % (ret, msg))

    lines = [l.strip() for l in open("infer_log.txt", encoding="utf-8", errors="replace")]
    print("\ninfer_log.txt（共 %d 行）:" % len(lines))
    for l in lines:
        print("  " + l)

    zeros = [l for l in lines if "mask=0" in l]
    print("\n掩码丢失帧数 %d（期望 %d：第 %d 帧起连续 2 帧被保持吃掉）"
          % (len(zeros), COUNT - SWITCH - 2, SWITCH))
    if zeros:
        first = int(zeros[0].split("frame=")[1].split()[0])
        print("  首次 mask=0 出现在第 %d 帧（期望 %d）" % (first, SWITCH + 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
