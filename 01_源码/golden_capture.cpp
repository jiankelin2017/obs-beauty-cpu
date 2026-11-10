// golden_capture.cpp —— 基线冻结（M0）的采集入口
//
// 离线工具版本：v1.1（2026-10-30）
//   v1.0 = 无显式版本标记的基线采集工具（goldens / goldens_legacy 均由它采出）。
//   v1.1 = 新增 blur_type<0「不下发」诊断分支（配合 legacy_engine.cpp 的守卫），
//          产品插件 obs-beauty.dll 路径不受影响，版本仍为 3.1.16、无需重装机。
//
// 只编译进**离线验证 DLL**，不进 OBS 插件 DLL（build_manual.bat 不含本文件）。
//
// 与既有 LegacySelfTest 的差别：LegacySelfTest 只能传 blur / whiten 两项，
// 这里可以传完整的参数数组 + blur_type / skin_detect / smooth_mode，
// 才能覆盖方案 v1 要求的参数矩阵。
//
// 导出（__stdcall，ctypes 用 WinDLL 调用）：
//   RefGoldenRun(engineDir, rawIn, rawOut, w, h, panel[], nPanel,
//                 blurType, skinDetect, smoothMode, resetSlot, msgBuf, msgCap)
//     resetSlot != 0 -> 归还并重新申请槽位（每档从干净状态开始）
//     resetSlot == 0 -> 沿用当前槽位（跑连续帧序列，模拟真实渲染的时序状态）

#include "legacy_engine.h"
#include "legacy_region.h"

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

namespace {

// 自测入参是 UTF-8（ctypes / Python 惯例），引擎内部走 ANSI 窄路径。
// 与 legacy_engine.cpp 里那份同逻辑，这里独立一份是为了不改引擎源码。
std::string utf8ToAcp(const char* s) {
    if (!s || !*s) return std::string();
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, nullptr, 0);
    if (n <= 0) return std::string(s);
    std::wstring w((size_t)n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s, -1, &w[0], n);
    int m = WideCharToMultiByte(CP_ACP, 0, w.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (m <= 0) return std::string(s);
    std::string a((size_t)m, '\0');
    WideCharToMultiByte(CP_ACP, 0, w.c_str(), -1, &a[0], m, nullptr, nullptr);
    a.resize((size_t)m - 1);
    return a;
}

void setMsg(char* buf, int cap, const char* fmt, ...) {
    if (!buf || cap <= 0) return;
    va_list args;
    va_start(args, fmt);
    vsnprintf_s(buf, (size_t)cap, _TRUNCATE, fmt, args);
    va_end(args);
}

int g_slot = -1;

}  // namespace

extern "C" {

__declspec(dllexport) int __stdcall RefGoldenRun(
    const char* engineDir, const char* rawIn, const char* rawOut,
    int width, int height,
    const double* panel, int nPanel,
    int blurType, int skinDetect, int smoothMode,
    int resetSlot,
    char* msgBuf, int msgCap) {
    if (msgBuf && msgCap > 0) msgBuf[0] = 0;
    if (!rawIn || !rawOut || width <= 0 || height <= 0) {
        setMsg(msgBuf, msgCap, "bad args");
        return 2;
    }

    const std::string engineDirA = utf8ToAcp(engineDir);
    const std::string rawInA = utf8ToAcp(rawIn);
    const std::string rawOutA = utf8ToAcp(rawOut);
    if (!engineDirA.empty()) _putenv_s("BEAUTY_ENGINE_ASSET_DIR", engineDirA.c_str());

    const size_t need = (size_t)width * (size_t)height * 4;

    FILE* f = nullptr;
    if (fopen_s(&f, rawInA.c_str(), "rb") != 0 || !f) {
        setMsg(msgBuf, msgCap, "cannot open input: %s", rawInA.c_str());
        return 3;
    }
    std::vector<unsigned char> buf(need);
    const size_t got = fread(&buf[0], 1, need, f);
    fclose(f);
    if (got != need) {
        setMsg(msgBuf, msgCap, "input too short: got %zu of %zu", got, need);
        return 4;
    }

    BeautySettings s;
    for (int i = 0; i < P_COUNT; i++) s.panel[i] = 0.0;
    const int n = (nPanel < P_COUNT) ? nPanel : P_COUNT;
    for (int i = 0; i < n; i++) s.panel[i] = panel[i];
    s.blur_type = blurType;
    s.skin_detect = skinDetect ? 1 : 0;
    s.smooth_mode = smoothMode;

    LegacyEngine& e = LegacyEngine::inst();
    std::string err;
    if (g_slot < 0 || resetSlot) {
        if (g_slot >= 0) e.releaseSlot(g_slot);
        g_slot = e.acquireSlot(err);
        if (g_slot < 0) {
            setMsg(msgBuf, msgCap, "acquireSlot failed: %s", err.c_str());
            return 5;
        }
    }

    std::vector<unsigned char> out(need);
    if (!e.process(g_slot, &buf[0], &out[0], width, height, s)) {
        setMsg(msgBuf, msgCap, "process failed: %s", e.lastErr());
        return 6;
    }

    if (fopen_s(&f, rawOutA.c_str(), "wb") != 0 || !f) {
        setMsg(msgBuf, msgCap, "cannot write output: %s", rawOutA.c_str());
        return 7;
    }
    fwrite(&out[0], 1, need, f);
    fclose(f);

    setMsg(msgBuf, msgCap,
           "OK faces=%d coverage=%.4f sdk=%.2fms item=%d region=%d",
           e.lastFaces(), e.regionCoverage(), e.lastCoreMs(), e.itemId(),
           e.regionActive() ? 1 : 0);
    return 0;
}

//
// 文件格式：8 字节小端头部（int32 mw, int32 mh）+ mw*mh 字节掩码（0..255）。
__declspec(dllexport) int __stdcall BeautyDumpMask(
    const char* engineDir, const char* rawIn, int width, int height,
    const char* outMask, char* msgBuf, int msgCap) {
    if (msgBuf && msgCap > 0) msgBuf[0] = 0;
    if (!rawIn || !outMask || width <= 0 || height <= 0) {
        setMsg(msgBuf, msgCap, "bad args");
        return 2;
    }
    const std::string engineDirA = utf8ToAcp(engineDir);
    const std::string rawInA = utf8ToAcp(rawIn);
    const std::string outA = utf8ToAcp(outMask);

    const size_t need = (size_t)width * (size_t)height * 4;
    FILE* f = nullptr;
    if (fopen_s(&f, rawInA.c_str(), "rb") != 0 || !f) {
        setMsg(msgBuf, msgCap, "cannot open input: %s", rawInA.c_str());
        return 3;
    }
    std::vector<unsigned char> buf(need);
    const size_t got = fread(&buf[0], 1, need, f);
    fclose(f);
    if (got != need) {
        setMsg(msgBuf, msgCap, "input too short: got %zu of %zu", got, need);
        return 4;
    }

    LegacyRegion& r = LegacyRegion::inst();
    std::string err;
    if (!r.ready() && !r.ensureReady(engineDirA, err)) {
        setMsg(msgBuf, msgCap, "region unavailable: %s", err.c_str());
        return 5;
    }
    const unsigned char* m = r.update(&buf[0], width, height, 1);
    if (!m) {
        setMsg(msgBuf, msgCap, "no mask this frame (faces=%d)", r.lastFaces());
        return 6;
    }
    const int mw = r.maskW(), mh = r.maskH();
    if (fopen_s(&f, outA.c_str(), "wb") != 0 || !f) {
        setMsg(msgBuf, msgCap, "cannot write mask: %s", outA.c_str());
        return 7;
    }
    int hdr[2] = {mw, mh};
    fwrite(hdr, sizeof(int), 2, f);
    fwrite(m, 1, (size_t)mw * (size_t)mh, f);
    fclose(f);
    setMsg(msgBuf, msgCap,
           "OK mask=%dx%d coverage=%.4f infer=%.2fms faces=%d",
           mw, mh, r.coverage(), r.lastInferMs(), r.lastFaces());
    return 0;
}

// 采集进程退出前归还槽位（可选；不调也没事，进程退出会带走一切）
__declspec(dllexport) void __stdcall RefGoldenRelease(void) {
    if (g_slot >= 0) {
        LegacyEngine::inst().releaseSlot(g_slot);
        g_slot = -1;
    }
}

}  // extern "C"
