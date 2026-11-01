# -*- coding: utf-8 -*-
"""探针：fuai.dll 能否直接吃随包分发的加密 bundle（非 Zip）。"""
import ctypes
import os
import sys

FUAI = r"C:/Program Files/obs-studio/obs-plugins/64bit/obs-beauty/fuai.dll"
BUNDLE = r"C:/Program Files/obs-studio/obs-plugins/64bit/obs-beauty/assets/model/ai_face_processor_pc.bundle"

d = open(BUNDLE, "rb").read()
print("bundle size=%d head=%s" % (len(d), d[:8].hex()))

# fuai.dll 依赖同目录其它 dll，先切进去
os.chdir(os.path.dirname(FUAI))
try:
    os.add_dll_directory(os.path.dirname(FUAI))
except Exception:
    pass

lib = ctypes.WinDLL(FUAI)
fn = lib.FUAI_NewFaceProcessorFromBundle
fn.restype = ctypes.c_void_p
fn.argtypes = [ctypes.c_char_p, ctypes.c_int]

buf = ctypes.create_string_buffer(d, len(d))
proc = fn(ctypes.cast(buf, ctypes.c_char_p), len(d))
print("FUAI_NewFaceProcessorFromBundle(encrypted) -> %r" % proc)

if proc:
    print("RESULT: 加密 bundle 可直接加载，无需明文分发")
    sys.exit(0)
else:
    print("RESULT: 加密 bundle 被拒绝，确实需要明文 bundle")
    sys.exit(2)
