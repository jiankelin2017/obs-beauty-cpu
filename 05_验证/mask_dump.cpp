// mask_dump.cpp - 掩码落盘（1.0.5.0 临时工具）
//
// 为什么需要它：cpu_bench 只报毫秒，看不到掩码**长什么样**。1.0.5.0 的头歪补偿
// 改了掩码几何（倾斜矩形），必须能亲眼确认 45° 时掩码是跟着头转的斜方框、
// 而不是把整张脸套进去的大方块，也不能糊到脸外面。
//
// 用法：mask_dump.exe <frame.raw> <w> <h> <out.pgm> [frames]
//   环境：BEAUTY_FACE_MODEL 指向 yunet.onnx；其余 BEAUTY_* 与真机一致。
//   前 frames 帧走完整 process()（把「连续无脸 → 倾斜探测 → 记住角度」那条
//   状态链跑完，并把 radius 等参数灌进去），最后一帧才把掩码抠出来落盘。
// 输出：PGM（P5）灰度掩码 + 覆盖率。
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "beauty_core.h"

int main(int argc, char** argv) {
    if (argc < 5) {
        printf("用法: mask_dump.exe <frame.raw> <w> <h> <out.pgm> [frames]\n");
        return 2;
    }
    const int w = atoi(argv[2]);
    const int h = atoi(argv[3]);
    const int n = (argc > 5) ? atoi(argv[5]) : 40;

    std::vector<unsigned char> src((size_t)w * h * 4), dst((size_t)w * h * 4);
    FILE* fp = fopen(argv[1], "rb");
    if (!fp) { printf("打不开 %s\n", argv[1]); return 2; }
    if (fread(&src[0], 1, src.size(), fp) != src.size()) {
        printf("尺寸不符：期望 %dx%d RGBA\n", w, h);
        fclose(fp);
        return 2;
    }
    fclose(fp);

    _putenv("BEAUTY_ENGINE_IMPL=core");
    if (!getenv("BEAUTY_ASYNC_DETECT")) _putenv("BEAUTY_ASYNC_DETECT=0");

    IBeautyEngine& e = beautyEngine();
    std::string err;
    bool didInit = false;
    if (!e.preheat(err, didInit) || !e.regionActive()) {
        printf("[FAIL] preheat/region: %s\n", err.c_str());
        return 1;
    }
    std::string serr;
    const int slot = e.acquireSlot(serr);
    if (slot < 0) { printf("[FAIL] acquireSlot: %s\n", serr.c_str()); return 1; }

    // 真机实测档位（与 cpu_bench 的 kProfile 同一组）
    const double prof[P_COUNT] = {26, 28, 61, 30, 59, 76, 0, 0, 100, 97, 90};
    BeautySettings s;
    for (int i = 0; i < P_COUNT; i++) s.panel[i] = prof[i];
    s.skin_detect = 1;

    for (int i = 0; i < n; i++) e.process(slot, &src[0], &dst[0], w, h, s);

    std::vector<unsigned char> mask((size_t)w * h, 0);
    const bool ok = beautyCoreComputeMask(&src[0], w, h, &mask[0]);
    size_t px = 0;
    for (size_t i = 0; i < mask.size(); i++)
        if (mask[i]) px++;
    printf("computeMask=%s  faces=%d  掩码 %zu px = %.2f%%（含羽化边缘的非零像素）\n",
           ok ? "ok" : "fail", e.lastFaces(), px,
           100.0 * (double)px / (double)mask.size());

    FILE* out = fopen(argv[4], "wb");
    if (!out) { printf("写不了 %s\n", argv[4]); return 2; }
    fprintf(out, "P5\n%d %d\n255\n", w, h);
    fwrite(&mask[0], 1, mask.size(), out);
    fclose(out);
    printf("已写 %s\n", argv[4]);
    return 0;
}
