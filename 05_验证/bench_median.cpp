// 微基准：3.0.4 的 medianRawMask 单次开销。
// 只测那一段循环本身（192x256 三值中值 + 两次 memcpy），不含 fuai / SDK。
// 用 cl /O2 编译，与生产一致的优化级别。
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <vector>

static double nowMs() {
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

int main() {
    const int mw = 192, mh = 256;
    const size_t n = (size_t)mw * mh;
    std::vector<unsigned char> mask(n), p1(n), p2(n), tmp(n);
    srand(12345);
    for (size_t i = 0; i < n; i++) mask[i] = (rand() & 7) ? 0 : 255;
    memcpy(&p1[0], &mask[0], n);
    memcpy(&p2[0], &mask[0], n);

    const int ITER = 5000;
    // 预热
    for (int it = 0; it < 200; it++) {
        memcpy(&tmp[0], &mask[0], n);
        const unsigned char* p1p = &p1[0];
        const unsigned char* c0p = &tmp[0];
        long long sum = 0;
        for (size_t i = 0; i < n; i++) {
            const int b = p1p[i], c = c0p[i];
            sum += (b > c ? b - c : c - b);
        }
        const double chg = (double)sum / (double)n;
        if (chg < 3.0) {
            const unsigned char* a = &p2[0];
            unsigned char* cur = &mask[0];
            for (size_t i = 0; i < n; i++) {
                const int x = a[i], y = p1p[i], z = c0p[i];
                int med;
                if (x < y) {
                    if (y < z)      med = y;
                    else if (x < z) med = z;
                    else            med = x;
                } else {
                    if (x < z)      med = x;
                    else if (y < z) med = z;
                    else            med = y;
                }
                cur[i] = (unsigned char)med;
            }
        }
        memcpy(&p2[0], &p1[0], n);
        memcpy(&p1[0], &tmp[0], n);
    }

    double t0 = nowMs();
    for (int it = 0; it < ITER; it++) {
        memcpy(&tmp[0], &mask[0], n);
        const unsigned char* p1p = &p1[0];
        const unsigned char* c0p = &tmp[0];
        long long sum = 0;
        for (size_t i = 0; i < n; i++) {
            const int b = p1p[i], c = c0p[i];
            sum += (b > c ? b - c : c - b);
        }
        const double chg = (double)sum / (double)n;
        if (chg < 3.0) {
            const unsigned char* a = &p2[0];
            unsigned char* cur = &mask[0];
            for (size_t i = 0; i < n; i++) {
                const int x = a[i], y = p1p[i], z = c0p[i];
                int med;
                if (x < y) {
                    if (y < z)      med = y;
                    else if (x < z) med = z;
                    else            med = x;
                } else {
                    if (x < z)      med = x;
                    else if (y < z) med = z;
                    else            med = y;
                }
                cur[i] = (unsigned char)med;
            }
        }
        memcpy(&p2[0], &p1[0], n);
        memcpy(&p1[0], &tmp[0], n);
    }
    double t1 = nowMs();
    printf("medianRawMask(3.0.5)  %dx%d  %d 次  合计 %.1f ms  单次 %.4f ms\n",
           mw, mh, ITER, t1 - t0, (t1 - t0) / ITER);
    return 0;
}
