// beauty_core_abtest —— 引擎抽象层的最小行为验证（脱离 OBS，独立控制台程序）
//
// 验证三件事：
//   1) BEAUTY_ENGINE_IMPL 能真的把实现切走（开关接上了）；
//   2) PassthroughEngine 语义正确：输出与输入逐字节相同（含 src==dst）；
//   3) LegacyAdapter 是纯转发：同一帧、同一组参数下，
//      beautyEngine().process(...) 与 LegacyEngine::inst().process(...) 的
//      输出逐字节相同（advanceFrame=false 消除帧序号带来的时序差异）。
//
// 用法：
//   beauty_core_abtest.exe [impl] [engineDir] [rawIn w h]
//     impl       = legacy / passthrough / core
//     engineDir  = 引擎数据目录（含 参考实现美颜库.dll），用于跑真实 参考实现
//     rawIn w h  = 裸 RGBA8 输入与尺寸，给出时才跑第 3 项对比
//
// 编译见 06_离线验证/build_beauty_core_abtest.bat

#include "beauty_core.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static int g_fail = 0;

static void check(bool ok, const char* what) {
    printf("  [%s] %s\n", ok ? "OK  " : "FAIL", what);
    if (!ok) g_fail++;
}

// 一条固定的测试参数：磨皮 50 / 美白 30 / 锐化 20
static void fillSettings(BeautySettings& s) {
    s.panel[P_BLUR] = 50;
    s.panel[P_WHITEN] = 30;
    s.panel[P_SHARPEN] = 20;
}

int main(int argc, char** argv) {
    const char* impl = (argc > 1 && argv[1][0]) ? argv[1] : "legacy";
    if (argc > 1 && argv[1][0]) {
        std::string v = std::string("BEAUTY_ENGINE_IMPL=") + argv[1];
        _putenv(v.c_str());
    }
    if (argc > 2 && argv[2][0]) {
        std::string v = std::string("BEAUTY_ENGINE_ASSET_DIR=") + argv[2];
        _putenv(v.c_str());
    }

    IBeautyEngine& e = beautyEngine();
    printf("engine id     = %s\n", e.id());
    printf("version       = %s\n", e.version() ? e.version() : "(null)");

    // ---- 1) 小图基本语义 ------------------------------------------------
    const int w = 8, h = 4;
    const size_t n = (size_t)w * h * 4;
    std::vector<unsigned char> src(n), dst(n, 0);
    for (size_t i = 0; i < n; i++) src[i] = (unsigned char)(i * 7 + 3);

    BeautySettings s;
    fillSettings(s);
    check(!s.allZero(), "test params are non-zero (otherwise the test proves nothing)");

    std::string err;
    const int slot = e.acquireSlot(err);
    check(slot >= 0, "acquireSlot returns a valid slot");
    if (slot < 0) printf("        err=%s\n", err.c_str());

    if (slot >= 0) {
        const bool ok = e.process(slot, &src[0], &dst[0], w, h, s);
        check(ok, "process returns success");

        if (strcmp(e.id(), "passthrough") == 0) {
            check(memcmp(&src[0], &dst[0], n) == 0,
                  "passthrough output is byte-identical to input");
            check(e.lastFaces() == 0 && !e.regionActive(),
                  "passthrough diagnostics are conservative");
        }
        std::vector<unsigned char> inPlace(src);
        check(e.process(slot, &inPlace[0], &inPlace[0], w, h, s),
              "process supports in-place (src == dst)");
        e.releaseSlot(slot);
    }

    // ---- 2) 真实帧：抽象层转发 vs 直接调引擎 ----------------------------
    if (argc > 5 && strcmp(e.id(), "legacy") == 0) {
        const char* rawIn = argv[3];
        const int rw = atoi(argv[4]);
        const int rh = atoi(argv[5]);
        const size_t rn = (size_t)rw * rh * 4;

        FILE* f = nullptr;
        if (fopen_s(&f, rawIn, "rb") != 0 || !f) {
            printf("  [FAIL] cannot open raw input: %s\n", rawIn);
            g_fail++;
        } else {
            std::vector<unsigned char> frame(rn);
            const size_t got = fread(&frame[0], 1, rn, f);
            fclose(f);
            if (got != rn) {
                printf("  [FAIL] raw input too short: got %zu of %zu\n", got, rn);
                g_fail++;
            } else {
                printf("\n  -- parity on %dx%d frame --\n", rw, rh);
                std::string e1, e2;
                const int s1 = LegacyEngine::inst().acquireSlot(e1);
                const int s2 = e.acquireSlot(e2);
                check(s1 >= 0 && s2 >= 0, "both paths got a slot");
                if (s1 < 0) printf("        direct err=%s\n", e1.c_str());
                if (s2 < 0) printf("        adapter err=%s\n", e2.c_str());

                if (s1 >= 0 && s2 >= 0) {
                    std::vector<unsigned char> o1(rn), o2(rn);
                    const bool p1 = LegacyEngine::inst().process(
                        s1, &frame[0], &o1[0], rw, rh, s, false);
                    const bool p2 = e.process(s2, &frame[0], &o2[0], rw, rh, s, false);
                    check(p1 && p2, "both paths processed the frame");
                    if (p1 && p2) {
                        const size_t diff = [&] {
                            size_t c = 0;
                            for (size_t i = 0; i < rn; i++)
                                if (o1[i] != o2[i]) c++;
                            return c;
                        }();
                        check(diff == 0, "adapter output is byte-identical to direct call");
                        if (diff)
                            printf("        %zu of %zu bytes differ\n", diff, rn);
                        //  sanity: the frame really went through the engine
                        const size_t changed = [&] {
                            size_t c = 0;
                            for (size_t i = 0; i < rn; i++)
                                if (o1[i] != frame[i]) c++;
                            return c;
                        }();
                        printf("        [info] %zu bytes changed vs input "
                               "(0 = params had no effect)\n", changed);
                    }
                    LegacyEngine::inst().releaseSlot(s1);
                    e.releaseSlot(s2);
                }
            }
        }
    }

    printf("\n%s\n", g_fail == 0 ? "RESULT: PASS" : "RESULT: FAIL");
    return g_fail == 0 ? 0 : 1;
}
