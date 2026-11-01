# -*- coding: utf-8 -*-
"""mk_mask.py —— 单独导出 SDK 的肤色掩码（LegacyRegion）。

为什么需要单独一个脚本
----------------------
`RefGoldenRun` 能直接吃**加密** bundle（= 第三方产品实际加载的那个文件），
但 `LegacyRegion`（肤色检测）只认**明文 ZIP** bundle，两者不能共用同一个
engine 目录 —— 用加密件调 `BeautyDumpMask` 会返回 `rc=5
region unavailable: bundle 不是明文 Zip`。

明文 / 加密两个 bundle 的渲染结果已实测**逐字节等价**
（`06_离线验证/goldens_encrypted/README.md`，四路 md5 全 diff=0），
所以「金标用加密引擎、掩码用明文引擎」不影响任何结论。

用法
----
    python mk_mask.py --engine "C:\\\\btwork_plain\\\\engine" ^
        --raw goldens/real/cam_in.raw --out goldens/real/cam_fuai.mask --w 1920 --h 1080

输出格式：`[int32 w][int32 h]` + w*h 字节掩码（0..255）。
"""
import argparse
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD_DLL = os.path.join(HERE, 'ref_golden.dll')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', required=True, help='含明文 bundle 的 engine 目录')
    ap.add_argument('--raw', required=True, help='输入 RGBA raw（w*h*4）')
    ap.add_argument('--out', required=True, help='输出 .mask 路径')
    ap.add_argument('--w', type=int, default=1920)
    ap.add_argument('--h', type=int, default=1080)
    args = ap.parse_args()

    if not os.path.exists(args.raw):
        raise SystemExit('缺输入 %s' % args.raw)
    need = args.w * args.h * 4
    if os.path.getsize(args.raw) != need:
        raise SystemExit('%s 大小 %d，期望 %d'
                         % (args.raw, os.path.getsize(args.raw), need))
    if os.path.exists(args.out):
        os.remove(args.out)

    d = ctypes.WinDLL(GOLD_DLL)
    d.BeautyDumpMask.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    d.BeautyDumpMask.restype = ctypes.c_int

    msg = ctypes.create_string_buffer(512)
    rc = d.BeautyDumpMask(args.engine.encode('utf-8'), args.raw.encode('utf-8'),
                          args.w, args.h, args.out.encode('utf-8'), msg, 512)
    txt = msg.value.decode('utf-8', 'replace')
    print('BeautyDumpMask rc=%d  %s' % (rc, txt))
    if rc != 0:
        return rc
    if not os.path.exists(args.out):
        raise SystemExit('rc=0 但没有产出文件')
    raw = open(args.out, 'rb').read()
    import struct
    mw, mh = struct.unpack('<2i', raw[:8])
    n = raw[8:]
    nz = sum(1 for b in n if b > 127)
    print('掩码 : %dx%d，取值 >127 的像素 %d（%.2f%%）'
          % (mw, mh, nz, 100.0 * nz / len(n) if n else 0.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
