// beauty_warp.cpp —— 美形三项（瘦脸 / 大眼 / 下巴）的位移场实现
//
// 实现要点（每一条都是踩过或算过才写的，改之前先读）：
//
// 1) **反向映射**：对每个输出像素求它的采样源坐标，再双线性取样。
//    正向映射（源→目标）会在目标上留空洞，补洞逻辑比反向映射贵得多。
//
// 2) **ROI 外扩 + 权重归零**：位移场只在脸框附近非零。如果 ROI 边界上位移
//    还有值，ROI 内外的像素就会错位，画面上表现为一条竖直/水平的硬缝。
//    所以每个权重函数都必须在 ROI 边界之前降到 0，ROI 还要比脸框外扩一圈
//    （瘦脸的侧向权重在 |u|≈1 处才最强，不扩就正好切在脸边）。
//
// 3) **坐标钳在 ROI 内**：外扩区已经包含背景，钳住不会读到 ROI 之外的
//    旧像素；不钳的话瘦脸在大幅度下会把采样点推出图像边界。
//
// 4) **位移接近 0 时直拷**：脸心一带三项位移都接近 0，直接 memcpy 一个像素
//    比 4 次双线性快得多，实测能省掉约一半耗时。
//
// 5) 没有关键点时退化：用「脸框比例」估眼位（0.38h / ±0.22w）和嘴线
//    （0.72h）。估出来的位置比关键点差，但至少不会让功能失效 ——
//    检不出关键点的帧在真机上并不罕见（侧脸、低头）。
//
// 6) **位移场建在「脸自己的坐标系」里，不是画面坐标系**（1.0.13.5）。
//    竖屏摄像头 / 场景项旋转的源，画面里的人是躺着的：引擎靠方向探测认出
//    90°/270° 并把框与五点反变换回源坐标，于是框在源坐标里是**横着**的
//    （f.w 是脸的**高**、f.h 是脸的**宽**）。旧实现在画面轴上硬算「向中线
//    水平压缩」「嘴线以下纵向压缩」，等于把瘦脸变成压脸长、把下巴压到脸的
//    侧面去 —— 用户看到的就是「形变位置不对」。
//    现在先求出脸在源图里的朝向 phi（有眼线就用眼线角，反向脸用嘴角符号
//    定 ±180°），把像素搬到 phi 的局部帧里算，再搬回去。phi == 0 时两条
//    路径的浮点表达式完全相同，**正立帧逐字节不变**。

#include "beauty_warp.h"

#include <cmath>
#include <cstring>

namespace beautycore {

namespace {

inline float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

inline float smoothstep01(float a, float b, float x) {
    if (b <= a) return x >= b ? 1.0f : 0.0f;
    const float t = clampf((x - a) / (b - a), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}

// 一张脸做位移场需要的全部几何量，先算一次，内层循环只读。
//
// 1.0.13.5：这些量都在**「循环坐标系」**里 —— 脸正立时它就是画面坐标（与
// 1.0.13.4 完全同义）；脸歪着/躺着时它是「绕脸心转过 -phi 的脸坐标系」，
// 原点仍在画面里（不挪到脸心），这样内层循环的算式一个字都不用改。
struct Geom {
    float cx = 0, cy = 0;        // 脸心（画面坐标，旋转不变）
    float fw = 0, fh = 0;        // 脸**自身**的宽 / 高（不是画面轴上的外接盒）
    float cp = 1, sp = 0;        // cos/sin(phi)：画面 → 脸坐标系
    bool  rot = false;           // phi != 0：需要逐像素搬运
    float eyeRx = 0, eyeRy = 0;  // 右眼（YuNet kps[0]）
    float eyeLx = 0, eyeLy = 0;  // 左眼（YuNet kps[1]）
    float eyeY = 0;              // 双眼平均高度
    float eyeDist = 0;           // 双眼间距，用来定「大眼」的作用半径
    float mouthY = 0;            // 嘴线高度，下巴变形的分界
    float chinY = 0;             // 下巴底（脸的下沿）
    bool hasEyes = false;        // 眼睛来自关键点（否则是比例估算）
};

Geom makeGeom(const FaceBox& f) {
    const float kPi = 3.14159265358979323846f;
    Geom g;
    g.cx = f.x + f.w * 0.5f;
    g.cy = f.y + f.h * 0.5f;

    // ---- 脸的朝向 phi ----
    // 眼线是五点里最稳的一条：它在画面里的角度就是头歪了多少；嘴角只用来
    // 定 ±180° 歧义（头朝下时眼线同样是「水平」的，单看它分不出正反）。
    float phi = 0.0f;
    bool havePhi = false;
    if (f.hasKps) {
        const float dxe = f.kps[2] - f.kps[0];
        const float dye = f.kps[3] - f.kps[1];
        if (fabsf(dxe) + fabsf(dye) > 4.0f) {
            phi = atan2f(dye, dxe);
            const float mx = (f.kps[6] + f.kps[8]) * 0.5f;
            const float myk = (f.kps[7] + f.kps[9]) * 0.5f;
            // 脸坐标系里嘴应在眼的 +y 侧（下方）；为负说明差了 180°。
            const float lyy = -sinf(phi) * (mx - g.cx) + cosf(phi) * (myk - g.cy);
            if (lyy < 0.0f) phi += kPi;
            while (phi > kPi) phi -= 2.0f * kPi;
            havePhi = true;
        }
    }
    /* 死区 8°：一是挡掉关键点噪声造成的无谓形变，二是保证**正立素材走的是
     * 原封不动的老算式**（本仓库 face_src 的眼线角就是 5.8°，落在死区里）。 */
    if (!havePhi || fabsf(phi) < 0.1396f) phi = 0.0f;
    g.cp = cosf(phi);
    g.sp = sinf(phi);
    g.rot = (phi != 0.0f);

    // ---- 脸自身的宽高 ----
    // 互换的物理原因只有一个：invRotateFace() 在 90°/270° 整数倍上把盒的 w/h
    // 对调了（那时盒的 w 其实是脸的高）。那是个**离散事实**，由 FaceBox::srcRot
    // 直接带过来。
    //
    // 1.0.13.5 曾用 |cos(phi)| >= |sin(phi)| 去猜它 —— 拿连续量猜离散事实。
    // 45° 时两个数只差 0.4%（实测 0.7085 vs 0.7057），关键点抖 0.2°，脸的
    // 宽高就被判反（107.5 ↔ 142.2，32% 的尺度跳变），画面当场闪一下。
    // 正立与 90/270 只是恰好猜对，所以问题只在歪头时暴露。
    if (f.rw > 1.0f && f.rh > 1.0f) {
        // 头歪时的紧框宽高：rw/rh 本身就是脸的宽 / 高，绝不再互换。
        g.fw = f.rw;
        g.fh = f.rh;
    } else if (f.srcRot == 90 || f.srcRot == 270) {
        g.fw = f.h;
        g.fh = f.w;
    } else {
        g.fw = f.w;
        g.fh = f.h;
    }

    if (!g.rot) {
        // ---- 老路径：画面坐标下的原式，逐字保留 ----
        g.chinY = f.y + f.h;
        g.eyeY = f.y + 0.38f * f.h;
        g.eyeRx = g.cx - 0.22f * f.w;
        g.eyeRy = g.eyeY;
        g.eyeLx = g.cx + 0.22f * f.w;
        g.eyeLy = g.eyeY;
        g.eyeDist = 0.44f * f.w;
        g.mouthY = f.y + 0.72f * f.h;
        if (f.hasKps) {
            const float r0x = f.kps[0], r0y = f.kps[1];
            const float l1x = f.kps[2], l1y = f.kps[3];
            const float d = sqrtf((l1x - r0x) * (l1x - r0x) + (l1y - r0y) * (l1y - r0y));
            if (d > 4.0f && d < 3.0f * f.w) {
                g.eyeRx = r0x;
                g.eyeRy = r0y;
                g.eyeLx = l1x;
                g.eyeLy = l1y;
                g.eyeDist = d;
                g.eyeY = (r0y + l1y) * 0.5f;
                g.hasEyes = true;
            }
            const float my = (f.kps[7] + f.kps[9]) * 0.5f;
            if (my > g.eyeY + 0.05f * f.h && my < g.chinY) g.mouthY = my;
        }
        return g;
    }

    // ---- 歪/躺路径：先把画面点搬到脸坐标系，再沿用同一套比例与判据 ----
    auto toLocal = [&](float x, float y, float& lx, float& ly) {
        const float dx = x - g.cx, dy = y - g.cy;
        lx = g.cx + (g.cp * dx + g.sp * dy);
        ly = g.cy + (-g.sp * dx + g.cp * dy);
    };
    // 比例兜底（与老式「盒顶 + 0.38h / 0.72h」等价：脸心 ± 自身高宽的比例）
    g.eyeY = g.cy - 0.12f * g.fh;
    g.eyeRx = g.cx - 0.22f * g.fw;
    g.eyeRy = g.eyeY;
    g.eyeLx = g.cx + 0.22f * g.fw;
    g.eyeLy = g.eyeY;
    g.eyeDist = 0.44f * g.fw;
    g.mouthY = g.cy + 0.22f * g.fh;
    g.chinY = g.cy + 0.5f * g.fh;
    if (f.hasKps) {
        float r0x, r0y, l1x, l1y;
        toLocal(f.kps[0], f.kps[1], r0x, r0y);
        toLocal(f.kps[2], f.kps[3], l1x, l1y);
        const float d = sqrtf((l1x - r0x) * (l1x - r0x) + (l1y - r0y) * (l1y - r0y));
        if (d > 4.0f && d < 3.0f * g.fw) {
            g.eyeRx = r0x;
            g.eyeRy = r0y;
            g.eyeLx = l1x;
            g.eyeLy = l1y;
            g.eyeDist = d;
            g.eyeY = (r0y + l1y) * 0.5f;
            g.hasEyes = true;
        }
        float m1x, m1y, m2x, m2y;
        toLocal(f.kps[6], f.kps[7], m1x, m1y);
        toLocal(f.kps[8], f.kps[9], m2x, m2y);
        const float my = (m1y + m2y) * 0.5f;
        if (my > g.eyeY + 0.05f * g.fh && my < g.chinY) g.mouthY = my;
    }
    return g;
}

}  // namespace

void warpFace(unsigned char* rgba, int w, int h, const FaceBox& f,
              const WarpParams& p, std::vector<unsigned char>& scratch) {
    if (!rgba || w <= 0 || h <= 0) return;
    if (p.thin <= 0.0f && p.eye <= 0.0f && p.chin <= 0.0f) return;
    if (!(f.w > 8.0f) || !(f.h > 8.0f)) return;

    const Geom g = makeGeom(f);
    const float acp = fabsf(g.cp), asp = fabsf(g.sp);

    // ---- ROI ----
    // 正立：脸框外扩 30% 宽 / 18% 高（原式，逐字保留）。
    // 歪/躺：位移场在脸坐标系里是「横向 0.80·fw、纵向 0.68·fh」的矩形，转到
    // 画面上是它的外接盒 —— 直接用脸框的 w/h 外扩会切掉两端，接缝就出来了。
    int x0, y0, x1, y1;
    if (!g.rot) {
        // 老路径按**画面轴**外扩，所以用 f.w / f.h 而不是 g.fw / g.fh。
        // 正立时两者相等（逐字节不变）；万一 90/270 又丢了关键点而落到这条
        // 路径上，用画面轴宽高才是对的（g.fw 那时是脸的宽，方向正好差 90°）。
        const float mx = 0.30f * f.w;
        const float my = 0.18f * f.h;
        x0 = (int)floorf(f.x - mx);
        x1 = (int)ceilf(f.x + f.w + mx);
        y0 = (int)floorf(f.y - my);
        y1 = (int)ceilf(f.y + f.h + my);
    } else {
        const float ex = acp * 0.80f * g.fw + asp * 0.68f * g.fh;
        const float ey = asp * 0.80f * g.fw + acp * 0.68f * g.fh;
        x0 = (int)floorf(g.cx - ex);
        x1 = (int)ceilf(g.cx + ex);
        y0 = (int)floorf(g.cy - ey);
        y1 = (int)ceilf(g.cy + ey);
    }
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > w) x1 = w;
    if (y1 > h) y1 = h;
    const int rw = x1 - x0;
    const int rh = y1 - y0;
    if (rw <= 2 || rh <= 2) return;

    // ---- 先把 ROI 拷进 scratch 当采样源（就地写会污染后面的取样）----
    const size_t rowBytes = (size_t)rw * 4;
    const size_t needBytes = rowBytes * (size_t)rh;
    if (scratch.size() < needBytes) scratch.resize(needBytes);
    unsigned char* src = &scratch[0];
    for (int y = 0; y < rh; y++)
        memcpy(src + (size_t)y * rowBytes,
               rgba + ((size_t)(y0 + y) * (size_t)w + (size_t)x0) * 4, rowBytes);

    // ---- 三个场的常量，循环外算好 ----
    // 大眼：作用半径取双眼间距的一半多一点（覆盖眼睛 + 眼皮 + 一点眼袋）。
    float eyeR = 0.52f * g.eyeDist;
    const float eyeMin = 0.10f * g.fw;
    const float eyeMax = 0.35f * g.fw;
    if (eyeR < eyeMin) eyeR = eyeMin;
    if (eyeR > eyeMax) eyeR = eyeMax;
    const float eyeAmp = p.eye * 0.55f;   // 满档中心放大 1.55 倍
    const bool doEye = (p.eye > 0.0f) && (eyeR > 1.0f);

    // 瘦脸：垂直高斯中心放在「眼线 → 嘴线」之间偏下，正好是脸颊。
    const float thinYc = g.eyeY + 0.62f * (g.mouthY - g.eyeY);
    const float thinSig = 0.24f * g.fh;
    const float thinK = p.thin * 0.24f;   // 满档外侧采样点外移 24%
    const bool doThin = (p.thin > 0.0f) && (thinSig > 0.5f);

    // 下巴：从嘴线往下压缩，嘴线以上不动。
    const float chinYm = g.mouthY + 0.02f * g.fh;
    const float chinSpan = g.chinY - chinYm;
    const float chinK = p.chin * 0.18f;   // 满档下巴纵向缩 18%
    const bool doChin = (p.chin > 0.0f) && (chinSpan > 1.0f);

    const float halfW = 0.5f * g.fw;

    for (int y = 0; y < rh; y++) {
        const float oy = (float)(y0 + y);
        unsigned char* out = rgba + ((size_t)(y0 + y) * (size_t)w + (size_t)x0) * 4;
        const unsigned char* srow = src + (size_t)y * rowBytes;

        for (int x = 0; x < rw; x++) {
            const float ox = (float)(x0 + x);
            /* 画面点 → 脸坐标系里的同一点。正立时 rot 为假、这里一次都不算，
             * ax/ay 就是 ox/oy —— 与 1.0.13.4 的算式完全相同。 */
            float ax = ox;
            float ay = oy;
            if (g.rot) {
                const float dx = ox - g.cx;
                const float dy = oy - g.cy;
                ax = g.cx + (g.cp * dx + g.sp * dy);
                ay = g.cy + (-g.sp * dx + g.cp * dy);
            }
            float sx = ax;
            float sy = ay;

            // ---- ① 大眼：以眼心为中心径向放大 ----
            // 采样点向眼心收拢（除以 m>1），内容就被「撑大」。
            if (doEye && g.hasEyes) {
                for (int e = 0; e < 2; e++) {
                    const float ex = e ? g.eyeLx : g.eyeRx;
                    const float ey = e ? g.eyeLy : g.eyeRy;
                    const float dx = sx - ex;
                    const float dy = sy - ey;
                    const float r2 = (dx * dx + dy * dy) / (eyeR * eyeR);
                    if (r2 >= 1.0f) continue;
                    const float q = 1.0f - r2;
                    const float fall = q * q;          // (1−r²)²：中心平、边缘陡
                    const float m = 1.0f + eyeAmp * fall;
                    sx = ex + dx / m;
                    sy = ey + dy / m;
                }
            }

            // ---- ② 瘦脸：向面中线水平压缩 ----
            // 垂直权重是高斯（只动脸颊那一段），侧向权重在 |u|≈0.1 起升、
            // 到 1.55 归零 —— 后者就是 ROI 外扩 30% 的原因。
            if (doThin) {
                /* 注意用的是 **ay**（本像素在脸坐标系里的输出位置），不是 sy：
                 * 瘦脸的垂直高斯是「画面上固定的一条带」，大眼/下巴对采样点的
                 * 挪动不该把它带着走。1.0.13.4 这里写的是 oy，正立时 ay 恒等于
                 * oy，所以两个版本逐位相同。 */
                const float dyv = (ay - thinYc) / thinSig;
                const float wv = expf(-0.5f * dyv * dyv);
                if (wv > 1e-4f) {
                    const float u = (sx - g.cx) / halfW;
                    const float au = fabsf(u);
                    const float lat = smoothstep01(0.10f, 0.80f, au) *
                                      (1.0f - smoothstep01(0.95f, 1.55f, au));
                    const float k = thinK * wv * lat;
                    if (k > 1e-4f) sx = g.cx + (sx - g.cx) * (1.0f + k);
                }
            }

            // ---- ③ 下巴：下半脸纵向压缩 ----
            // 中线强、两侧弱（lat），否则会连下颌角一起往上提，脸变方。
            if (doChin && sy > chinYm) {
                const float t = (sy - chinYm) / chinSpan;
                const float wv = smoothstep01(0.0f, 0.45f, t) *
                                 (1.0f - smoothstep01(0.92f, 1.10f, t));
                if (wv > 1e-4f) {
                    const float u = fabsf((sx - g.cx) / halfW);
                    const float lat = 1.0f - 0.60f * smoothstep01(0.20f, 1.0f, u);
                    const float k = chinK * wv * lat;
                    if (k > 1e-4f) sy = chinYm + (sy - chinYm) * (1.0f + k);
                }
            }

            // ---- 脸坐标系 → 画面 ----
            if (g.rot) {
                const float dx = sx - g.cx;
                const float dy = sy - g.cy;
                sx = g.cx + (g.cp * dx - g.sp * dy);
                sy = g.cy + (g.sp * dx + g.cp * dy);
            }

            // ---- 采样 ----
            const float dxo = sx - ox;
            const float dyo = sy - oy;
            unsigned char* dstp = out + (size_t)x * 4;

            if (dxo > -0.02f && dxo < 0.02f && dyo > -0.02f && dyo < 0.02f) {
                memcpy(dstp, srow + (size_t)x * 4, 4);   // 位移可忽略：直拷
                continue;
            }

            float lx = clampf(sx - (float)x0, 0.0f, (float)(rw - 1));
            float ly = clampf(sy - (float)y0, 0.0f, (float)(rh - 1));
            int ix = (int)lx;
            int iy = (int)ly;
            int ix1 = ix + 1;
            int iy1 = iy + 1;
            if (ix1 > rw - 1) ix1 = rw - 1;
            if (iy1 > rh - 1) iy1 = rh - 1;
            const float fx = lx - (float)ix;
            const float fy = ly - (float)iy;

            const unsigned char* p00 = src + (size_t)iy * rowBytes + (size_t)ix * 4;
            const unsigned char* p01 = src + (size_t)iy * rowBytes + (size_t)ix1 * 4;
            const unsigned char* p10 = src + (size_t)iy1 * rowBytes + (size_t)ix * 4;
            const unsigned char* p11 = src + (size_t)iy1 * rowBytes + (size_t)ix1 * 4;

            for (int c = 0; c < 4; c++) {
                const float a = (float)p00[c] * (1.0f - fx) + (float)p01[c] * fx;
                const float b = (float)p10[c] * (1.0f - fx) + (float)p11[c] * fx;
                dstp[c] = (unsigned char)(a * (1.0f - fy) + b * fy + 0.5f);
            }
        }
    }
}

}  // namespace beautycore
