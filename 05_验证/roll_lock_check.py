# -*- coding: utf-8 -*-
"""倾斜补偿（roll）状态机判据 —— 锁死要能放，歪着不能误放。

为什么需要它
------------
1.0.13.9 给 roll 加了一道「周期性 0° 对照」的释放门：roll 锁着的时候，每
BEAUTY_ROLL_CHECK 帧额外跑一次 0° 检测，只有 0° 的框明显更好才释放。
这道门有两个失效方向，而且方向相反：

  · 放不掉：回正后 roll 仍是 -45。框停在撑大的外接盒（离线 175x175，紧框
    107x134，面积 2.1 倍），形变方向偏约 42°。这是 1.0.5.0~1.0.13.8 的缺陷。
  · 误放：头还歪着就放了。补偿一撤，歪头又回到没有补偿的老路径。

两个方向都得单独立判据，只测其中一个会让另一个悄悄坏掉。

三个场景与判定
--------------
  R  0°→57°→0° 再保持 0° 150 帧    回正后必须释放，且必须逐帧渐变（不硬切）
  H  固定 45/50/60° 保持 150 帧     锁上之后必须一直锁着（一次都不许放）
  S  固定 20/30/35° 保持 150 帧     不该锁（小角度靠紧框就能检到，锁了反而添抖动）

R 的"逐帧渐变"单独判：释放走 startGeoFade 的 6 帧插值，单帧跳变应 ≤ 15°。
一旦某帧直接 -45→0，说明过渡被绕过，肉眼看就是闪一下。

为什么必须用同步口径
--------------------
异步（真机默认）下第 k 帧用哪份检测结果取决于线程调度，"第几帧释放"不可
复现。状态机的时序只能同步测；异步只测最终有没有释放。

用法
----
    python 05_验证/roll_lock_check.py            # 全量
    python 05_验证/roll_lock_check.py --quick    # 跳过 H/S，只测 R

退出码：0 = 全部通过；1 = 有 FAIL。
"""
import os
import sys
import ctypes

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["BEAUTY_FACE_MODEL"] = os.path.join(HERE, "models", "yunet.onnx")
os.environ["BEAUTY_ASYNC_DETECT"] = "0"       # 时序判据必须同步
os.environ.pop("BEAUTY_FACE_EMA", None)       # 关掉 EMA/hold，否则第一帧沿用旧框
os.environ.pop("BEAUTY_FACE_HOLD", None)
os.environ.setdefault("BEAUTY_ROLL_CHECK", "45")

import _warp_seam as M  # noqa: E402

W = H = 640
BASE = Image.open(M.SRCSS).convert("RGB").resize((M.W0, M.H0), Image.LANCZOS)


def canvas(angle):
    im = BASE.rotate(-angle, expand=True, fillcolor=(128, 128, 128)) if angle else BASE
    c = Image.new("RGB", (W, H), (128, 128, 128))
    c.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    a = np.asarray(c, np.uint8)
    return np.dstack([a, np.full((H, W, 1), 255, np.uint8)])


def new_slot():
    msg = ctypes.create_string_buffer(512)
    slot = M.dll.BeautyCoreAcquireSlot(msg, 512)
    for i in range(3):
        M.dll.BeautyCoreSetShape(i, 100.0)
    return slot


def step(slot, angle, rin, rout):
    """喂一帧，返回 (roll, 框w, 框h)；无脸返回 (None, None, None)。"""
    rgba = canvas(angle)
    rgba.tofile(rin)
    M.dll.BeautyCoreRunSlot(slot, rin.encode(), rout.encode(), W, H,
                            0.0, 0, 0.0, 0.0, 1,
                            ctypes.create_string_buffer(512), 512)
    buf = ctypes.create_string_buffer(1024)
    if M.dll.BeautyCoreFaceSlot(slot, buf, 1024) < 1:
        return None, None, None
    txt = buf.value.decode("gbk", "ignore")
    if "|" not in txt:
        return None, None, None
    f = M.parse_face(txt)
    return f["roll"], f["w"], f["h"]


def run_seq(slot, angles, rin, rout):
    out = []
    for a in angles:
        out.append((a,) + step(slot, a, rin, rout))
    return out


def scenario_release():
    """回正后必须释放，且逐帧渐变。"""
    slot = new_slot()
    rin = os.path.join(M.OUT, "_rl_i.raw")
    rout = os.path.join(M.OUT, "_rl_o.raw")
    seq = [0] * 12 + list(range(0, 58)) + list(range(57, -1, -1)) + [0] * 150
    rows = run_seq(slot, seq, rin, rout)

    locked_at = None
    for i, (ang, roll, _, _) in enumerate(rows):
        if roll is not None and abs(roll) > 1.0:
            locked_at = i
    if locked_at is None:
        print("FAIL  R: 全程没锁上 roll —— 素材/角度或 BEAUTY_AUTO_ROLL 有问题")
        return False

    tail = rows[-150:]
    rel_idx = None
    for j, (ang, roll, _, _) in enumerate(tail):
        if roll is not None and abs(roll) < 1.0:
            rel_idx = j
            break
    if rel_idx is None:
        last = [r[1] for r in tail[-5:]]
        print("FAIL  R: 回正后 150 帧仍无释放，末帧 roll=%s" % last)
        return False

    # 释放过程逐帧角度（从锁定到 0 的过渡段）
    trans = [r[1] for r in tail[max(0, rel_idx - 8):rel_idx + 1] if r[1] is not None]
    jumps = [abs(b - a) for a, b in zip(trans, trans[1:])]
    max_jump = max(jumps) if jumps else 0.0
    ok_gradual = max_jump <= 15.0
    roll_end = tail[-1][1]
    w_end, h_end = tail[-1][2], tail[-1][3]

    print("PASS  R: 回正后第 %d 帧释放（BEAUTY_ROLL_CHECK=%s）"
          % (rel_idx, os.environ.get("BEAUTY_ROLL_CHECK")))
    print("         末帧 roll=%.1f 框=%.1fx%.1f" % (roll_end, w_end, h_end))
    print("         过渡逐帧 %s  最大单帧跳变 %.1f° %s"
          % ("/".join("%.0f" % x for x in trans), max_jump,
             "OK" if ok_gradual else "<<< 硬切"))
    if not ok_gradual:
        print("FAIL  R: 释放是硬切，不是 6 帧渐变 —— 会闪一下")
    return ok_gradual and abs(roll_end) < 1.0


def scenario_hold(angle, frames=150):
    """固定歪角保持，锁上后不许放。"""
    slot = new_slot()
    rin = os.path.join(M.OUT, "_rh_i.raw")
    rout = os.path.join(M.OUT, "_rh_o.raw")
    rows = run_seq(slot, [angle] * frames, rin, rout)
    rolls = [r[1] for r in rows]
    if all(r is None or abs(r) < 1.0 for r in rolls):
        print("SKIP  H%.0f: 该角度不触发锁定（紧框已能检到），无从误放" % angle)
        return True
    # 锁定之后是否出现回到 0
    first_lock = next(i for i, r in enumerate(rolls) if r is not None and abs(r) > 1.0)
    after = rolls[first_lock:]
    rel = [i + first_lock for i, r in enumerate(after) if r is not None and abs(r) < 1.0]
    if rel:
        print("FAIL  H%.0f: 头始终歪着，第 %s 帧却把补偿释放了（误放）"
              % (angle, rel[:5]))
        return False
    print("PASS  H%.0f: %d 帧全程锁定 roll=%.1f，无误放" % (angle, frames, rolls[-1]))
    return True


def scenario_small(angle, frames=120):
    """小角度不该锁。"""
    slot = new_slot()
    rin = os.path.join(M.OUT, "_rs_i.raw")
    rout = os.path.join(M.OUT, "_rs_o.raw")
    rows = run_seq(slot, [angle] * frames, rin, rout)
    rolls = [r[1] for r in rows if r[1] is not None]
    if not rolls:
        print("SKIP  S%.0f: 无脸" % angle)
        return True
    mx = max(abs(r) for r in rolls)
    if mx > 1.0:
        print("FAIL  S%.0f: 小角度锁了 roll=%.1f —— 无谓加一层补偿与切换" % (angle, mx))
        return False
    print("PASS  S%.0f: %d 帧 roll 恒 0（不锁）" % (angle, frames))
    return True


def main():
    quick = "--quick" in sys.argv
    ok = True
    ok &= scenario_release()
    if not quick:
        for a in (45.0, 50.0, 60.0):
            ok &= scenario_hold(a)
        for a in (20.0, 30.0, 35.0):
            ok &= scenario_small(a)
    print("\n=== %s ===" % ("全部通过" if ok else "存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
