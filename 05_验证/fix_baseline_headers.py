# -*- coding: utf-8 -*-
"""补写 revert_baseline.py 漏掉的两次 wr()：只处理两个头文件。"""
import io
import sys

D = r"C:\legacy_e2e\b311"


def rd(p):
    with io.open(p, "r", encoding="utf-8") as f:
        return f.read()


def wr(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def cut(s, old, new, what):
    n = s.count(old)
    if n != 1:
        print("FAIL %s: 命中 %d 次（要求 1）" % (what, n))
        sys.exit(1)
    print("ok %s" % what)
    return s.replace(old, new, 1)


p = D + r"\legacy_region.h"
s = rd(p)
s = cut(s,
        "    bool inferOnce(const unsigned char* rgba, int w, int h);\n"
        "    // 3.0.12（P1）：ensureReady 成功后的预热推理（见 .cpp 长注释）。\n"
        "    // 直接调 seh* 裸封装跑满 kWarmupCalls 次干净推理，把 fuai 早期的\n"
        "    // 访问违例在加载期烧掉；失败只重试，不置 failed_、不碰掩码状态。\n"
        "    bool warmup();\n",
        "    bool inferOnce(const unsigned char* rgba, int w, int h);\n",
        "头文件声明")
wr(p, s)

p = D + r"\legacy_engine.h"
s = rd(p)
s = cut(s,
        '#define BEAUTY_BUILD_PATCH 12\n#define BEAUTY_BUILD_STR "3.0.12"\n',
        '#define BEAUTY_BUILD_PATCH 11\n#define BEAUTY_BUILD_STR "3.0.11"\n',
        "版本号")
wr(p, s)

print("补写完成")
