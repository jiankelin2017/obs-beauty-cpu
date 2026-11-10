// det_bench.cpp - 单帧人脸检测诊断（1.0.5.0 临时工具）
//
// 为什么需要它：cpu_bench 只报「掩码 ROI 是多少毫秒」，看不到检测框本身。
// 排查「头歪 45° 补偿后 ROI 反而变大 7 倍」时，必须看到 detect() 吐出来的
// 原始框、以及 invRotateFace 之后落回源坐标的框，否则分不清是「模型给了个
// 假框」还是「反变换算错」。
//
// 用法：
//   det_bench.exe <frame.raw> <w> <h> [角度1 角度2 ...]
//   frame.raw 是 RGBA（stride=4），角度缺省 0 45 -45 90 270
//
// 输出：每个角度一行的 faces 数、最高分、框（旋转后坐标系）与反变换后的框。
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>

#include "beauty_face.h"

using namespace beautycore;

// 与 beauty_core.cpp 的 invRotatePoint 必须逐字一致（同一组向量式）
static void invPoint(float px, float py, float rot, float Wr, float Hr,
                     float Ws, float Hs, float& ox, float& oy) {
    const float crx = (Wr - 1) * 0.5f, cry = (Hr - 1) * 0.5f;
    const float csx = (Ws - 1) * 0.5f, csy = (Hs - 1) * 0.5f;
    const float dx = px - crx, dy = py - cry;
    float rx = dx, ry = dy;
    const int qi = (int)lroundf(rot);
    if (fabsf(rot - (float)qi) < 0.01f && (qi % 90) == 0) {
        switch (((qi % 360) + 360) % 360) {
        case 90:  rx =  dy; ry = -dx; break;
        case 270: rx = -dy; ry =  dx; break;
        case 180: rx = -dx; ry = -dy; break;
        default: break;
        }
    } else {
        const float th = rot * 3.14159265358979323846f / 180.0f;
        const float ct = cosf(th), st = sinf(th);
        rx = dx * ct + dy * st;
        ry = -dx * st + dy * ct;
    }
    ox = rx + csx;
    oy = ry + csy;
}

int main(int argc, char** argv) {
    if (argc < 4) {
        printf("用法: det_bench.exe <frame.raw> <w> <h> [角度...]\n");
        return 2;
    }
    const char* path = argv[1];
    const int w = atoi(argv[2]);
    const int h = atoi(argv[3]);
    std::vector<float> angs;
    for (int i = 4; i < argc; i++) angs.push_back((float)atof(argv[i]));
    if (angs.empty()) {
        angs.push_back(0.0f);  angs.push_back(45.0f); angs.push_back(-45.0f);
        angs.push_back(90.0f); angs.push_back(270.0f);
    }

    std::vector<unsigned char> buf((size_t)w * h * 4);
    FILE* fp = fopen(path, "rb");
    if (!fp) { printf("打不开 %s\n", path); return 2; }
    const size_t got = fread(&buf[0], 1, buf.size(), fp);
    fclose(fp);
    if (got != buf.size()) {
        printf("尺寸不符：读到 %zu，期望 %zu\n", got, buf.size());
        return 2;
    }

    FaceDetector det;
    std::string err;
    const char* mp = getenv("BEAUTY_FACE_MODEL");
    if (!mp || !*mp) mp = "models/yunet.onnx";
    if (!det.load(mp, err)) {
        printf("模型加载失败 %s: %s\n", mp, err.c_str());
        return 3;
    }
    printf("模型 %s 输入 %d\n", mp, det.inputSize());
    printf("帧 %dx%d\n", w, h);

    for (size_t a = 0; a < angs.size(); a++) {
        const float rot = angs[a];
        float Wr = 0.0f, Hr = 0.0f;
        rotCanvasSize(rot, w, h, Wr, Hr);
        std::vector<FaceBox> faces;
        std::string e;
        const bool ok = det.detect(&buf[0], w, h, faces, e, 0.6f, 0.3f, 4, rot);
        printf("\n=== 角度 %+.1f°（画布 %.1fx%.1f）=== detect=%s faces=%zu %s\n",
               rot, Wr, Hr, ok ? "ok" : "fail", faces.size(), e.c_str());
        for (size_t i = 0; i < faces.size(); i++) {
            const FaceBox& f = faces[i];
            printf("  [%zu] 旋转后坐标 x=%.1f y=%.1f w=%.1f h=%.1f score=%.3f\n",
                   i, f.x, f.y, f.w, f.h, f.score);
            // 1.0.5.0：倾斜探测的「像不像人脸」判据候选量。检测框在**旋转后坐标系**
            // 里恒为正立，所以这里的几何关系与 0° 检测完全同口径，可以直接拿来比。
            if (f.hasKps) {
                const float ew = sqrtf((f.kps[2] - f.kps[0]) * (f.kps[2] - f.kps[0]) +
                                       (f.kps[3] - f.kps[1]) * (f.kps[3] - f.kps[1]));
                const float mx = (f.w > f.h) ? f.w : f.h;
                const float eyeY = 0.5f * (f.kps[1] + f.kps[3]);
                const float mouthY = 0.5f * (f.kps[7] + f.kps[9]);
                bool inside = true;
                for (int k = 0; k < 10; k += 2) {
                    if (f.kps[k] < f.x - 1.0f || f.kps[k] > f.x + f.w + 1.0f) inside = false;
                    if (f.kps[k + 1] < f.y - 1.0f || f.kps[k + 1] > f.y + f.h + 1.0f) inside = false;
                }
                printf("      度量 eye/max=%.3f eye/w=%.3f 眼在上=%.3f 框高 框内=%s\n",
                       ew / mx, ew / f.w, (mouthY - eyeY) / f.h, inside ? "y" : "n");
            }
            // 反变换：与 beauty_core.cpp 的 invRotateFace 同口径
            FaceBox g = f;
            if (rot != 0.0f) {
                const int qi = (int)lroundf(rot);
                const bool axis = (fabsf(rot - (float)qi) < 0.01f) && ((qi % 90) == 0);
                if (!axis) {
                    const float cx[4] = {f.x, f.x + f.w, f.x + f.w, f.x};
                    const float cy[4] = {f.y, f.y, f.y + f.h, f.y + f.h};
                    float x0 = 1e30f, y0 = 1e30f, x1 = -1e30f, y1 = -1e30f;
                    for (int k = 0; k < 4; k++) {
                        float nx, ny;
                        invPoint(cx[k], cy[k], rot, Wr, Hr, (float)w, (float)h, nx, ny);
                        if (nx < x0) x0 = nx;
                        if (nx > x1) x1 = nx;
                        if (ny < y0) y0 = ny;
                        if (ny > y1) y1 = ny;
                    }
                    g.x = x0; g.y = y0; g.w = x1 - x0; g.h = y1 - y0;
                } else {
                    const float c0 = f.x + f.w * 0.5f, c1 = f.y + f.h * 0.5f;
                    float nx, ny;
                    invPoint(c0, c1, rot, Wr, Hr, (float)w, (float)h, nx, ny);
                    if (qi == 90 || qi == 270) { const float t = g.w; g.w = g.h; g.h = t; }
                    g.x = nx - g.w * 0.5f;
                    g.y = ny - g.h * 0.5f;
                }
            }
            const float area = (g.w > 0 && g.h > 0) ? g.w * g.h : 0.0f;
            printf("      源坐标     x=%.1f y=%.1f w=%.1f h=%.1f  面积占画面 %.1f%%\n",
                   g.x, g.y, g.w, g.h, area * 100.0f / ((float)w * h));
            if (f.hasKps) {
                printf("      关键点 ");
                for (int k = 0; k < 10; k += 2) {
                    float nx, ny;
                    invPoint(f.kps[k], f.kps[k + 1], rot, Wr, Hr, (float)w, (float)h, nx, ny);
                    printf("(% .0f,% .0f) ", nx, ny);
                }
                printf("\n");
            }
        }
    }
    return 0;
}
