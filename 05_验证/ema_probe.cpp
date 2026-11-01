// ema_probe —— CoreEngine 0.7.2「细节层时序 EMA」的验收台架
//
// 用法：ema_probe.exe <raw RGBA> <w> <h> <mode> [frames]
//   mode = static  同一帧重复喂（看静止时输出是否稳定 / 收敛）
//          noise   同一帧 + 逐帧变化的确定性噪声（模拟传感器噪点）
//          motion  每帧横向平移 EMA_STEP 像素（模拟摇头）
//
// 环境变量：
//   EMA_NOISE  噪声幅度（灰阶，默认 6）
//   EMA_STEP   每帧平移像素（默认 6）
//   BEAUTY_EMA 0/1 —— 由引擎自己读，本台架只透传，不干预
//
// 输出每帧一行：
//   #k inDiff=… outDiff=… hash=…
//     inDiff  = 输入亮度帧间差均值（探针自己算，用来标注「这一帧算不算运动」）
//     outDiff = **输出**帧间差均值（要考察的量：噪点被锐化放大的闪烁）
//     hash    = 输出帧的 FNV-1a 64 位哈希
//
// 三条验收判据（配合两个不同 BEAUTY_EMA 值各跑一次，用 diff_ema.py 比对）：
//   1) motion 模式：两次运行的 hash 逐帧**必须完全一致** —— 证明运动时零拖影
//      （beta=1 时不写回亮度平面，走的还是原来的浮点路径）。
//   2) noise 模式：EMA=1 的 outDiff 应显著低于 EMA=0（噪点闪烁被压掉）。
//   3) static 模式：两者 outDiff 都≈0，且 EMA=1 的 hash 从第 2 帧起不再变化
//      （历史收敛到自身，没有漂移）。

#include "beauty_core.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

// 真机实测档位（P_ 顺序：blur, clarity, whiten, red, sharpen, globalSharp,
// threed, eyebright, pouch, nasolabial, delspot）
static double kProfile[P_COUNT] = {26, 28, 61, 30, 59, 76, 0, 0, 100, 97, 90};

// EMA_PROFILE="26,0,0,0,59,76,0,0,0,0,0" 可覆盖，用来把「锐化贡献的闪烁」
// 从「磨皮本身的闪烁」里拆出来 —— 否则总量下降 30% 说不清是哪一段的功劳。
static void loadProfileFromEnv() {
    const char* v = getenv("EMA_PROFILE");
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
        printf("[ema] profile overridden by EMA_PROFILE\n");
    } else {
        printf("[ema] EMA_PROFILE needs %d values, got %d - ignored\n", (int)P_COUNT, n);
    }
}

static BeautySettings makeSettings() {
    BeautySettings s;
    for (int i = 0; i < P_COUNT; i++) s.panel[i] = kProfile[i];
    s.skin_detect = 1;
    return s;
}

// xorshift32：确定性伪随机，保证 EMA=0 / EMA=1 两次运行看到**逐字节相同**的输入序列
static unsigned int xs32(unsigned int& st) {
    st ^= st << 13;
    st ^= st >> 17;
    st ^= st << 5;
    return st;
}

static unsigned long long fnv1a(const unsigned char* p, size_t n) {
    unsigned long long h = 1469598103934665603ULL;
    for (size_t i = 0; i < n; i++) {
        h ^= (unsigned long long)p[i];
        h *= 1099511628211ULL;
    }
    return h;
}

// 亮度帧间差均值（每 4 像素取一个，和引擎里 updateMotion 的抽样密度一致）
static double lumaDiff(const std::vector<unsigned char>& a,
                       const std::vector<unsigned char>& b) {
    if (a.size() != b.size() || a.empty()) return 0.0;
    const size_t n = a.size() / 4;
    unsigned long long acc = 0;
    size_t cnt = 0;
    for (size_t i = 0; i < n; i += 4) {
        const size_t o = i * 4;
        const int la = (a[o] * 77 + a[o + 1] * 151 + a[o + 2] * 28) >> 8;
        const int lb = (b[o] * 77 + b[o + 1] * 151 + b[o + 2] * 28) >> 8;
        const int d = la - lb;
        acc += (unsigned long long)(d < 0 ? -d : d);
        cnt++;
    }
    return cnt ? (double)acc / (double)cnt : 0.0;
}

// 输出 RGB 帧间差均值（跳过 alpha；每 4 像素取一个）
static double rgbDiff(const std::vector<unsigned char>& a,
                      const std::vector<unsigned char>& b) {
    if (a.size() != b.size() || a.empty()) return 0.0;
    const size_t n = a.size() / 4;
    unsigned long long acc = 0;
    size_t cnt = 0;
    for (size_t i = 0; i < n; i += 4) {
        const size_t o = i * 4;
        for (int c = 0; c < 3; c++) {
            const int d = (int)a[o + c] - (int)b[o + c];
            acc += (unsigned long long)(d < 0 ? -d : d);
        }
        cnt += 3;
    }
    return cnt ? (double)acc / (double)cnt : 0.0;
}

// 横向平移（循环回绕）
static void shiftX(const std::vector<unsigned char>& in, std::vector<unsigned char>& out,
                   int w, int h, int dx) {
    out.resize(in.size());
    dx %= w;
    if (dx < 0) dx += w;
    for (int y = 0; y < h; y++) {
        const unsigned char* s = &in[(size_t)y * w * 4];
        unsigned char* d = &out[(size_t)y * w * 4];
        for (int x = 0; x < w; x++) {
            const int sx = (x + dx) % w;
            memcpy(d + (size_t)x * 4, s + (size_t)sx * 4, 4);
        }
    }
}

int main(int argc, char** argv) {
    if (argc < 5) {
        printf("usage: ema_probe.exe <raw RGBA> <w> <h> <static|noise|motion> [frames]\n");
        return 2;
    }
    const char* rawPath = argv[1];
    const int w = atoi(argv[2]);
    const int h = atoi(argv[3]);
    const std::string mode = argv[4];
    const int n = (argc > 5) ? atoi(argv[5]) : 8;
    const size_t bytes = (size_t)w * h * 4;

    FILE* f = nullptr;
    if (fopen_s(&f, rawPath, "rb") != 0 || !f) {
        printf("[FAIL] cannot open %s\n", rawPath);
        return 1;
    }
    std::vector<unsigned char> base(bytes);
    const size_t got = fread(&base[0], 1, bytes, f);
    fclose(f);
    if (got != bytes) {
        printf("[FAIL] %s is %zu bytes, expected %zu (%dx%d RGBA)\n", rawPath, got,
               bytes, w, h);
        return 1;
    }

    int noiseAmp = 6;
    if (const char* v = getenv("EMA_NOISE")) noiseAmp = atoi(v);
    int step = 6;
    if (const char* v = getenv("EMA_STEP")) step = atoi(v);
    const char* emaEnv = getenv("BEAUTY_EMA");

    _putenv("BEAUTY_ENGINE_IMPL=core");
    // 离线必须确定性：关异步检测，让「第 k 帧用哪份掩码」不受线程调度影响
    _putenv("BEAUTY_ASYNC_DETECT=0");
    loadProfileFromEnv();

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

    printf("engine = %s / %s | frame = %dx%d | mode = %s | frames = %d | "
           "BEAUTY_EMA = %s\n",
           e.id(), e.version(), w, h, mode.c_str(), n,
           emaEnv && *emaEnv ? emaEnv : "(unset -> on)");
    if (mode == "noise") printf("noiseAmp = %d\n", noiseAmp);
    if (mode == "motion") printf("step = %d px/frame\n", step);
    printf("profile =");
    for (int i = 0; i < P_COUNT; i++) printf(" %.0f", kProfile[i]);
    printf("\n");

    const BeautySettings s = makeSettings();
    std::vector<unsigned char> src(bytes), dst(bytes), prevOut, prevIn;
    std::vector<unsigned char> shifted;

    double sumOut = 0.0;
    int sumCnt = 0;
    for (int k = 0; k < n; k++) {
        if (mode == "motion") {
            shiftX(base, shifted, w, h, k * step);
            src = shifted;
        } else {
            src = base;
            if (mode == "noise" && k > 0) {
                // 噪声按帧号播种：两次运行同 k 帧拿到同一份噪声
                unsigned int st = 0x9E3779B9u ^ (unsigned int)(k * 2654435761u);
                if (st == 0) st = 1;
                for (size_t i = 0; i < bytes; i += 4) {
                    const int nz = (int)(xs32(st) % (unsigned int)(2 * noiseAmp + 1)) - noiseAmp;
                    for (int c = 0; c < 3; c++) {
                        int v = (int)src[i + c] + nz;
                        if (v < 0) v = 0;
                        if (v > 255) v = 255;
                        src[i + c] = (unsigned char)v;
                    }
                }
            }
        }

        if (!e.process(slot, &src[0], &dst[0], w, h, s)) {
            printf("[FAIL] process returned false at frame %d\n", k);
            return 1;
        }

        const double inD = prevIn.empty() ? 0.0 : lumaDiff(src, prevIn);
        const double outD = prevOut.empty() ? 0.0 : rgbDiff(dst, prevOut);
        printf("#%d inDiff=%6.3f outDiff=%6.3f hash=%016llx\n", k, inD, outD,
               fnv1a(&dst[0], bytes));

        // 前两帧含首帧复位 / 掩码首次检出，统计从第 2 帧起
        if (k >= 2) {
            sumOut += outD;
            sumCnt++;
        }
        prevOut = dst;
        prevIn = src;
    }

    printf("SUMMARY mode=%s frames=%d outDiffMean=%.4f\n", mode.c_str(), n,
           sumCnt ? sumOut / sumCnt : 0.0);

    e.releaseSlot(slot);
    printf("DONE\n");
    return 0;
}
