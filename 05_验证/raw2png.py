# -*- coding: utf-8 -*-
"""raw RGBA -> PNG（无第三方依赖，纯 zlib + struct）。

用法: python raw2png.py in.raw w h out.png
"""
import struct
import sys
import zlib


def write_png(path, w, h, rgba):
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0
        raw += rgba[y * w * 4:(y + 1) * w * 4]
    comp = zlib.compress(bytes(raw), 6)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    open(path, "wb").write(png)
    print("wrote %s  %dx%d  %d bytes" % (path, w, h, len(png)))


if __name__ == "__main__":
    src, w, h, dst = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    d = open(src, "rb").read()
    assert len(d) == w * h * 4, (len(d), w * h * 4)
    write_png(dst, w, h, d)
