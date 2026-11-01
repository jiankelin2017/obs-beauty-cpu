// preheat_probe —— 一次性验证：CoreEngine 的 preheat() 是否真的把人脸模型加载起来
//
// 背景（滤镜 3.1.4 修的那个 bug）：
//   CoreEngine::preheat() 原来是空壳，只 err.clear() 就 return true；而 ensureReady()
//   是唯一做 face_.load() 的地方，obs-beauty.cpp 又从不直接调它。结果 OBS 里
//   faceOk_ 恒 false → updateMask() 第一句 return false → 磨皮退回全帧、
//   清晰/美白/红润/五官五项/脸内锐化全部不执行（面板 11 项只剩 2 项）。
//
// 这个探针就是那个回归的守门人：preheat 之后 regionActive() 必须是 1。
// 它跑的是插件里同一份 beauty_core.cpp，区别只是不经过 OBS。
//
// 用法：preheat_probe.exe
//   必须放在含 onnxruntime.dll 的目录里（selfDir() 按 exe 所在目录找 ORT），
//   并用 BEAUTY_FACE_MODEL 指向 yunet.onnx。

#include "beauty_core.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static int g_fail = 0;

static void check(bool ok, const char* what) {
    printf("  [%s] %s\n", ok ? "OK  " : "FAIL", what);
    if (!ok) g_fail++;
}

int main() {
    // 默认引擎断言（3.1.7 起是 core）。PROBE_KEEP_IMPL=1 时不覆盖环境变量，
    // 用来验证「不设 BEAUTY_ENGINE_IMPL 时到底走哪个引擎」—— 那是切换默认引擎
    // 唯一能被自动断言的证据，光看源码注释不算。
    const bool keepImpl = getenv("PROBE_KEEP_IMPL") != nullptr;
    if (!keepImpl) _putenv("BEAUTY_ENGINE_IMPL=core");

    IBeautyEngine& e = beautyEngine();
    printf("engine        = %s / %s%s\n", e.id(), e.version() ? e.version() : "(null)",
           keepImpl ? "   (env not overridden)" : "");
    if (keepImpl) {
        // 只有「真的没设 BEAUTY_ENGINE_IMPL」时这条才代表默认值；若外层显式设了
        // nama / passthrough，FAIL 是预期的（这里只是把实际值打出来）。
        char buf[160];
        snprintf(buf, sizeof(buf),
                 "默认引擎是 core（未设 BEAUTY_ENGINE_IMPL 时），实际拿到 '%s'", e.id());
        check(strcmp(e.id(), "core") == 0, buf);
    } else {
        check(strcmp(e.id(), "core") == 0, "engine impl is core");
    }

    // ---- 1) preheat 必须真的初始化，并且报 didInit=1 ---------------------
    std::string err;
    bool didInit = false;
    const DWORD t0 = GetTickCount();
    const bool ok = e.preheat(err, didInit);
    const DWORD dt = GetTickCount() - t0;

    printf("preheat       = ok=%d didInit=%d %lums err='%s'\n", ok ? 1 : 0,
           didInit ? 1 : 0, (unsigned long)dt, err.c_str());

    check(ok, "preheat returns true");
    check(didInit, "preheat reports didInit (否则插件层不会打 init OK)");
    // 这是本次修复的核心断言
    check(e.regionActive(), "regionActive == 1 (人脸模型已加载，掩码路径可用)");

    // ---- 2) 第二次必须幂等，且不再报 didInit ----------------------------
    std::string err2;
    bool didInit2 = false;
    const bool ok2 = e.preheat(err2, didInit2);
    printf("preheat #2    = ok=%d didInit=%d\n", ok2 ? 1 : 0, didInit2 ? 1 : 0);
    check(ok2, "second preheat still returns true");
    check(!didInit2, "second preheat reports didInit=0 (幂等)");
    check(e.regionActive(), "regionActive still 1 after second preheat");

    // ---- 3) acquireSlot 兜底路径也要能拉起引擎 --------------------------
    std::string err3;
    const int slot = e.acquireSlot(err3);
    check(slot >= 0, "acquireSlot succeeds after preheat");
    if (slot < 0) printf("        err=%s\n", err3.c_str());
    if (slot >= 0) e.releaseSlot(slot);

    printf("\n%s\n", g_fail == 0 ? "RESULT: PASS" : "RESULT: FAIL");
    return g_fail == 0 ? 0 : 1;
}
