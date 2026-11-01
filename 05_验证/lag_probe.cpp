// lag_probe —— 量「掩码滞后」到底有几帧（阶跃响应法）
//
// 用法：lag_probe.exe <raw RGBA> <w> <h> [pre] [post] [shiftPx]
//   前 pre 帧人脸在 x0，从第 pre 帧起整个人像横移 shiftPx，之后保持不动。
//   每帧算出「被改动的像素」的横向质心 —— 那就是掩码实际所在的 x。
//   质心从 x0 走到 x0+shiftPx 用了 L 帧，L 就是端到端滞后。
//
// 为什么用质心：磨皮只在掩码内落笔（掩码外逐字节还原），所以 |out-in| 的
// 质心 ≈ 掩码质心。这样不用暴露任何内部状态，用公开 API 就能量。
//
// 档位只开磨皮 26：全局锐化会改整帧，|out-in| 铺满画面，质心就没意义了。
//
// 环境变量：
//   BEAUTY_ASYNC_DETECT  1（默认，测异步流水线）/ 0（测同步）
//   BEAUTY_MASK_EVERY    提交周期，默认 0
//
// 判读：
//   L = 1  异步流水线的理论极限（掩码来自上一帧）
//   L >= 2 还有别的东西在拖（队列、复用、采集时机）

#include "beauty_core.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static double nowMs() {
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)f.QuadPart;
}

static void shiftX(const std::vector<unsigned char>& in, std::vector<unsigned char>& out,
                   int w, int h, int dx) {
    out.resize(in.size());
    dx %= w;
    if (dx < 0) dx += w;
    for (int y = 0; y < h; y++) {
        const unsigned char* s = &in[(size_t)y * w * 4];
        unsigned char* d = &out[(size_t)y * w * 4];
        for (int x = 0; x < w; x++)
            memcpy(d + (size_t)x * 4, s + (size_t)((x + dx) % w) * 4, 4);
    }
}

int main(int argc, char** argv) {
    if (argc < 4) {
        printf("usage: lag_probe.exe <raw RGBA> <w> <h> [pre] [post] [shiftPx]\n");
        return 2;
    }
    const char* rawPath = argv[1];
    const int w = atoi(argv[2]);
    const int h = atoi(argv[3]);
    const int pre = (argc > 4) ? atoi(argv[4]) : 6;
    const int post = (argc > 5) ? atoi(argv[5]) : 6;
    const int shift = (argc > 6) ? atoi(argv[6]) : 60;
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
        printf("[FAIL] %s is %zu bytes, expected %zu\n", rawPath, got, bytes);
        return 1;
    }

    // 只开磨皮：让 |out-in| 集中在掩码内
    BeautySettings s;
    for (int i = 0; i < P_COUNT; i++) s.panel[i] = 0.0;
    s.panel[P_BLUR] = 26;
    s.skin_detect = 1;

    if (!getenv("BEAUTY_ASYNC_DETECT")) _putenv("BEAUTY_ASYNC_DETECT=1");
    _putenv("BEAUTY_ENGINE_IMPL=core");

    IBeautyEngine& e = beautyEngine();
    std::string err;
    bool didInit = false;
    if (!e.preheat(err, didInit) || !e.regionActive()) {
        printf("[FAIL] preheat/region: %s\n", err.c_str());
        return 1;
    }
    std::string serr;
    const int slot = e.acquireSlot(serr);
    if (slot < 0) {
        printf("[FAIL] acquireSlot: %s\n", serr.c_str());
        return 1;
    }

    const char* ad = getenv("BEAUTY_ASYNC_DETECT");
    const char* me = getenv("BEAUTY_MASK_EVERY");
    printf("engine=%s/%s frame=%dx%d pre=%d post=%d shift=%dpx async=%s maskEvery=%s\n",
           e.id(), e.version(), w, h, pre, post, shift,
           ad ? ad : "1", me ? me : "0(默认)");
    printf("%6s %6s %10s %10s %10s\n", "frame", "shift", "centroidX", "changedPx", "procMs");

    std::vector<unsigned char> src(bytes), dst(bytes), shifted;
    const int n = pre + post;
    for (int k = 0; k < n; k++) {
        const int dx = (k < pre) ? 0 : shift;
        if (dx) { shiftX(base, shifted, w, h, dx); src = shifted; }
        else    { src = base; }

        const double t0 = nowMs();
        if (!e.process(slot, &src[0], &dst[0], w, h, s)) {
            printf("[FAIL] process at frame %d\n", k);
            return 1;
        }
        const double ms = nowMs() - t0;

        // 逐列统计改动量，算横向质心
        double sw = 0.0, sx = 0.0;
        long long changed = 0;
        for (int y = 0; y < h; y++) {
            const unsigned char* a = &src[(size_t)y * w * 4];
            const unsigned char* b = &dst[(size_t)y * w * 4];
            for (int x = 0; x < w; x++) {
                const size_t o = (size_t)x * 4;
                int d = 0;
                for (int c = 0; c < 3; c++) {
                    const int v = (int)b[o + c] - (int)a[o + c];
                    d += (v < 0 ? -v : v);
                }
                if (d > 2) {                 // 噪声门槛，避免把 ±1 的量化算进去
                    sw += (double)d;
                    sx += (double)x * (double)d;
                    changed++;
                }
            }
        }
        const double cx = (sw > 0.0) ? sx / sw : -1.0;
        printf("%6d %6d %10.2f %10lld %10.2f\n", k, dx, cx, changed, ms);
    }

    e.releaseSlot(slot);
    printf("\n判读：centroidX 从第 %d 帧的位置走到 +%dpx，用了几帧就是几帧滞后。\n",
           pre - 1, shift);
    return 0;
}
