# -*- coding: utf-8 -*-
"""feather_ab.py —— 3.1.9/3.1.10 掩码边界羽化的 A/B（跨进程）

为什么必须跨进程：`BEAUTY_MASK_FEATHER` 在 `ensureReady()` 里读一次，
同一进程内改 `os.environ` 不一定能传进 DLL 的 CRT（实测就没传进去）。
所以 dump 的 on/off 两趟**各自 fork 一个子进程**，由子进程自己设环境
变量再加载 DLL —— 主进程什么都不用设，也不会再出现「两趟一样、
cmp 报羽化没生效」的假阴性。

用法：
    python feather_ab.py dump on      # 默认羽化（3.1.10：8% 脸宽，smoothstep）
    python feather_ab.py dump off     # BEAUTY_MASK_FEATHER=0（= 3.1.8 的硬边）
    python feather_ab.py cmp          # 比两份掩码

判据（3.1.10 实测值，改动羽化后应重新核）：
    受影响像素  ~14% 的掩码像素（8% 斜坡;3.1.9 的 12% 是 ~21%）
    掩码总能量  -6.3% 左右（3.1.9 的 12% 是 -10%，真机反馈"效果弱了较多"）
    斜坡宽度    8% 脸宽（720p 脸宽≈200px → 16px），单调无台阶；
                脖子通道按脖子自身半宽 ×8% 起 ramp，不再吃脸宽
"""
import ctypes
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "beauty_core_test.dll")
RES = os.path.join(HERE, "goldens", "res")
SIZES = [("640x394", 640, 394), ("720p", 1280, 720), ("1080p", 1920, 1080)]


def mask_path(name, tag):
    return os.path.join(RES, "_feather_%s_%s.raw" % (name, tag))


def load(path, w, h):
    # 输出是 8 字节头 (int32 w, int32 h) + w*h 掩码
    return np.fromfile(path, dtype=np.uint8)[8:8 + w * h].reshape(h, w)


def subprocess_dump(tag):
    """在一个干净子进程里跑单趟 dump：环境变量在子进程启动时继承，最可靠。
    off 趟设 BEAUTY_MASK_FEATHER=0；on 趟清掉这个变量走默认 8%。"""
    env = dict(os.environ)
    env.pop("BEAUTY_MASK_FEATHER", None)
    if tag == "off":
        env["BEAUTY_MASK_FEATHER"] = "0"
    elif tag != "on":
        raise SystemExit("tag 必须是 on 或 off")
    subprocess.call([sys.executable, os.path.abspath(__file__), "_do_dump", tag],
                    env=env, cwd=HERE)


def do_dump(tag):
    import ctypes
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_char_p,
                                   ctypes.c_int]
    dll.BeautyCoreMask.restype = ctypes.c_int
    for name, w, h in SIZES:
        raw = os.path.join(RES, name + ".raw")
        if not os.path.exists(raw):
            raise SystemExit("missing %s - run verify_roi.py first" % raw)
        out = mask_path(name, tag)
        msg = ctypes.create_string_buffer(512)
        rc = dll.BeautyCoreMask(raw.encode("utf-8"), w, h, out.encode("utf-8"),
                                msg, 512)
        if rc != 0:
            raise SystemExit("rc=%d %s" % (rc, msg.value.decode("utf-8", "replace")))
        m = load(out, w, h)
        print("%-8s %-4s mask_px=%-7d sum=%d"
              % (name, tag, int((m > 0).sum()), int(m.astype(np.int64).sum())))


def do_cmp():
    for name, w, h in SIZES:
        a = load(mask_path(name, "on"), w, h).astype(np.int16)
        b = load(mask_path(name, "off"), w, h).astype(np.int16)
        d = a - b
        changed = int((d != 0).sum())
        nz = int((b > 0).sum())
        print("== %s  mask_px=%d  changed=%d (%.1f%%)  maxdiff=%d"
              % (name, nz, changed, 100.0 * changed / max(nz, 1),
                 int(np.abs(d).max()) if changed else 0))
        if not changed:
            print("   !! 羽化没有生效 —— 先确认 build_core_test.bat 重建过")
            continue
        ys, xs = np.nonzero(d)
        print("   bbox x=%d..%d y=%d..%d" % (xs.min(), xs.max(), ys.min(), ys.max()))
        cy = int(ys.mean())
        idx = np.nonzero(d[cy])[0]
        if len(idx):
            step = max(1, len(idx) // 14)
            print("   y=%d  x=%d..%d  (off>on)" % (cy, idx.min(), idx.max()))
            print("     " + "  ".join("%d>%d" % (b[cy, x], a[cy, x])
                                      for x in range(idx.min(), idx.max() + 1, step)))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "dump":
        subprocess_dump(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "_do_dump":
        do_dump(sys.argv[2])
    else:
        do_cmp()
