# -*- coding: utf-8 -*-
"""从 nz_probe_nodel.py 生成带 DLL 搜索路径的探针副本 nz_probe_dlldir.py。

完整插件 DLL 依赖 obs.dll（OBS 安装目录）与 fuai.dll（插件数据目录），
原探针直接 ctypes.WinDLL 会报 FileNotFoundError。
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "nz_probe_nodel.py")
DST = os.path.join(HERE, "nz_probe_dlldir.py")

PATHS = [
    r"C:\Program Files\obs-studio\bin\64bit",
    r"C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty",
]

INSERT = "\n".join([
    "",
    "# --- dll 目录补丁：让完整插件 DLL（依赖 obs.dll / fuai.dll）可加载 ---",
    "_dll_dirs = []",
    "for _p in %r:" % (PATHS,),
    "    try:",
    "        _dll_dirs.append(os.add_dll_directory(_p))",
    "    except Exception:",
    "        pass",
    "",
])

with io.open(SRC, encoding="utf-8") as f:
    src = f.read()

anchor = "from measure_whiten_fixed import read_png_rgba"
assert anchor in src, "anchor not found"
src = src.replace(anchor, anchor + "\n" + INSERT, 1)

with io.open(DST, "w", encoding="utf-8") as f:
    f.write(src)

print("wrote", DST)
