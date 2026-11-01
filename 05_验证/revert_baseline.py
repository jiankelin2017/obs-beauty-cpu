# -*- coding: utf-8 -*-
"""把 b311/ 下的测试副本精确回退成 3.0.11（无预热）基线，用于 A/B 对照。

只做三处逆向替换，每处都必须恰好命中一次，否则报错退出：
  1. legacy_region.cpp：删 kWarmupCalls/kWarmupTries 常量
  2. legacy_region.cpp：删 ensureReady 里的 warmup() 调用与注释
  3. legacy_region.cpp：删 warmup() 函数整体（含上方长注释）
  4. legacy_region.h：删 warmup() 声明
  5. legacy_engine.h：版本 3.0.12 -> 3.0.11
"""
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


# ---- 1+2+3: legacy_region.cpp ----
p = D + r"\legacy_region.cpp"
s = rd(p)

s = cut(s,
        "static const int kMaskHoldFrames = 6;\n"
        "// 3.0.12（P1）：预热推理参数。kWarmupCalls = 主动烧掉的推理次数 ——\n"
        "// 实测 fuai 早期访问违例都发生在第 2 次调用，跑满 2 次才覆盖该失败点；\n"
        "// kWarmupTries = 含重试的总尝试上限，重试不置 failed_（见 warmup()）。\n"
        "static const int kWarmupCalls = 2;\n"
        "static const int kWarmupTries = 4;\n",
        "static const int kMaskHoldFrames = 6;\n",
        "常量")

s = cut(s,
        '    ready_ = true;\n'
        '    trace("ensureReady 完成");\n'
        '\n'
        '    // 3.0.12（P1）：把 fuai 早期推理那约 10% 的访问违例在加载期烧掉。\n'
        '    // 预热失败只重试、不置 failed_；重试耗尽也保持 ready_ —— 引擎行为\n'
        '    // 与不预热完全一致，任何情况下都不会比 3.0.11 更差（详见 warmup()）。\n'
        '    warmup();\n'
        '    return true;\n'
        '}\n',
        '    ready_ = true;\n'
        '    trace("ensureReady 完成");\n'
        '    return true;\n'
        '}\n',
        "ensureReady 调用")

i = s.find("// 3.0.12（P1 方案 1）：预热推理。")
j = s.find("// 诊断自检：BEAUTY_REGION_SELFTEST=1")
if i < 0 or j < 0 or j <= i:
    print("FAIL 定位 warmup 函数失败 i=%d j=%d" % (i, j))
    sys.exit(1)
# 函数注释横幅从 i 往前一个分隔线开始
banner = "// " + "-" * 75 + "\n"
bi = s.rfind(banner, 0, i)
bj = s.rfind(banner, 0, j)
if bi < 0 or bj < 0 or bj <= bi:
    print("FAIL 定位横幅失败 bi=%d bj=%d" % (bi, bj))
    sys.exit(1)
removed = s[bi:bj]
if "bool LegacyRegion::warmup()" not in removed or "预热推理" not in removed:
    print("FAIL 待删区块内容不符")
    sys.exit(1)
print("ok warmup 函数（%d 字节）" % len(removed))
s = s[:bi] + s[bj:]
if "warmup" in s:
    print("FAIL 仍残留 warmup 字样")
    sys.exit(1)
wr(p, s)

# ---- 4: legacy_region.h ----
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

# ---- 5: legacy_engine.h 版本 ----
p = D + r"\legacy_engine.h"
s = rd(p)
s = cut(s,
        '#define BEAUTY_BUILD_PATCH 12\n#define BEAUTY_BUILD_STR "3.0.12"\n',
        '#define BEAUTY_BUILD_PATCH 11\n#define BEAUTY_BUILD_STR "3.0.11"\n',
        "版本号")

print("全部回退完成")
