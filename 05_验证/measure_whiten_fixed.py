# -*- coding: utf-8 -*-
"""在**固定的输入皮肤像素集**上测美白前后的亮度变化。

measure_whiten.py 会在输出图上重新跑一遍 YCbCr 肤色判据，而美白会把一部分
像素推出判据范围，导致输出均值只统计「没被美白到的像素」—— 越美白偏差越大。
这里改成用输入那次判据得到的像素集，输出也在同一个集合上取均值。
"""
import ctypes
import os
import struct
import sys

DLL = r"C:/legacy_e2e/legacy_engine_test.dll"
ASSET_DIR = r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty"
OUT = r"C:/legacy_e2e/out"


def read_png_rgba(path):
    """最小 PNG 解码：只支持 8-bit RGB/RGBA 非隔行。"""
    d = open(path, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    idat = b""
    w = h = bd = ct = None
    while pos < len(d):
        ln = struct.unpack(">I", d[pos:pos + 4])[0]
        typ = d[pos + 4:pos + 8]
        data = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct = struct.unpack(">IIBB", data[:10])
        elif typ == b"IDAT":
            idat += data
        elif typ == b"IEND":
            break
        pos += 12 + ln
    import zlib
    raw = zlib.decompress(idat)
    nch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    assert bd == 8, bd
    stride = w * nch
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if f == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        for x in range(w):
            s = x * nch
            o = (y * w + x) * 4
            if nch == 1:
                out[o] = out[o + 1] = out[o + 2] = line[s]
            elif nch == 2:
                out[o] = out[o + 1] = out[o + 2] = line[s]
            elif nch == 3:
                out[o], out[o + 1], out[o + 2] = line[s], line[s + 1], line[s + 2]
            else:
                out[o], out[o + 1], out[o + 2] = line[s], line[s + 1], line[s + 2]
            out[o + 3] = 255
        prev = line
    return bytes(out), w, h


def is_skin(r, g, b):
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b
    if y < 30 or not (77 <= cb <= 127) or not (133 <= cr <= 173):
        return False
    mx, mn = max(r, g, b), min(r, g, b)
    if mx > 0 and (mx - mn) / mx > 0.55:
        return False
    return True


def main():
    img = sys.argv[1]
    rgba, w, h = read_png_rgba(img)
    os.makedirs(OUT, exist_ok=True)
    raw_in = os.path.join(OUT, "_fx_in.raw")
    raw_out = os.path.join(OUT, "_fx_out.raw")
    open(raw_in, "wb").write(rgba)

    # 输入皮肤像素集（固定，之后都在这个集合上取均值）
    skin = []
    for i in range(w * h):
        o = i * 4
        if is_skin(rgba[o], rgba[o + 1], rgba[o + 2]):
            skin.append(i)
    print("固定皮肤像素集：%d / %d (%.1f%%)" % (len(skin), w * h, 100.0 * len(skin) / (w * h)))

    print("")
    print("美白  皮肤平均亮度   变化      皮肤平均R   变化")
    print("-" * 52)
    for v in (0, 25, 55, 100):
        open(r"C:/legacy_e2e/panel.txt", "w").write("2:%d" % v)
        dll = ctypes.WinDLL(DLL)
        dll.LegacySelfTest.restype = ctypes.c_int
        dll.LegacySelfTest.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double,
            ctypes.c_char_p, ctypes.c_int]
        msg = ctypes.create_string_buffer(2048)
        ret = dll.LegacySelfTest(ASSET_DIR.encode("ascii"), raw_in.encode("ascii"),
                               raw_out.encode("ascii"), w, h, 0.0, 0.0, msg, 2048)
        if ret != 0:
            print("FAIL", msg.value.decode("utf-8", "replace"))
            return 1
        b = open(raw_out, "rb").read()
        sl = sr = 0.0
        for i in skin:
            o = i * 4
            sl += 0.299 * b[o] + 0.587 * b[o + 1] + 0.114 * b[o + 2]
            sr += b[o]
        l0 = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
        # 输入的基准
        sl0 = sr0 = 0.0
        for i in skin:
            o = i * 4
            sl0 += 0.299 * rgba[o] + 0.587 * rgba[o + 1] + 0.114 * rgba[o + 2]
            sr0 += rgba[o]
        n = len(skin)
        print("%-5d %10.2f  %+7.2f  %9.2f  %+7.2f"
              % (v, sl / n, sl / n - sl0 / n, sr / n, sr / n - sr0 / n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
