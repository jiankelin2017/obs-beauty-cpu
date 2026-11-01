# -*- coding: utf-8 -*-
"""把自研 CoreEngine 在某一帧上算出的掩码落盘，并叠加到画面上看几何。"""
import ctypes, os, sys
import numpy as np
from PIL import Image

HERE = r'D:\插件\OBS美颜\06_离线验证'
CORE_DLL = os.path.join(HERE, 'beauty_core_test.dll')
os.add_dll_directory(HERE)
for sub in ('deps\\runtime\\bin', 'deps\\runtime', '_probe_run'):
    p = os.path.join(HERE, sub)
    if os.path.isdir(p):
        os.add_dll_directory(p)


def png_to_raw(png, raw, w, h):
    im = Image.open(png).convert('RGBA')
    if im.size != (w, h):
        im = im.resize((w, h), Image.LANCZOS)
    np.asarray(im, np.uint8).tofile(raw)


def dump_mask(raw, w, h, out):
    d = ctypes.WinDLL(CORE_DLL)
    d.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    d.BeautyCoreMask.restype = ctypes.c_int
    msg = ctypes.create_string_buffer(512)
    if os.path.exists(out):
        os.remove(out)
    rc = d.BeautyCoreMask(raw.encode(), w, h, out.encode(), msg, 512)
    print('BeautyCoreMask rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
    return rc


def read_mask(p):
    b = open(p, 'rb').read()
    mw, mh = np.frombuffer(b[:8], np.int32)
    return np.frombuffer(b[8:], np.uint8).reshape((mh, mw))


if __name__ == '__main__':
    src = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else 'f'
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 720
    raw = os.path.join(r'C:\btwork\mask_check', tag + '.raw')
    png_to_raw(src, raw, w, h)
    out = os.path.join(r'C:\btwork\mask_check', tag + '_core.mask')
    dump_mask(raw, w, h, out)
    m = read_mask(out)
    print('mask', m.shape, 'nonzero %.2f%%' % (100.0 * (m > 0).mean()),
          'full(>200) %.2f%%' % (100.0 * (m > 200).mean()))
