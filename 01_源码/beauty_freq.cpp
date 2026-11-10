// beauty_freq.cpp —— 高低频分离磨皮实现

#include "beauty_env.h"   // beauty_env()：BEAUTY_* 覆盖的唯一入口（1.0.13.10 C-2/C-3）
#include "beauty_freq.h"
#include "beauty_pool.h"

#include "beauty_guide.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>

namespace beautycore {

namespace {

int effThreads(int threads, int rows) {
    if (threads == 1) return 1;
    int n = threads;
    if (n <= 0) {
        const unsigned hc = std::thread::hardware_concurrency();
        n = hc ? (int)hc : 4;
        if (n > 8) n = 8;
    }
    if (n < 1) n = 1;
    if (rows < 32) return 1;
    const int byRows = rows / 16;
    if (n > byRows) n = byRows;
    return (n < 1) ? 1 : n;
}

void buildKernel(std::vector<float>& k, int radius, float sigma) {
    const int n = radius * 2 + 1;
    k.assign((size_t)n, 0.0f);
    const float inv = (sigma > 0.0f) ? 1.0f / (2.0f * sigma * sigma) : 0.0f;
    float sum = 0.0f;
    for (int i = 0; i < n; i++) {
        const int d = i - radius;
        const float v = std::exp(-(float)(d * d) * inv);
        k[(size_t)i] = v;
        sum += v;
    }
    if (sum > 0.0f) {
        for (int i = 0; i < n; i++) k[(size_t)i] /= sum;
    }
}

// 并行按行跑一段区间
template <typename Fn>
void runRows(int y0, int y1, int threads, Fn fn) {
    const int rows = y1 - y0;
    const int nt = effThreads(threads, rows);
    if (nt <= 1) {
        fn(y0, y1);
        return;
    }
    beautycore::parallelRows(y0, y1, nt, [&fn](int b, int e) { fn(b, e); });
}

inline int clampi(int v, int lo, int hi) {
    return (v < lo) ? lo : ((v > hi) ? hi : v);
}

}  // namespace

void gaussBlurRgba(const unsigned char* src, unsigned char* dst,
                   int w, int h, int radius, float sigma,
                   const RoiRect& roi, int threads,
                   std::vector<unsigned char>& scratch) {
    if (!src || !dst || w <= 0 || h <= 0) return;
    if (roi.empty()) return;
    if (radius < 1) {
        // 半径 0：低频 = 原图
        for (int y = roi.y0; y < roi.y1; y++) {
            const size_t off = (size_t)y * w * 4;
            memcpy(dst + off + (size_t)roi.x0 * 4, src + off + (size_t)roi.x0 * 4,
                   (size_t)roi.width() * 4);
        }
        return;
    }

    std::vector<float> ker;
    buildKernel(ker, radius, sigma);
    const int taps = radius * 2 + 1;

    const size_t need = (size_t)w * h * 4;
    if (scratch.size() < need) scratch.resize(need);
    unsigned char* mid = &scratch[0];

    // 水平 pass：只做「垂直 pass 会读到」的那些行（roi 上下各外扩 radius）。
    // 不做整图 —— 1080p 整图水平模糊要多花 3~4 倍时间，而 ROI 外的低频没人用。
    const int hy0 = clampi(roi.y0 - radius, 0, h);
    const int hy1 = clampi(roi.y1 + radius, 0, h);
    runRows(hy0, hy1, threads, [&](int yBegin, int yEnd) {
        for (int y = yBegin; y < yEnd; y++) {
            const unsigned char* row = src + (size_t)y * w * 4;
            unsigned char* out = mid + (size_t)y * w * 4;
            for (int x = 0; x < w; x++) {
                float a0 = 0, a1 = 0, a2 = 0;
                for (int t = 0; t < taps; t++) {
                    const int sx = clampi(x + t - radius, 0, w - 1);
                    const float kv = ker[(size_t)t];
                    const unsigned char* p = row + (size_t)sx * 4;
                    a0 += p[0] * kv;
                    a1 += p[1] * kv;
                    a2 += p[2] * kv;
                }
                unsigned char* o = out + (size_t)x * 4;
                o[0] = (unsigned char)(a0 + 0.5f);
                o[1] = (unsigned char)(a1 + 0.5f);
                o[2] = (unsigned char)(a2 + 0.5f);
                o[3] = row[(size_t)x * 4 + 3];
            }
        }
    });

    // 垂直 pass：只写 roi 内的行，x 覆盖 roi 宽度
    runRows(roi.y0, roi.y1, threads, [&](int yBegin, int yEnd) {
        for (int y = yBegin; y < yEnd; y++) {
            unsigned char* out = dst + (size_t)y * w * 4;
            for (int x = roi.x0; x < roi.x1; x++) {
                float a0 = 0, a1 = 0, a2 = 0;
                for (int t = 0; t < taps; t++) {
                    const int sy = clampi(y + t - radius, 0, h - 1);
                    const float kv = ker[(size_t)t];
                    const unsigned char* p = mid + ((size_t)sy * w + x) * 4;
                    a0 += p[0] * kv;
                    a1 += p[1] * kv;
                    a2 += p[2] * kv;
                }
                unsigned char* o = out + (size_t)x * 4;
                o[0] = (unsigned char)(a0 + 0.5f);
                o[1] = (unsigned char)(a1 + 0.5f);
                o[2] = (unsigned char)(a2 + 0.5f);
                o[3] = src[((size_t)y * w + x) * 4 + 3];
            }
        }
    });
}

void freqComposite(const unsigned char* src, const unsigned char* low,
                   unsigned char* dst, int w, int h,
                   float strength, float magLo, float magHi, float grain,
                   const RoiRect& roi, int threads) {
    if (!src || !low || !dst || w <= 0 || h <= 0 || roi.empty()) return;
    if (strength <= 0.0f) {
        for (int y = roi.y0; y < roi.y1; y++) {
            const size_t off = (size_t)y * w * 4;
            memcpy(dst + off + (size_t)roi.x0 * 4, src + off + (size_t)roi.x0 * 4,
                   (size_t)roi.width() * 4);
        }
        return;
    }
    if (magHi <= magLo) magHi = magLo + 1.0f;

    runRows(roi.y0, roi.y1, threads, [&](int yBegin, int yEnd) {
        for (int y = yBegin; y < yEnd; y++) {
            for (int x = roi.x0; x < roi.x1; x++) {
                const size_t o = ((size_t)y * w + x) * 4;
                int d0 = (int)src[o + 0] - (int)low[o + 0];
                int d1 = (int)src[o + 1] - (int)low[o + 1];
                int d2 = (int)src[o + 2] - (int)low[o + 2];

                // 双边迭代会留下"阶梯感"——平坦区被压成平台，平台之间出现新台阶，
                // 实测「小幅度高频」反而从 105% 涨到 113%。做法是把 4 邻域尺度的
                // 极细颗粒从要磨掉的量里扣回来：(src-low) - (src-around)*grain。
                // 这样只磨中频瑕疵，最细的皮肤纹理原样留着。
                if (grain > 0.0f) {
                    const int xm = (x > 0) ? (x - 1) : 0;
                    const int xp = (x + 1 < w) ? (x + 1) : (w - 1);
                    const int ym = (y > 0) ? (y - 1) : 0;
                    const int yp = (y + 1 < h) ? (y + 1) : (h - 1);
                    const size_t oxm = ((size_t)y * w + xm) * 4;
                    const size_t oxp = ((size_t)y * w + xp) * 4;
                    const size_t oym = ((size_t)ym * w + x) * 4;
                    const size_t oyp = ((size_t)yp * w + x) * 4;
                    const int g0 = (src[oxm] + src[oxp] + src[oym] + src[oyp]) / 4;
                    const int g1 = (src[oxm+1] + src[oxp+1] + src[oym+1] + src[oyp+1]) / 4;
                    const int g2 = (src[oxm+2] + src[oxp+2] + src[oym+2] + src[oyp+2]) / 4;
                    d0 -= (int)((src[o+0] - g0) * grain);
                    d1 -= (int)((src[o+1] - g1) * grain);
                    d2 -= (int)((src[o+2] - g2) * grain);
                }
                int mag = d0 < 0 ? -d0 : d0;
                int t = d1 < 0 ? -d1 : d1;
                if (t > mag) mag = t;
                t = d2 < 0 ? -d2 : d2;
                if (t > mag) mag = t;

                // atten = strength · (1 - smoothstep(magLo, magHi, mag))
                float a;
                if ((float)mag <= magLo) {
                    a = strength;
                } else if ((float)mag >= magHi) {
                    a = 0.0f;
                } else {
                    const float u = ((float)mag - magLo) / (magHi - magLo);
                    a = strength * (1.0f - u * u * (3.0f - 2.0f * u));
                }
                if (a <= 0.0f) {
                    dst[o + 0] = src[o + 0];
                    dst[o + 1] = src[o + 1];
                    dst[o + 2] = src[o + 2];
                } else {
                    dst[o + 0] = (unsigned char)(src[o + 0] - d0 * a + 0.5f);
                    dst[o + 1] = (unsigned char)(src[o + 1] - d1 * a + 0.5f);
                    dst[o + 2] = (unsigned char)(src[o + 2] - d2 * a + 0.5f);
                }
                dst[o + 3] = src[o + 3];
            }
        }
    });
}

// clarity：大半径局部对比回填。
//
// out = dst + (L - box(L, r)) × gain × gate(|L - box(L,r)|) × mask
//
// 三个刻意的选择：
//   1) 只在**亮度**上算，把同一个增量加到 RGB 三通道 —— 保持色相与饱和度不变，
//      三通道各算各的会把颜色边缘放大成彩边。
//   2) gate 用软膝而不是硬阈值：硬阈值会在阈值边界处留下「加/不加」的分界线，
//      看起来像一圈圈的等高线。
//   3) 输入是 dst（磨皮之后的图），不是 src —— 我们要增强的是最终画面的结构，
//      拿原图算会把刚磨掉的瑕疵重新加回来一半。
static inline float claritySmoothStep(float a, float b, float x) {
    if (b <= a) return (x < a) ? 0.0f : 1.0f;
    float t = (x - a) / (b - a);
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    return t * t * (3.0f - 2.0f * t);
}

void clarityRgb(unsigned char* dst, int w, int h, const unsigned char* mask,
                const RoiRect& roi, const ClarityParams& p, int threads,
                std::vector<float>& scratch) {
    if (!dst || !mask || w <= 0 || h <= 0 || roi.empty()) return;
    if (p.gain <= 0.0f) return;

    LowFreqBuf lf = boxLumaRoi(dst, w, h, p.radius, roi, threads, scratch);
    if (!lf.valid()) return;

    const float lo = p.kneeLo;
    const float hi = (p.kneeHi > lo) ? p.kneeHi : (lo + 1.0f);

    runRows(roi.y0, roi.y1, threads, [&](int yBegin, int yEnd) {
        for (int y = yBegin; y < yEnd; y++) {
            const int ly = y - lf.y0;
            for (int x = roi.x0; x < roi.x1; x++) {
                const unsigned char m = mask[(size_t)y * w + x];
                if (m == 0) continue;                 // 掩码外一个字节都不动
                const int lx = x - lf.x0;
                if (lx < 0 || ly < 0 || lx >= lf.bw || ly >= lf.bh) continue;
                const size_t o = ((size_t)y * w + x) * 4;

                const float L = 0.299f * dst[o + 0] + 0.587f * dst[o + 1] +
                                0.114f * dst[o + 2];
                const float mid = L - lf.r[(size_t)ly * lf.bw + lx];
                const float am = std::fabs(mid);
                const float gate = 1.0f - claritySmoothStep(lo, hi, am);
                if (gate <= 0.0f) continue;

                const float k = p.gain * gate * ((float)m * (1.0f / 255.0f));
                const float add = mid * k;
                if (add > -0.5f && add < 0.5f) continue;   // 增量小于半个灰阶：不动

                for (int c = 0; c < 3; c++) {
                    float v = (float)dst[o + c] + add;
                    if (v < 0.0f) v = 0.0f;
                    if (v > 255.0f) v = 255.0f;
                    dst[o + c] = (unsigned char)(v + 0.5f);
                }
            }
        }
    });
}

// 与上面同构，但低频来自浮点平面。合成的算术一个字都没改 —— 变的只是
// `src - low` 里的 low 保持浮点精度（不再先压回 uint8，少一次量化）。
void freqCompositePlanes(const unsigned char* src, unsigned char* dst,
                         int w, int h, const LowFreqBuf& low,
                         float strength, float magLo, float magHi, float grain,
                         const RoiRect& roi, int threads) {
    if (!src || !dst || w <= 0 || h <= 0 || roi.empty() || !low.valid()) return;
    if (strength <= 0.0f) {
        for (int y = roi.y0; y < roi.y1; y++) {
            const size_t off = (size_t)y * w * 4;
            memcpy(dst + off + (size_t)roi.x0 * 4, src + off + (size_t)roi.x0 * 4,
                   (size_t)roi.width() * 4);
        }
        return;
    }
    if (magHi <= magLo) magHi = magLo + 1.0f;

    runRows(roi.y0, roi.y1, threads, [&](int yBegin, int yEnd) {
        for (int y = yBegin; y < yEnd; y++) {
            const int ly = y - low.y0;
            for (int x = roi.x0; x < roi.x1; x++) {
                const int lx = x - low.x0;
                if (lx < 0 || ly < 0 || lx >= low.bw || ly >= low.bh) continue;
                const size_t li = (size_t)ly * low.bw + lx;
                const size_t o = ((size_t)y * w + x) * 4;

                float d0 = (float)src[o + 0] - low.r[li];
                float d1 = (float)src[o + 1] - low.g[li];
                float d2 = (float)src[o + 2] - low.b[li];

                // 颗粒回填：与 freqComposite 完全一致（在 uint8 源上取 4 邻域）
                if (grain > 0.0f) {
                    const int xm = (x > 0) ? (x - 1) : 0;
                    const int xp = (x + 1 < w) ? (x + 1) : (w - 1);
                    const int ym = (y > 0) ? (y - 1) : 0;
                    const int yp = (y + 1 < h) ? (y + 1) : (h - 1);
                    const size_t oxm = ((size_t)y * w + xm) * 4;
                    const size_t oxp = ((size_t)y * w + xp) * 4;
                    const size_t oym = ((size_t)ym * w + x) * 4;
                    const size_t oyp = ((size_t)yp * w + x) * 4;
                    const int g0 = (src[oxm] + src[oxp] + src[oym] + src[oyp]) / 4;
                    const int g1 = (src[oxm+1] + src[oxp+1] + src[oym+1] + src[oyp+1]) / 4;
                    const int g2 = (src[oxm+2] + src[oxp+2] + src[oym+2] + src[oyp+2]) / 4;
                    d0 -= ((float)src[o+0] - (float)g0) * grain;
                    d1 -= ((float)src[o+1] - (float)g1) * grain;
                    d2 -= ((float)src[o+2] - (float)g2) * grain;
                }

                float mag = std::fabs(d0);
                const float t1 = std::fabs(d1), t2 = std::fabs(d2);
                if (t1 > mag) mag = t1;
                if (t2 > mag) mag = t2;

                float a;
                if (mag <= magLo) {
                    a = strength;
                } else if (mag >= magHi) {
                    a = 0.0f;
                } else {
                    const float u = (mag - magLo) / (magHi - magLo);
                    a = strength * (1.0f - u * u * (3.0f - 2.0f * u));
                }
                if (a <= 0.0f) {
                    dst[o + 0] = src[o + 0];
                    dst[o + 1] = src[o + 1];
                    dst[o + 2] = src[o + 2];
                } else {
                    const float v0 = (float)src[o + 0] - d0 * a;
                    const float v1 = (float)src[o + 1] - d1 * a;
                    const float v2 = (float)src[o + 2] - d2 * a;
                    dst[o + 0] = (unsigned char)(v0 < 0 ? 0 : (v0 > 255 ? 255 : v0) + 0.5f);
                    dst[o + 1] = (unsigned char)(v1 < 0 ? 0 : (v1 > 255 ? 255 : v1) + 0.5f);
                    dst[o + 2] = (unsigned char)(v2 < 0 ? 0 : (v2 > 255 ? 255 : v2) + 0.5f);
                }
                dst[o + 3] = src[o + 3];
            }
        }
    });
}

void highLowSmooth(const unsigned char* src, unsigned char* dst,
                   int w, int h, const FreqParams& p,
                   const RoiRect& roi, int threads,
                   std::vector<unsigned char>& lowBuf,
                   std::vector<unsigned char>& scratch,
                   std::vector<float>& guideScratch) {
    if (!src || !dst || w <= 0 || h <= 0 || roi.empty()) return;

    // 路线 C（lowPath == 3）：盒式迭代低通，不保边。
    //
    // 与上面两条路线的根本差别：低频层**不保边**。边缘处 (src − low) 幅度自然变大，
    // 由后面的幅度门控统一拦住；而痘印/鼻翼阴影/唇纹幅度中等，会被削掉。
    // 之前「双边保边 + 门控保边」两道叠在一起，等于把瑕疵也一起放过了 —— 实测
    if (p.lowPath == 3) {
        BoxLowParams bp;
        bp.radius = (p.boxRadius > 0) ? p.boxRadius : 4;
        bp.iters = (p.boxIters > 0) ? p.boxIters : 3;
        LowFreqBuf lf = boxRgbRoi(src, w, h, bp, roi, threads, guideScratch);
        if (lf.valid()) {
            freqCompositePlanes(src, dst, w, h, lf,
                                (float)p.strength / 100.0f, p.magLo, p.magHi,
                                p.grain, roi, threads);
            return;
        }
    }

    // 路线 A（lowPath > 0）：浮点双边 + 可选低频参照。
    // 上面 lowMode 那条是「换算法」，这条是「换权重判据 + 换精度」，
    // 两者互斥，这里优先走新路线。
    if (p.lowPath > 0) {
        BilateralRefParams bp;
        bp.radius = (p.radius > 0) ? p.radius : 2;
        bp.sigmaSpace = p.sigmaSpace;
        bp.sigmaColor = p.sigmaColor;
        bp.iters = (p.iters < 1) ? 1 : p.iters;
        bp.refRadius = (p.lowPath >= 2) ? p.refRadius : 0;
        // guideScratch 复用为浮点平面缓冲（9 个 bw×bh 平面），避免再加一个成员
        LowFreqBuf lf = lowFreqRefRoi(src, w, h, bp, roi, threads, guideScratch);
        if (lf.valid()) {
            freqCompositePlanes(src, dst, w, h, lf,
                                (float)p.strength / 100.0f, p.magLo, p.magHi,
                                p.grain, roi, threads);
            return;
        }
        // 分配失败等极端情况：落回下面的旧路线，宁可比原来丑也不能不出效果
    }

    const size_t need = (size_t)w * h * 4;
    if (lowBuf.size() < need) lowBuf.resize(need);
    if (scratch.size() < need) scratch.resize(need);

    // 低频层用**双边迭代**而不是大半径高斯。两个原因：
    //   1) 保边：高斯是各向同性的，会把边缘也糊进低频，导致 (src-low) 在边缘
    //      处出现大差值，幅度门控只能部分救回来（实测大幅度区掉到 92%）；
    //      双边在边缘处几乎不平均，(src-low) 本来就接近 0。
    //   2) 便宜：r=2 的双边已经优化过（ROI + 多线程），迭代几次仍比 σ=3 的
    //      19-tap 可分离高斯便宜得多（实测高斯 1080p 要 34 ms，超预算）。
    // 迭代 N 次把等效半径推到 N×r，同时每次都不跨边缘。
    if (p.lowMode == 1) {
        // 引导滤波低频：O(1)/像素，半径与成本无关，且输出是局部线性的
        // （q = a·I + b），不会像双边迭代那样把平坦区压成平台再出现台阶。
        GuideParams gp;
        gp.radius = p.guideRadius;
        gp.eps = p.guideEps;
        guidedSmoothRoi(src, &lowBuf[0], w, h, gp, roi, threads, guideScratch);
        freqComposite(src, &lowBuf[0], dst, w, h,
                      (float)p.strength / 100.0f, p.magLo, p.magHi, p.grain,
                      roi, threads);
        return;
    }

    const int iters = (p.iters < 1) ? 1 : p.iters;
    const int r = (p.radius > 0) ? p.radius : 2;

    // 每一轮迭代都会把「有效区域」向外扩 r 像素（边缘像素的邻域要读到外面）。
    // 所以迭代 N 轮必须用外扩 N×r 的 ROI 跑，否则第 2 轮开始就会在边界读到
    // 上一轮没写过的残留数据 —— 实测 ROI 内边界会出现 maxdiff=7 的偏差。
    // 最后只在原始 roi 内合成，多算的那一圈对外不可见。
    RoiRect wide = roi;
    const int grow = r * iters;
    wide.x0 = (roi.x0 - grow < 0) ? 0 : roi.x0 - grow;
    wide.y0 = (roi.y0 - grow < 0) ? 0 : roi.y0 - grow;
    wide.x1 = (roi.x1 + grow > w) ? w : roi.x1 + grow;
    wide.y1 = (roi.y1 + grow > h) ? h : roi.y1 + grow;

    bilateralRgbaRoi(src, &lowBuf[0], w, h, r, p.sigmaSpace,
                     p.sigmaColor, wide, threads);
    unsigned char* cur = &lowBuf[0];
    unsigned char* alt = &scratch[0];
    for (int i = 1; i < iters; i++) {
        bilateralRgbaRoi(cur, alt, w, h, r, p.sigmaSpace, p.sigmaColor,
                         wide, threads);
        std::swap(cur, alt);
    }
    freqComposite(src, cur, dst, w, h,
                  (float)p.strength / 100.0f, p.magLo, p.magHi, p.grain,
                  roi, threads);
}

}  // namespace beautycore

namespace beautycore {

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// 数据来源：06_离线验证\全项对齐_20261030\tone_curve.py
//   （绕开本工程 3.x 用 CPU 顶替的那几项），在 3 张真机帧的肤色掩码内
//   按输入灰阶分箱统计输出。箱内 σ：clarity 0.08~0.27、color_level
//   0.36~1.24、red_level 0.73 —— 只有零点几灰阶，说明它们是**纯颜色变换**。
//
// 结论（推翻两条旧认知）：
//   ① 「清晰」不是局部对比/中频增益，是 S 形对比曲线 + 轻微暖调（96→92、
//      160→170、200→210）。原来那套 12px 中频回填在语义上就是错的。
//   ② 「红润」不是加红，是**只压绿通道**（峰值 -5 @96~128 灰阶，
//      224 灰阶以上归零），R 基本不动、B 微升。旧实现加 R 压 B 是另一种观感。
//
// 表：5 档（面板 0/25/50/75/100）× 3 通道 × 17 锚点（输入 0,16,...,240,255）。
// 档位与输入值都线性插值。锚点外的区间夹到端点。
static const unsigned char kClarityLut5[5][3][17] = {
    { /* panel 0 = identity */
      {  0, 16, 32, 48, 64, 80, 96,112,128,144,160,176,192,208,224,240,255},
      {  0, 16, 32, 48, 64, 80, 96,112,128,144,160,176,192,208,224,240,255},
      {  0, 16, 32, 48, 64, 80, 96,112,128,144,160,176,192,208,224,240,255},
    },
    { /* 0.25 */
      {  0, 16, 32, 47, 62, 78, 95,112,129,146,162,179,195,210,225,241,255},
      {  0, 16, 31, 46, 62, 79, 95,112,129,146,163,179,194,209,224,240,255},
      {  0, 16, 31, 46, 62, 79, 95,112,129,146,163,179,195,209,225,240,255},
    },
    { /* 0.5 */
      {  0, 16, 32, 46, 60, 77, 94,112,129,147,165,182,198,212,227,241,255},
      {  0, 16, 29, 44, 60, 77, 95,113,131,149,166,182,195,211,225,240,255},
      {  0, 16, 29, 44, 60, 77, 95,112,131,149,166,182,197,211,226,240,255},
    },
    { /* 0.75 */
      {  0, 16, 32, 45, 58, 75, 93,111,130,149,167,185,200,215,229,241,255},
      {  0, 16, 28, 42, 58, 76, 94,113,133,151,169,185,197,212,225,241,255},
      {  0, 16, 28, 42, 58, 76, 94,113,132,151,169,185,200,212,227,241,255},
    },
    { /* 1.0 */
      {  0, 16, 32, 43, 56, 74, 92,111,131,151,170,188,203,217,230,242,255},
      {  0, 16, 26, 40, 56, 74, 94,114,134,154,172,188,199,214,226,241,255},
      {  0, 16, 26, 41, 56, 74, 93,113,133,153,171,188,203,214,228,241,255},
    },
};

static const unsigned char kWhitenLut5[5][3][17] = {
    { /* panel 0 = identity */
      {  0, 16, 32, 48, 64, 80, 96,112,128,144,160,176,192,208,224,240,255},
      {  0, 16, 32, 48, 64, 80, 96,112,128,144,160,176,192,208,224,240,255},
      {  0, 16, 32, 48, 64, 80, 96,112,128,144,160,176,192,208,224,240,255},
    },
    { /* 0.25 */
      {  0, 16, 32, 49, 65, 82, 99,115,132,148,164,179,195,210,225,241,255},
      {  0, 16, 33, 49, 66, 82, 99,116,132,148,163,179,194,209,225,241,255},
      {  0, 16, 32, 49, 66, 83,100,116,133,149,164,179,195,210,225,240,255},
    },
    { /* 0.5 */
      {  0, 16, 32, 50, 67, 85,102,119,136,152,167,182,197,212,227,241,255},
      {  0, 16, 33, 51, 68, 85,103,119,136,152,167,182,196,211,225,241,255},
      {  0, 16, 32, 51, 68, 86,104,121,137,153,168,182,198,211,227,241,255},
    },
    { /* 0.75 */
      {  0, 16, 32, 50, 68, 87,105,122,140,156,171,185,200,214,228,242,254},
      {  0, 16, 34, 52, 69, 87,106,123,140,156,170,185,197,212,226,242,255},
      {  0, 16, 32, 52, 70, 89,108,125,142,158,172,186,201,213,228,241,255},
    },
    { /* 1.0 */
      {  0, 16, 32, 51, 70, 89,108,126,144,160,174,188,203,216,230,242,254},
      {  0, 16, 35, 54, 71, 90,109,126,143,159,174,187,199,214,227,242,255},
      {  0, 16, 32, 53, 72, 92,112,129,146,162,176,189,204,215,230,242,255},
    },
};

// 红润：只有绿通道被压（面板 100 档实测），R 不动、B 微升。
static const signed char kRosyG17[17] = {0,0,-4,-4,-5,-5,-5,-5,-4,-4,-3,-3,-1,-1,0,0,0};
static const signed char kRosyB17[17] = {0,0, 2, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1,0,0};

namespace {

// 17 锚点表（步长 16，最后一点 255）线性插值。
inline float lut17(const unsigned char* t, float v) {
    const float p = v * (1.0f / 16.0f);
    if (p >= 16.0f) return (float)t[16];
    if (p <= 0.0f) return (float)t[0];
    const int i = (int)p;
    const float f = p - (float)i;
    return (float)t[i] + ((float)t[i + 1] - (float)t[i]) * f;
}

inline float dlt17(const signed char* t, float v) {
    const float p = v * (1.0f / 16.0f);
    if (p >= 16.0f) return (float)t[16];
    if (p <= 0.0f) return (float)t[0];
    const int i = (int)p;
    const float f = p - (float)i;
    return (float)t[i] + ((float)t[i + 1] - (float)t[i]) * f;
}

// 档位插值：0..1 → 表索引 0..4
struct Lv5 {
    int i0;
    float f;
    explicit Lv5(float a) {
        float x = a * 4.0f;
        if (x < 0.0f) x = 0.0f;
        if (x > 3.999f) x = 3.999f;
        i0 = (int)x;
        f = x - (float)i0;
    }
    inline float at(const unsigned char t[5][3][17], int c, float v) const {
        const float a = lut17(t[i0][c], v);
        const float b = lut17(t[i0 + 1][c], v);
        return a + (b - a) * f;
    }
};

}  // namespace

namespace {

// 色彩三段（清晰 / 美白 / 红润）是否**整帧施加**（不乘皮肤掩码）。
//
// 默认 1 —— 口径与 GPU 版 `BEAUTY_TONE_GLOBAL=1` 完全一致，也是本版要修的
// 「手遮脸 → 美白遮罩叠到手部」的修法本身。
//
// 为什么这三段不该乘掩码：它们是**纯逐像素颜色表**，与位置、邻域都无关
// （实测箱内 σ 只有零点几灰阶，见上面 LUT 的注释）。乘上掩码之后，掩码的
// 边界（椭圆 / 脸框裁切 / 脖子矩形）就变成一条可见的色界。手往脸上一搭，
// 脸框与肤色椭圆都还罩得住手背（手背是肤色，YCbCr 判据必然放行），那条
// 色界于是正好切在手背上 —— 用户看到的就是「一块美白遮罩盖在手部」。
// 整帧施加后画面里根本不存在这条边界：手拿到的是与全画面同一条曲线，
// 不会再出现一个贴在手背上的椭圆。
//
// 只放弃**色调**这条链上的空间选区。磨皮 / 锐化 / 五官五项仍然按皮肤掩码走
// —— 那几项要的是「只动皮肤」，而色调要的是「整幅一致的色彩」。
//
// 回退：`BEAUTY_TONE_GLOBAL=0` 恢复 1.0.1.0 及以前的行为（只在 roi 内、
// mask>0 的像素上施加；背景逐字节不变，旧 golden 用它可以原样复现）。
// 只读一次环境变量：色调每帧都跑，getenv + 字符串比较会有可测开销。
bool toneGlobal() {
    static const bool v = [] {
        const char* e = beauty_env("BEAUTY_TONE_GLOBAL");
        return !(e && e[0] == '0');
    }();
    return v;
}

}  // namespace

// 1.0.11.0（A3）：整数复合表开关，默认开。
// 放在匿名命名空间外，因为滤镜侧 init 日志要打「跑的是哪条路」。
bool toneIntLutOn() {
    static const bool v = [] {
        const char* e = beauty_env("BEAUTY_TONE_LUT");
        return !(e && e[0] == '0');
    }();
    return v;
}

bool toneColor(unsigned char* dst, int w, int h,
               const unsigned char* mask, const RoiRect& roi,
               float clarity, float whiten, float rosy, int threads) {
    if (!dst || !mask || roi.empty()) return false;
    if (clarity < 0.0f) clarity = 0.0f;
    if (clarity > 1.0f) clarity = 1.0f;
    if (whiten < 0.0f) whiten = 0.0f;
    if (whiten > 1.0f) whiten = 1.0f;
    if (rosy < 0.0f) rosy = 0.0f;
    if (rosy > 1.0f) rosy = 1.0f;
    if (clarity <= 0.0f && whiten <= 0.0f && rosy <= 0.0f) return false;

    const bool doClar = (clarity > 0.0f);
    const bool doWhiten = (whiten > 0.0f);
    const bool doRosy = (rosy > 0.0f);
    const Lv5 lc(clarity), lw(whiten);

    // 整帧模式跳过掩码与 ROI；回退模式两种都用（见 toneGlobal 的注释）。
    const bool global = toneGlobal();
    const int rx0 = global ? 0 : roi.x0;
    const int rx1 = global ? w : roi.x1;
    const int ry0 = global ? 0 : roi.y0;
    const int ry1 = global ? h : roi.y1;

    // 17 锚点表**预展开成 256 项**（每通道一张）。
    //
    // 为什么必须做：整帧模式下每像素要跑 2 次 lut17（档位 + 取值两级插值）×
    // 3 通道，4K 单线程实测 +63 ms（29 → 92 ms），付不起。输入本来就是
    // 0..255 的整数，而 lut17 对整数只做一次线性插值 —— 缓存下来值不变，
    // 展开在数学上与原式**逐位等价**（GPU 版的 444,528 采样对拍偏差 0）。
    // 表在每次调用重建一次（768 次求值），相对整帧可以忽略。
    float tC[3][256], tW[3][256], tG[256], tB[256];
    if (doClar)
        for (int v = 0; v < 256; ++v)
            for (int c = 0; c < 3; ++c) tC[c][v] = lc.at(kClarityLut5, c, (float)v);
    if (doWhiten)
        for (int v = 0; v < 256; ++v)
            for (int c = 0; c < 3; ++c) tW[c][v] = lw.at(kWhitenLut5, c, (float)v);
    if (doRosy)
        for (int v = 0; v < 256; ++v) {
            tG[v] = dlt17(kRosyG17, (float)v);
            tB[v] = dlt17(kRosyB17, (float)v);
        }

    // 查表 + 小数线性插值。17 锚点表在每 16 级内线性，所以本式与 lut17(v)
    // 逐位等价（v 可以是「清晰」级联之后的非整数）。
    auto tab = [](const float* t, float v) {
        if (v <= 0.0f) return t[0];
        if (v >= 255.0f) return t[255];
        const int i = (int)v;
        const float f = v - (float)i;
        return t[i] + (t[i + 1] - t[i]) * f;
    };

    // ---- 1.0.11.0（A3）：整帧模式走「整数复合表」---------------------------
    // 整帧模式里 sk 恒等于 1.0，于是「清晰 → 美白 → 红润」对每个通道就是一个
    // **只取决于输入字节的纯函数**：输入 0..255 共 256 种，输出也只有 256 种。
    // 把它预计算成 3 张 256 项 uint8 表，每像素就只剩 3 次查表 + 3 次存，
    // 省掉每像素 3~9 次浮点插值、9 个分支和 6 次 byte↔float 往返。
    //
    // 逐字节等价性：表里的算式与下面逐像素版本**逐字相同**。唯一被「简化」的
    // 是 * sk，而 sk 在这里就是 1.0f —— 乘 1.0f 在 IEEE-754 下是精确的，
    // `r += (tab - r) * 1.0f` 与逐像素版 `r += (tab - r) * sk` 得到同一个 float。
    // 所以不能把 `r += (tab - r)` 手写成 `r = tab`（那是代数等价、不是浮点等价）。
    //
    // 掩码回退模式（BEAUTY_TONE_GLOBAL=0）不走这条：那里 sk 随像素变，没法查表。
    if (global && toneIntLutOn()) {
        unsigned char uR[256], uG[256], uB[256];
        for (int v = 0; v < 256; ++v) {
            float r = (float)v, g = (float)v, b = (float)v;
            if (doClar) {
                r += (tab(tC[0], r) - r) * 1.0f;
                g += (tab(tC[1], g) - g) * 1.0f;
                b += (tab(tC[2], b) - b) * 1.0f;
            }
            if (doWhiten) {
                r += (tab(tW[0], r) - r) * 1.0f;
                g += (tab(tW[1], g) - g) * 1.0f;
                b += (tab(tW[2], b) - b) * 1.0f;
            }
            if (doRosy) {
                g += tab(tG, g) * rosy * 1.0f;
                b += tab(tB, b) * rosy * 1.0f;
            }
            uR[v] = (unsigned char)(r < 0 ? 0 : (r > 255.0f ? 255.0f : r + 0.5f));
            uG[v] = (unsigned char)(g < 0 ? 0 : (g > 255.0f ? 255.0f : g + 0.5f));
            uB[v] = (unsigned char)(b < 0 ? 0 : (b > 255.0f ? 255.0f : b + 0.5f));
        }
        // 1.0.12.0（A6）：顺手把 A 置 255。
        // 这段本来就是整帧读改写 8.3 MB，A 是同一 cache line 里的第 4 个字节，
        // 边际成本≈0；而独立的 forceOpaque 要为此再完整遍历一遍整帧。
        // 写成一个 32 位存而不是 4 次 8 位存：小端下 0xFF000000 | B<<16 | G<<8 | R
        // 正好是 RGBA 四字节，一次读改写比「3 次查表存 + 1 次 A 存」少一半访存。
        // p 每像素走 4 字节、dst 至少 8 字节对齐，所以 32 位对齐安全。
        runRows(0, h, threads, [&](int yBegin, int yEnd) {
            for (int y = yBegin; y < yEnd; y++) {
                unsigned char* p = dst + (size_t)y * (size_t)w * 4;
                for (int x = 0; x < w; x++, p += 4) {
                    const uint32_t v = (uint32_t)uR[p[0]]
                                     | ((uint32_t)uG[p[1]] << 8)
                                     | ((uint32_t)uB[p[2]] << 16)
                                     | 0xFF000000u;
                    *(uint32_t*)(void*)p = v;
                }
            }
        });
        return true;
    }

    runRows(ry0, ry1, threads, [&](int yBegin, int yEnd) {
        for (int y = yBegin; y < yEnd; y++) {
            const size_t rowOff = (size_t)y * w;
            for (int x = rx0; x < rx1; x++) {
                float sk;
                if (global) {
                    sk = 1.0f;                  // 整帧施加：不存在掩码边界
                } else {
                    const unsigned char mv = mask[rowOff + x];
                    if (mv == 0) continue;      // 非皮肤：一个字节都不动
                    sk = (float)mv * (1.0f / 255.0f);
                }
                const size_t o = (rowOff + x) * 4;

                float r = (float)dst[o + 0];
                float g = (float)dst[o + 1];
                float b = (float)dst[o + 2];

                // 这个顺序保证「清晰抬对比不会把美白抬亮压平」（先结构后提亮）。
                if (doClar) {
                    r += (tab(tC[0], r) - r) * sk;
                    g += (tab(tC[1], g) - g) * sk;
                    b += (tab(tC[2], b) - b) * sk;
                }
                if (doWhiten) {
                    r += (tab(tW[0], r) - r) * sk;
                    g += (tab(tW[1], g) - g) * sk;
                    b += (tab(tW[2], b) - b) * sk;
                }
                if (doRosy) {
                    g += tab(tG, g) * rosy * sk;
                    b += tab(tB, b) * rosy * sk;
                }

                dst[o + 0] = (unsigned char)(r < 0 ? 0 : (r > 255.0f ? 255.0f : r + 0.5f));
                dst[o + 1] = (unsigned char)(g < 0 ? 0 : (g > 255.0f ? 255.0f : g + 0.5f));
                dst[o + 2] = (unsigned char)(b < 0 ? 0 : (b > 255.0f ? 255.0f : b + 0.5f));
            }
        }
    });
    // 这条路径没碰 A（掩码模式下非皮肤像素必须原样保留，浮点模式也没顺带写过），
    // 交回调用方兜底。
    return false;
}

void toneWhitenRosy(unsigned char* dst, int w, int h,
                    const unsigned char* mask, const RoiRect& roi,
                    float whiten, float rosy, int threads) {
    toneColor(dst, w, h, mask, roi, 0.0f, whiten, rosy, threads);
}

}  // namespace beautycore
