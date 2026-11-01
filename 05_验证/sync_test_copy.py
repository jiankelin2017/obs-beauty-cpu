# -*- coding: utf-8 -*-
"""把生产源码同步到 C:\\legacy_e2e 测试副本，并恢复两处测试专用改动。

为什么要有这个脚本：生产源码 cp 过来会把测试钩子覆盖掉，导致测试静默退回
默认参数、得出错误结论（2026-10-24 踩过：美白 55 测出 -0.50 的怪结果）。
以后每次同步都必须跑这个脚本，不能手动 cp 了事。

做三件事：
  1. cp 生产 src/{legacy_engine,legacy_region}.{cpp,h} 到本目录
  2. 注入 panel.txt 测量钩子（inject_test_hook.py）
  3. 补上 LegacySeqTest 序列驱动器（生产源码里没有，只属于测试副本）
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = r"D:/插件/obs-beauty-filter/obs-plugin-build/src"

FILES = ["legacy_engine.cpp", "legacy_region.cpp", "legacy_engine.h", "legacy_region.h"]

SEQ_DECL = '''__declspec(dllexport) unsigned long __stdcall LegacyVersion(void);

// 测试专用（只在本副本声明）：同进程多帧序列驱动，用来验证掩码滞后。
// inDir 下需有 seq_000.raw .. seq_(count-1).raw，输出写到 outDir 同名文件。
__declspec(dllexport) int __stdcall LegacySeqTest(const char* engineDir,
                                                const char* inDir,
                                                const char* outDir,
                                                int width, int height, int count,
                                                double blur, double whiten,
                                                char* msgBuf, int msgCap);
#ifdef __cplusplus
}
#endif
'''

SEQ_DECL_OLD = '''__declspec(dllexport) unsigned long __stdcall LegacyVersion(void);
#ifdef __cplusplus
}
#endif
'''

# LegacySeqTest 的函数体：从当前测试副本里原样保留，避免每次手抄
SEQ_FUNC_MARK = "// 测试专用：多帧序列驱动"


def main():
    # 0) 先把旧的 LegacySeqTest 函数体存下来（生产源码里没有它）
    old_cpp = open(os.path.join(HERE, "legacy_engine.cpp"), "rb").read().decode("utf-8")
    seq_func = None
    if SEQ_FUNC_MARK in old_cpp:
        i = old_cpp.index("// " + "-" * 75)
        # 找到函数体起始的注释块
        start = old_cpp.rindex("// " + "-" * 75, 0, old_cpp.index(SEQ_FUNC_MARK))
        end = old_cpp.rindex("}  // extern \"C\"")
        seq_func = old_cpp[start:end]
    if seq_func:
        print("[0] 已保留旧 LegacySeqTest 函数体（%d 字节）" % len(seq_func))
    else:
        print("[0] 未找到旧 LegacySeqTest，将从内置模板生成")

    # 1) cp 生产源码
    for f in FILES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(HERE, f))
    print("[1] 已同步 %d 个生产源文件" % len(FILES))

    # 2) 注入测量钩子
    r = subprocess.run([sys.executable, os.path.join(HERE, "inject_test_hook.py")],
                       capture_output=True, text=True)
    print("[2] inject_test_hook:", r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        return 1

    # 3) 补 LegacySeqTest
    cpp = open(os.path.join(HERE, "legacy_engine.cpp"), "rb").read().decode("utf-8")
    hdr = open(os.path.join(HERE, "legacy_engine.h"), "rb").read().decode("utf-8")

    if "LegacySeqTest" not in hdr:
        if SEQ_DECL_OLD not in hdr:
            print("[3] 头部锚点没找到，手工检查")
            return 1
        hdr = hdr.replace(SEQ_DECL_OLD, SEQ_DECL, 1)
        open(os.path.join(HERE, "legacy_engine.h"), "wb").write(hdr.encode("utf-8"))
        print("[3] 已在 legacy_engine.h 声明 LegacySeqTest")

    if "LegacySeqTest" not in cpp:
        if seq_func is None:
            print("[3] 没有旧函数体可复用，且未内置模板 —— 请手工补")
            return 1
        tail = '}  // extern "C"'
        i = cpp.rindex(tail)
        cpp = cpp[:i] + seq_func + "\n" + cpp[i:]
        open(os.path.join(HERE, "legacy_engine.cpp"), "wb").write(cpp.encode("utf-8"))
        print("[3] 已在 legacy_engine.cpp 追加 LegacySeqTest")

    # 4) 自检：确认关键点开关与 kRegionEvery 与生产一致
    reg = open(os.path.join(HERE, "legacy_region.cpp"), "rb").read().decode("utf-8")
    lm = re.search(r"g_setUseLandmark\(proc_, (\d)\)", reg)
    ev = re.search(r"^const int kRegionEvery = (\d+);", cpp, re.M)
    print("[4] 自检：SetUseFaceLandmark=%s  kRegionEvery=%s"
          % (lm.group(1) if lm else "?", ev.group(1) if ev else "?"))
    if lm and lm.group(1) != "0":
        print("    !! 生产源码的关键点开关不是 0，与 2.1.1 预期不符")
    if ev and ev.group(1) != "1":
        print("    !! 生产源码的 kRegionEvery 不是 1，与 2.1.1 预期不符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
