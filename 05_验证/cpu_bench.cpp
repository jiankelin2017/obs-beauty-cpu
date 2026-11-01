// cpu_bench —— CoreEngine 每帧成本的逐项拆解（1280x720，离线，不经过 OBS）
//
// 用法：cpu_bench.exe <raw RGBA> <w> <h> [frames] [dumpOut.raw]
//
// 回答两个问题：
//   1) 3.1.4 修的「掩码生效」到底省了多少（全帧 vs 掩码包围盒）；
//   2) 面板 11 项里每一组各花多少毫秒 —— 用户想知道「关掉哪个能省多少」。
//
// 参数档位默认取真机实测的一组（2026-10-28 15:10 那次会话的场景文件）：
//   blur 26 / clarity 28 / whiten 61 / red 30 / sharpen 59 /
//   global_sharpen 76 / threed 0 / eyebright 0 / pouch 100 / nasolabial 97 / delspot 90
// 想换档位就改下面的 kProfile。
//
// 注意：这里测的是墙钟时间，且刻意关掉异步检测（BEAUTY_ASYNC_DETECT=0），
// 让 YuNet 也落在同一线程里 —— 这样「每帧总成本」才是完整的。OBS 里开着异步，
// 检测在 worker 上，单看 process() 会偏乐观。

#include "beauty_core.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>      // timeBeginPeriod：按真实帧率节流时要用
#pragma comment(lib, "winmm.lib")

static double nowMs() {
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)f.QuadPart;
}

// 真机实测档位（P_ 顺序：blur, clarity, whiten, red, sharpen, globalSharp,
// threed, eyebright, pouch, nasolabial, delspot）
static double kProfile[P_COUNT] = {26, 28, 61, 30, 59, 76, 0, 0, 100, 97, 90};

// 允许用 BENCH_PROFILE="26,28,61,30,59,76,0,0,100,97,90" 覆盖，便于逐项消融。
static void loadProfileFromEnv() {
    const char* v = getenv("BENCH_PROFILE");
    if (!v || !*v) return;
    double tmp[P_COUNT];
    int n = 0;
    const char* p = v;
    while (n < P_COUNT) {
        char* end = nullptr;
        const double d = strtod(p, &end);
        if (end == p) break;
        tmp[n++] = d;
        p = end;
        if (*p == ',') p++;
    }
    if (n == P_COUNT) {
        for (int i = 0; i < P_COUNT; i++) kProfile[i] = tmp[i];
        printf("[bench] profile overridden by BENCH_PROFILE\n");
    } else {
        printf("[bench] BENCH_PROFILE needs %d values, got %d - ignored\n", (int)P_COUNT, n);
    }
}

static BeautySettings makeSettings(const bool on[P_COUNT]) {
    BeautySettings s;
    for (int i = 0; i < P_COUNT; i++) s.panel[i] = on[i] ? kProfile[i] : 0.0;
    s.skin_detect = 1;
    return s;
}

static double runMs(IBeautyEngine& e, int slot, const unsigned char* src,
                    unsigned char* dst, int w, int h, const BeautySettings& s, int n) {
    e.process(slot, src, dst, w, h, s);   // 预热，不计
    const double t0 = nowMs();
    for (int i = 0; i < n; i++) e.process(slot, src, dst, w, h, s);
    return (nowMs() - t0) / (double)n;
}

int main(int argc, char** argv) {
    if (argc < 4) {
        printf("usage: cpu_bench.exe <raw RGBA> <w> <h> [frames] [dumpOut.raw]\n");
        return 2;
    }
    const char* rawPath = argv[1];
    const int w = atoi(argv[2]);
    const int h = atoi(argv[3]);
    const int n = (argc > 4) ? atoi(argv[4]) : 40;
    const char* dumpPath = (argc > 5) ? argv[5] : nullptr;
    const size_t bytes = (size_t)w * h * 4;

    FILE* f = nullptr;
    if (fopen_s(&f, rawPath, "rb") != 0 || !f) {
        printf("[FAIL] cannot open %s\n", rawPath);
        return 1;
    }
    std::vector<unsigned char> src(bytes), dst(bytes);
    const size_t got = fread(&src[0], 1, bytes, f);
    fclose(f);
    if (got != bytes) {
        printf("[FAIL] %s is %zu bytes, expected %zu (%dx%d RGBA)\n", rawPath, got,
               bytes, w, h);
        return 1;
    }

    _putenv("BEAUTY_ENGINE_IMPL=core");
    loadProfileFromEnv();
    // 默认关异步检测，让 YuNet 也落在同一线程 —— 「每帧总成本」才完整。
    // 想测 OBS 的实际配置（异步开）就预先设 BEAUTY_ASYNC_DETECT=1。
    if (!getenv("BEAUTY_ASYNC_DETECT")) _putenv("BEAUTY_ASYNC_DETECT=0");

    IBeautyEngine& e = beautyEngine();
    std::string err;
    bool didInit = false;
    if (!e.preheat(err, didInit) || !e.regionActive()) {
        printf("[FAIL] preheat/region not ready: %s\n", err.c_str());
        return 1;
    }
    std::string serr;
    const int slot = e.acquireSlot(serr);
    if (slot < 0) {
        printf("[FAIL] acquireSlot: %s\n", serr.c_str());
        return 1;
    }

    printf("engine = %s / %s | frame = %dx%d | %d frames per step\n\n", e.id(),
           e.version(), w, h, n);

    // ---- 1) 磨皮单独：全帧 vs 掩码 ROI ---------------------------------
    bool onlyBlur[P_COUNT] = {false};
    onlyBlur[P_BLUR] = true;
    const BeautySettings sBlur = makeSettings(onlyBlur);

    beautyCoreSetPerf(0, 0);   // 关 ROI = 3.1.4 之前的实际行为
    const double msFull = runMs(e, slot, &src[0], &dst[0], w, h, sBlur, n);
    beautyCoreSetPerf(0, 1);   // 开 ROI = 3.1.4 之后
    const double msRoi = runMs(e, slot, &src[0], &dst[0], w, h, sBlur, n);
    const int faces = e.lastFaces();

    printf("  只开磨皮 %-3.0f 全帧 (修前) = %6.2f ms\n", kProfile[P_BLUR], msFull);
    printf("  只开磨皮 %-3.0f 掩码 ROI(修后) = %6.2f ms   ratio %.3f  省 %.0f%%  faces=%d\n\n",
           kProfile[P_BLUR], msRoi, msRoi / msFull, (1.0 - msRoi / msFull) * 100.0, faces);

    // ---- 2) 按真机档位逐组累加 -----------------------------------------
    struct Step { const char* name; int idx[4]; };
    const Step steps[] = {
        {"磨皮",                    {P_BLUR, -1, -1, -1}},
        {"+ 清晰",                  {P_CLARITY, -1, -1, -1}},
        {"+ 美白 / 红润",           {P_WHITEN, P_RED, -1, -1}},
        {"+ 锐化(脸内)",            {P_SHARPEN, -1, -1, -1}},
        {"+ 全局锐化",              {P_GLOBAL_SHARP, -1, -1, -1}},
        {"+ 去黑眼圈/法令纹/祛斑痘", {P_POUCH, P_NASOLABIAL, P_DELSPOT, -1}},
    };
    const int nSteps = (int)(sizeof(steps) / sizeof(steps[0]));

    bool on[P_COUNT] = {false};
    double prev = 0.0;
    printf("  %-26s %8s %8s\n", "累加", "ms", "增量");
    printf("  %-26s %8s %8s\n", "--------------------------", "--------", "--------");
    for (int k = 0; k < nSteps; k++) {
        for (int j = 0; j < 4; j++)
            if (steps[k].idx[j] >= 0) on[steps[k].idx[j]] = true;
        const BeautySettings s = makeSettings(on);
        const double ms = runMs(e, slot, &src[0], &dst[0], w, h, s, n);
        printf("  %-26s %8.2f %+8.2f\n", steps[k].name, ms, ms - prev);
        prev = ms;
    }
    const double msAll = prev;

    // ---- 3) 同样全开，但强制全帧（假如掩码再丢会怎样）------------------
    beautyCoreSetPerf(0, 0);
    const BeautySettings sAll = makeSettings(on);
    const double msAllFull = runMs(e, slot, &src[0], &dst[0], w, h, sAll, n);
    beautyCoreSetPerf(0, 1);

    printf("\n  全开(掩码 ROI) = %6.2f ms     全开(强制全帧) = %6.2f ms  ratio %.3f\n",
           msAll, msAllFull, msAll / msAllFull);

    // ---- 3b) 进程级 CPU 占用（异步检测的节奏只看得到这里）----------------
    // 上面那些毫秒数是**渲染线程**的墙钟，worker 烧了多少核它一点反映都没有。
    // 3.1.8 把掩码提交周期从 4 帧改成每帧，渲染线程多一次 memcpy、worker 占用
    // 从 14.1/167 ≈ 8% 涨到 14.1/33 ≈ 42%（单核）。这一段专门量这个差值。
    //
    // 必须按真实帧率节流再量：不节流时台架会跑到 80fps，8 个磨皮线程把核占满，
    // 争用被放大成「每帧多 1.4ms」，那是台架的假象，不是真机。真机 30fps 下
    // 磨皮只占 33ms 预算的 1/3，核大量空闲。
    //   BENCH_FPS=30 BEAUTY_ASYNC_DETECT=1 BEAUTY_MASK_EVERY=4 cpu_bench.exe ...
    //   BENCH_FPS=30 BEAUTY_ASYNC_DETECT=1 BEAUTY_MASK_EVERY=0 cpu_bench.exe ...
    {
        FILETIME ct, et, kt, ut;
        auto cpuSec = [&]() -> double {
            GetProcessTimes(GetCurrentProcess(), &ct, &et, &kt, &ut);
            ULARGE_INTEGER k, u;
            k.LowPart = kt.dwLowDateTime;  k.HighPart = kt.dwHighDateTime;
            u.LowPart = ut.dwLowDateTime;  u.HighPart = ut.dwHighDateTime;
            return (double)(k.QuadPart + u.QuadPart) * 1e-7;
        };
        int fpsCap = 0;
        if (const char* v = getenv("BENCH_FPS")) fpsCap = atoi(v);
        const double frameMs = (fpsCap > 0) ? 1000.0 / (double)fpsCap : 0.0;
        // Windows 默认 Sleep 精度 15.6ms，节流到 33ms 会抖成 33/48 交替。
        // 抬到 1ms 才谈得上「按帧率节流」。
        if (fpsCap > 0) timeBeginPeriod(1);

        cpuSec();                       // 先调一次，别把首次开销算进去
        const int nCpu = (n < 150) ? 150 : n;   // 太短的窗口测不准
        const uint64_t sub0 = beautyCoreMaskSubmits();
        const double c0 = cpuSec();
        const double w0 = nowMs();
        double renderMs = 0.0;
        for (int i = 0; i < nCpu; i++) {
            const double s0 = nowMs();
            e.process(slot, &src[0], &dst[0], w, h, sAll);
            renderMs += nowMs() - s0;
            if (frameMs > 0.0) {
                const double el = nowMs() - s0;
                if (el < frameMs) Sleep((DWORD)(frameMs - el));
            }
        }
        const double wall = (nowMs() - w0) / 1000.0;
        const double cores = (cpuSec() - c0) / wall;
        const uint64_t subs = beautyCoreMaskSubmits() - sub0;
        if (fpsCap > 0) timeEndPeriod(1);

        const char* ad = getenv("BEAUTY_ASYNC_DETECT");
        const char* me = getenv("BEAUTY_MASK_EVERY");
        printf("\n  [节流到 %s] %d 帧 / %.2fs\n",
               fpsCap > 0 ? (fpsCap == 30 ? "30fps" : "自定义") : "不限（满负荷）",
               nCpu, wall);
        printf("  渲染线程每帧 = %.2f ms\n", renderMs / nCpu);
        printf("  进程 CPU 占用 = %.2f 核（%.0f%% 单核）  async=%s maskEvery=%s\n",
               cores, cores * 100.0,
               ad ? ad : "0(默认)", me ? me : "0(默认)");
        printf("  掩码提交     = %llu 次 / %d 帧 = %.2f 次/帧   （周期 0 应≈1.0，周期 4 应≈0.20）\n",
               (unsigned long long)subs, nCpu, (double)subs / (double)nCpu);
    }

    // ---- 4) 可选：把处理后的帧存下来，交给 Python 量 detail ---------------
    if (dumpPath) {
        e.process(slot, &src[0], &dst[0], w, h, sAll);
        FILE* o = nullptr;
        if (fopen_s(&o, dumpPath, "wb") == 0 && o) {
            fwrite(&dst[0], 1, bytes, o);
            fclose(o);
            printf("  dumped -> %s\n", dumpPath);
        }
    }

    e.releaseSlot(slot);
    printf("\nDONE\n");
    return 0;
}
