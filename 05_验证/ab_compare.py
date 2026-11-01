# -*- coding: utf-8 -*-
"""决定性 A/B：同一段序列，2.1.0 配置 vs 2.1.1 配置，逐帧对比输出。

对同一个输入帧，两种配置的掩码相同（已证实逐比特一致），所以输出差异只来自
「掩码是新的还是旧 2 帧」。要找的是：2.1.1 的输出里是否出现了 2.1.0 没有的
极端值（0 或 255），以及差异是否集中在脸颊一带。

用法:
  python ab_compare.py save210     # 切到 2.1.0 配置，跑，存结果
  python ab_compare.py compare     # 与已存的 2.1.1 结果对比
"""
import ctypes
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "legacy_engine_test.dll")
ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
IN_DIR = os.path.join(HERE, "ab_in")
W, H = 640, 394
N = 24
STEP = 6          # 每帧 6px，接近真实头部晃动速度

BASE = open(os.path.join(HERE, "probe_in.raw"), "rb").read()
assert len(BASE) == W * H * 4
PANEL = "0:75,2:55,3:30,4:75"


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
    if os.path.isdir(IN_DIR):
        shutil.rmtree(IN_DIR)
    os.makedirs(IN_DIR)
    for k in range(N):
        open(os.path.join(IN_DIR, "seq_%03d.raw" % k), "wb").write(shifted(k * STEP))


def run(tag):
    outdir = os.path.join(HERE, "ab_out_" + tag)
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir)
    open(os.path.join(HERE, "panel.txt"), "w").write(PANEL)
    dll = ctypes.WinDLL(DLL)
    dll.LegacySeqTest.restype = ctypes.c_int
    dll.LegacySeqTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int]
    msg = ctypes.create_string_buffer(2048)
    ret = dll.LegacySeqTest(ASSET_DIR.encode(), IN_DIR.encode(), outdir.encode(),
                          W, H, N, 75.0, 55.0, msg, 2048)
    print("  [%s] ret=%d %s" % (tag, ret, msg.value.decode("utf-8", "replace")[:100]))
    return [open(os.path.join(outdir, "seq_%03d.raw" % k), "rb").read()
            for k in range(N)] if ret == 0 else None


def set_config(landmark, every):
    """改测试副本的两个开关并重编。"""
    cpp = os.path.join(HERE, "legacy_engine.cpp")
    d = open(cpp, "rb").read().decode("utf-8")
    import re
    d = re.sub(r"g_setUseLandmark\(proc_, \d\)", "g_setUseLandmark(proc_, %d)" % landmark, d)
    d = re.sub(r"^const int kRegionEvery = \d+;", "const int kRegionEvery = %d;" % every,
               d, flags=re.M)
    open(cpp, "wb").write(d.encode("utf-8"))
    r = subprocess.run(["cmd", "/c", "build_test.bat"], cwd=HERE,
                       capture_output=True)
    ok = b"OK" in r.stdout
    print("  rebuild(landmark=%d, every=%d) -> %s" % (landmark, every, "OK" if ok else "FAIL"))
    return ok


def stats(frames, tag):
    """纯黑/纯白/极暗/极亮像素计数，以及它们在帧间的跳变。"""
    print("")
    print("--- %s ---" % tag)
    for name, pred in (
        ("纯黑 0,0,0", lambda b, o: b[o] == 0 and b[o+1] == 0 and b[o+2] == 0),
        ("纯白 255", lambda b, o: b[o] == 255 and b[o+1] == 255 and b[o+2] == 255),
        ("极暗 <=2", lambda b, o: b[o] <= 2 and b[o+1] <= 2 and b[o+2] <= 2),
        ("极亮 >=253", lambda b, o: b[o] >= 253 and b[o+1] >= 253 and b[o+2] >= 253),
    ):
        cnt = []
        for b in frames:
            n = 0
            for i in range(W * H):
                if pred(b, i * 4):
                    n += 1
            cnt.append(n)
        jumps = [abs(cnt[k] - cnt[k-1]) for k in range(1, len(cnt))]
        print("  %-12s 每帧 min=%7d max=%7d  帧间跳变 max=%7d"
              % (name, min(cnt), max(cnt), max(jumps) if jumps else 0))
    return None


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    build_seq()
    if what in ("save210", "all"):
        print("=== 切到 2.1.0 配置（关键点ON + every=3）===")
        if not set_config(1, 3):
            return 1
        a = run("210")
        if a:
            stats(a, "2.1.0 关键点ON + every=3")
    if what in ("save211", "all"):
        print("")
        print("=== 切回 2.1.1 配置（关键点OFF + every=1）===")
        if not set_config(0, 1):
            return 1
        b = run("211")
        if b:
            stats(b, "2.1.1 关键点OFF + every=1")
    if what == "compare":
        a = [open(os.path.join(HERE, "ab_out_210", "seq_%03d.raw" % k), "rb").read()
             for k in range(N)]
        b = [open(os.path.join(HERE, "ab_out_211", "seq_%03d.raw" % k), "rb").read()
             for k in range(N)]
        print("=== 逐帧差异（2.1.1 相对 2.1.0）===")
        for k in range(N):
            d = 0
            extreme_new = 0
            for i in range(W * H):
                o = i * 4
                m = max(abs(b[k][o] - a[k][o]), abs(b[k][o+1] - a[k][o+1]),
                        abs(b[k][o+2] - a[k][o+2]))
                if m > 30:
                    d += 1
                # 2.1.1 是极端值而 2.1.0 不是
                be = (b[k][o] <= 2 or b[k][o] >= 253)
                ae = (a[k][o] <= 2 or a[k][o] >= 253)
                if be and not ae:
                    extreme_new += 1
            print("  帧 %2d: 差异>30 的像素 %6d   2.1.1 新增极端值 %5d" % (k, d, extreme_new))


if __name__ == "__main__":
    sys.exit(main())
