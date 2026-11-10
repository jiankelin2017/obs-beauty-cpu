# -*- coding: utf-8 -*-
"""端到端验证：不经 OBS，直接驱动引擎跑 加载->初始化->渲染->落盘。

用法: python e2e_run.py <blur> <whiten> <out.raw> [region_off]
"""
import ctypes
import os
import sys

ASSET_DIR = os.path.join(os.path.expanduser("~"), "WorkBuddy AI/2026-10-24-14-50-29/legacy_e2e")
DLL = r"C:/legacy_e2e/legacy_engine_test.dll"
IN_RAW = os.path.join(ASSET_DIR, "probe_in.raw")
W, H = 640, 394


def main():
    blur = float(sys.argv[1])
    whiten = float(sys.argv[2])
    out_raw = sys.argv[3]
    region_off = len(sys.argv) > 4 and sys.argv[4] == "region_off"
    if region_off:
        os.environ["BEAUTY_REGION_OFF"] = "1"
    else:
        os.environ.pop("BEAUTY_REGION_OFF", None)

    dll = ctypes.WinDLL(DLL)
    dll.LegacySelfTest.restype = ctypes.c_int
    dll.LegacySelfTest.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
        ctypes.c_double, ctypes.c_double,
        ctypes.c_char_p, ctypes.c_int,
    ]
    msg = ctypes.create_string_buffer(1024)
    ret = dll.LegacySelfTest(
        ASSET_DIR.encode("ascii"), IN_RAW.encode("ascii"), out_raw.encode("ascii"),
        W, H, blur, whiten, msg, 1024)
    print("ret=%d msg=%s" % (ret, msg.value.decode("utf-8", "replace")))
    if ret != 0:
        sys.exit(ret)

    a = open(IN_RAW, "rb").read()
    b = open(out_raw, "rb").read()
    assert len(a) == len(b) == W * H * 4, (len(a), len(b))
    n = len(a) // 4
    changed = 0
    heavy = 0
    sum_abs = 0
    max_abs = 0
    for i in range(n):
        o = i * 4
        d = 0
        for c in range(3):
            dd = abs(a[o + c] - b[o + c])
            d = max(d, dd)
            sum_abs += dd
            if dd > max_abs:
                max_abs = dd
        if d > 4:
            changed += 1
        if d > 16:
            heavy += 1
    print("pixels=%d changed(>4)=%d (%.2f%%) heavy(>16)=%d (%.2f%%) mean|d|=%.3f max|d|=%d"
          % (n, changed, 100.0 * changed / n, heavy, 100.0 * heavy / n,
             sum_abs / (n * 3.0), max_abs))


if __name__ == "__main__":
    main()
