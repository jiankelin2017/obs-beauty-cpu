//
// 解码公式是从实测反推的（640×640 上 cv2.FaceDetectorYN 当真值校准）：
//     cx = (col + bx) * stride
//     cy = (row + by) * stride
//     w  = exp(bw) * stride
//     h  = exp(bh) * stride
//     score = sqrt(cls * obj)
// 校验依据：stride=32 上最佳 anchor 解出 cx≈327.9/cy≈278.7、w≈109.9，
// 与 cv2 的 324.2/276.0、111.3 相差不到 3%。

#include "beauty_face.h"

#include "beauty_onnx.h"

#include <cmath>
#include <cstring>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

namespace beautycore {

namespace {

// 默认推理边长。实际值放在 FaceDetector::inputSize_ 里（可运行期调整）。
const int kDefaultInputSize = 640;

// 给 2 个线程就能砍掉近一半，且不会把 OBS 的编码线程挤掉（编码通常占 4~6 核）。
const int kInferThreads = 2;
const int kStrides[3] = {8, 16, 32};

double nowMs() {
    static LARGE_INTEGER freq = {0};
    if (freq.QuadPart == 0) QueryPerformanceFrequency(&freq);
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)freq.QuadPart;
}

// 等比缩放 + 居中 letterbox 到 640x640。
//
// 为什么不用直接拉伸：OBS 的视频帧多是 16:9，直接拉成正方形会把脸横向压扁
void letterboxRgb(const unsigned char* src, int sw, int sh, int stride,
                  unsigned char* dst, int dw, int dh,
                  float& scale, int& ox, int& oy) {
    scale = fminf((float)dw / sw, (float)dh / sh);
    const int nw = (int)(sw * scale + 0.5f);
    const int nh = (int)(sh * scale + 0.5f);
    ox = (dw - nw) / 2;
    oy = (dh - nh) / 2;
    memset(dst, 0, (size_t)dw * dh * 3);
    for (int y = 0; y < nh; y++) {
        const float fy = (y + 0.5f) / scale - 0.5f;
        int y0 = (int)floorf(fy);
        const float wy = fy - y0;
        int y1 = y0 + 1;
        if (y0 < 0) y0 = 0;
        if (y1 >= sh) y1 = sh - 1;
        if (y0 >= sh) y0 = sh - 1;
        const unsigned char* r0 = src + (size_t)y0 * sw * stride;
        const unsigned char* r1 = src + (size_t)y1 * sw * stride;
        unsigned char* o = dst + (size_t)(oy + y) * dw * 3 + (size_t)ox * 3;
        for (int x = 0; x < nw; x++) {
            const float fx = (x + 0.5f) / scale - 0.5f;
            int x0 = (int)floorf(fx);
            const float wx = fx - x0;
            int x1 = x0 + 1;
            if (x0 < 0) x0 = 0;
            if (x1 >= sw) x1 = sw - 1;
            if (x0 >= sw) x0 = sw - 1;
            for (int k = 0; k < 3; k++) {
                const float a = r0[(size_t)x0 * stride + k] * (1 - wx) +
                                r0[(size_t)x1 * stride + k] * wx;
                const float b = r1[(size_t)x0 * stride + k] * (1 - wx) +
                                r1[(size_t)x1 * stride + k] * wx;
                o[(size_t)x * 3 + k] = (unsigned char)(a * (1 - wy) + b * wy + 0.5f);
            }
        }
    }
}

// 带输入旋转的 letterbox（1.0.3.0，从 GPU 版 2.13.1 移植）—— 把旋转做进重采样。
//
// 契约：产出的 dst 是「源图绕其自身中心旋转 +rot 后的整图」的 letterbox 结果，
// 也就是检测模型看到的是**摆正了的人脸**；输出的 scale/ox/oy 与 letterboxRgb
// 同义，只是基准换成旋转后尺寸 (rw,rh)。因此 decode 出来的框落在「旋转后整图」
// 坐标系里，调用方必须再用 invRotateFace(..., rw, rh, sw, sh) 反变换回源坐标。
//
// 方向约定：逐字照抄 beauty_core.cpp 的 invRotatePoint() 的向量式，两处共用同一
// 组式子 —— "顺时针/逆时针"这种字面说法就不再是论据，谁也不用猜。
//
// 为什么不先物理旋转再 letterbox：4K 一帧 33 MB，转一份要多一次全帧读写，
// 而旋转本质只是坐标变换 —— 放进采样循环等于零成本。
// （rotCanvasSize 已移出匿名命名空间 —— beauty_core.cpp 的反变换要共用同一对
//   画布尺寸，放这里的话它拿不到。）
void letterboxRgbRot(const unsigned char* src, int sw, int sh, int stride,
                     unsigned char* dst, int dw, int dh, float rot,
                     float& scale, int& ox, int& oy) {
    // 1.0.5.0：rot 从 int 放宽到 float。90 的整数倍仍走原来的整数分支
    // （case 90/180/270 三个式子一个字节都没动），任意角度走一般式 ——
    // 一般式在 0/90/180/270 上算出来的结果与 switch 逐位相同，见函数尾注释。
    const int qi = (int)lroundf(rot);
    const bool axis = (fabsf(rot - (float)qi) < 0.01f) && ((qi % 90) == 0);
    const int q = ((qi % 360) + 360) % 360;
    float rwf = 0.0f, rhf = 0.0f;
    rotCanvasSize(rot, sw, sh, rwf, rhf);
    scale = fminf((float)dw / rwf, (float)dh / rhf);
    const int nw = (int)(rwf * scale + 0.5f);
    const int nh = (int)(rhf * scale + 0.5f);
    ox = (dw - nw) / 2;
    oy = (dh - nh) / 2;
    memset(dst, 0, (size_t)dw * dh * 3);
    // 两个坐标系都以「像素中心」为原点，与 invRotatePoint 的 (W-1)*0.5 一致。
    const float crx = (rwf - 1.0f) * 0.5f, cry = (rhf - 1.0f) * 0.5f;
    const float csx = (sw - 1) * 0.5f, csy = (sh - 1) * 0.5f;
    const float th = rot * 3.14159265358979323846f / 180.0f;
    const float ct = cosf(th), st = sinf(th);
    for (int y = 0; y < nh; y++) {
        const float ry = (y + 0.5f) / scale - 0.5f;
        unsigned char* o = dst + (size_t)(oy + y) * dw * 3 + (size_t)ox * 3;
        for (int x = 0; x < nw; x++) {
            const float rx = (x + 0.5f) / scale - 0.5f;
            const float dx = rx - crx, dy = ry - cry;
            // 旋转后坐标 → 源坐标（invRotatePoint 的逆映射，见函数头说明）
            float sx, sy;
            if (axis) {
                switch (q) {
                case 90:  sx =  dy; sy = -dx; break;
                case 180: sx = -dx; sy = -dy; break;
                case 270: sx = -dy; sy =  dx; break;
                default:  sx =  dx; sy =  dy; break;
                }
            } else {
                sx = dx * ct + dy * st;
                sy = -dx * st + dy * ct;
            }
            sx += csx;
            sy += csy;
            int x0 = (int)floorf(sx);
            const float wx = sx - x0;
            int y0 = (int)floorf(sy);
            const float wy = sy - y0;
            int x1 = x0 + 1, y1 = y0 + 1;
            // 1.0.5.0：四条边**都**要钳位。老代码只钳了 x0/y0 的下界与 x1/y1 的上界，
            // 那在 90/270 下够用（映射只会落在画布内），但任意角度时旋转画布四角会
            // 映射到源图外 —— x1 可能是负数，`r0[x1*stride]` 就是负索引越界读，
            // 真机上直接段错误。下界两边都钳，是这次崩溃的直接修复。
            if (x0 < 0) x0 = 0;
            if (x1 < 0) x1 = 0;
            if (x0 >= sw) x0 = sw - 1;
            if (x1 >= sw) x1 = sw - 1;
            if (y0 < 0) y0 = 0;
            if (y1 < 0) y1 = 0;
            if (y0 >= sh) y0 = sh - 1;
            if (y1 >= sh) y1 = sh - 1;
            const unsigned char* r0 = src + (size_t)y0 * sw * stride;
            const unsigned char* r1 = src + (size_t)y1 * sw * stride;
            for (int k = 0; k < 3; k++) {
                const float a = r0[(size_t)x0 * stride + k] * (1 - wx) +
                                r0[(size_t)x1 * stride + k] * wx;
                const float b = r1[(size_t)x0 * stride + k] * (1 - wx) +
                                r1[(size_t)x1 * stride + k] * wx;
                o[(size_t)x * 3 + k] = (unsigned char)(a * (1 - wy) + b * wy + 0.5f);
            }
        }
    }
}

float iouOf(const FaceBox& a, const FaceBox& b) {
    const float ax2 = a.x + a.w, ay2 = a.y + a.h;
    const float bx2 = b.x + b.w, by2 = b.y + b.h;
    const float ix = fmaxf(0.f, fminf(ax2, bx2) - fmaxf(a.x, b.x));
    const float iy = fmaxf(0.f, fminf(ay2, by2) - fmaxf(a.y, b.y));
    const float inter = ix * iy;
    const float uni = a.w * a.h + b.w * b.h - inter;
    return uni > 0 ? inter / uni : 0.f;
}

}  // namespace

// 旋转画布的尺寸：把整幅 sw×sh 转 rot 度后需要多大的画布才装得下。
// 必须是**唯一出处** —— beauty_core.cpp 的 invRotateFace 要按同一对数算中心，
// 两边差 0.5 像素，检测框就会整体偏一格。
//   90 的整数倍：宽高互换（与 1.0.3.0 完全一致，整数精确）
//   任意角度：|W·cos| + |H·sin|, |W·sin| + |H·cos|
void rotCanvasSize(float rot, int sw, int sh, float& rw, float& rh) {
    const float kPi = 3.14159265358979323846f;
    const int qi = (int)lroundf(rot);
    if (fabsf(rot - (float)qi) < 0.01f && (qi % 90) == 0) {
        const int q = ((qi % 360) + 360) % 360;
        const bool swap = (q == 90 || q == 270);
        rw = (float)(swap ? sh : sw);
        rh = (float)(swap ? sw : sh);
    } else {
        const float th = rot * kPi / 180.0f;
        const float c = fabsf(cosf(th)), s = fabsf(sinf(th));
        rw = (float)sw * c + (float)sh * s;
        rh = (float)sw * s + (float)sh * c;
    }
}

bool FaceDetector::loaded() const {
    std::lock_guard<std::mutex> lk(mtx_);
    return model_ != nullptr;
}

void FaceDetector::releaseLocked() {
    delete (OnnxModel*)model_;
    model_ = nullptr;
    input_.clear();
    resized_.clear();
}

void FaceDetector::release() {
    std::lock_guard<std::mutex> lk(mtx_);
    releaseLocked();
}

void FaceDetector::setInputSize(int px) {
    std::lock_guard<std::mutex> lk(mtx_);
    if (fixedSize_) return;      // 模型写死了尺寸，改了会让推理直接报错
    int s = px;
    if (s < 160) s = 160;
    if (s > 1024) s = 1024;
    s = (s / 32) * 32;      // stride 8/16/32 都要求整除，向下取整最省事
    if (s < 160) s = 160;
    inputSize_ = s;
}

bool FaceDetector::load(const char* modelPath, std::string& err) {
    // 1.0.13.4：load 自己也持锁。它不再调 release()（那会二次加锁死在这里），
    // 改用 releaseLocked()。
    std::lock_guard<std::mutex> lk(mtx_);
    releaseLocked();
    inputSize_ = kDefaultInputSize;   // 动态 shape 时按默认值跑
    fixedSize_ = false;
    OnnxModel* m = new OnnxModel();
    if (!m->load(modelPath, err, kInferThreads)) {
        delete m;
        return false;
    }
    // 但别家导出的可能是固定 shape —— 那种情况下要跟着模型走，否则推理会报错。
    const std::vector<int64_t>& sh = m->inputShape();
    if (sh.size() != 4 || sh[1] != 3) {
        err = "模型输入不是 1x3xHxW";
        delete m;
        return false;
    }
    if (sh[2] > 0 && sh[3] > 0 && sh[2] == sh[3]) {
        inputSize_ = (int)sh[2];   // 固定 shape：必须用它，不能自己选
        fixedSize_ = true;
    }
    model_ = m;
    return true;
}

bool FaceDetector::detect(const unsigned char* rgb, int w, int h,
                          std::vector<FaceBox>& faces, std::string& err,
                          float conf, float nms, int stride, float rotateDeg,
                          DetMeta* out) {
    // 1.0.13.4：整段串行。下面所有成员缓冲（resized_ / input_ / bestScore_ /
    // lastMs_）都是这一份实例的，两个 slot 同时进来会互相踩 —— 见头文件注释。
    std::lock_guard<std::mutex> lk(mtx_);
    faces.clear();
    if (out) { out->best = 0.0f; out->ms = 0.0; }
    if (!model_) { err = "检测模型未加载"; return false; }
    if (!rgb || w <= 0 || h <= 0) { err = "输入无效"; return false; }
    const double t0 = nowMs();

    const int S = inputSize_;
    bestScore_ = 0.f;
    resized_.resize((size_t)S * S * 3);
    float scale = 1.f;
    int ox = 0, oy = 0;
    // 1.0.3.0：rot=0 走原函数（逐字节不变），≠0 走带旋转的重采样。
    // 1.0.5.0：接受任意角度（±45 用于「头歪」补偿）。90 的整数倍仍走整数分支；
    // 非整数的极端值（NaN / 巨值）归一化到 0，避免造出宽高错位的画布。
    float rot = 0.0f;
    if (std::isfinite(rotateDeg)) {
        float m = fmodf(rotateDeg, 360.0f);
        if (m < 0.0f) m += 360.0f;
        rot = m;
    }
    if (rot == 0.0f)
        letterboxRgb(rgb, w, h, stride, &resized_[0], S, S, scale, ox, oy);
    else
        letterboxRgbRot(rgb, w, h, stride, &resized_[0], S, S, rot, scale, ox, oy);

    input_.resize((size_t)3 * S * S);
    for (int y = 0; y < S; y++) {
        for (int x = 0; x < S; x++) {
            const unsigned char* p = &resized_[((size_t)y * S + x) * 3];
            const size_t i = (size_t)y * S + x;
            input_[i] = (float)p[0];                                    // R
            input_[i + (size_t)S * S] = (float)p[1];  // G
            input_[i + 2 * (size_t)S * S] = (float)p[2];
        }
    }

    std::vector<int64_t> shape{1, 3, S, S};
    std::vector<OnnxTensor> outs;
    if (!((OnnxModel*)model_)->run(input_.data(), shape, outs, err)) return false;

    // 12 个输出：cls/obj/bbox/kps × stride 8/16/32，按名字找（不依赖顺序）
    auto find = [&](const char* name) -> const OnnxTensor* {
        for (size_t i = 0; i < outs.size(); i++)
            if (strcmp(((OnnxModel*)model_)->outputName((int)i), name) == 0)
                return &outs[i];
        return nullptr;
    };

    std::vector<FaceBox> cand;
    for (int si = 0; si < 3; si++) {
        const int st = kStrides[si];
        char nb[16];
        snprintf(nb, sizeof(nb), "cls_%d", st);
        const OnnxTensor* cls = find(nb);
        snprintf(nb, sizeof(nb), "obj_%d", st);
        const OnnxTensor* obj = find(nb);
        snprintf(nb, sizeof(nb), "bbox_%d", st);
        const OnnxTensor* bbox = find(nb);
        if (!cls || !obj || !bbox) continue;
        snprintf(nb, sizeof(nb), "kps_%d", st);
        const OnnxTensor* kps = find(nb);   // 5 个点 × (x,y)，可缺省

        const int cols = S / st;
        const int rows = S / st;
        const int n = cols * rows;
        if ((int)cls->data.size() < n || (int)obj->data.size() < n) continue;
        if ((int)bbox->data.size() < n * 4) continue;

        for (int i = 0; i < n; i++) {
            const float score = sqrtf(cls->data[i] * obj->data[i]);
            if (score > bestScore_) bestScore_ = score;
            if (score < conf) continue;
            const int row = i / cols, col = i % cols;
            const float bx = bbox->data[i * 4 + 0];
            const float by = bbox->data[i * 4 + 1];
            const float bw = bbox->data[i * 4 + 2];
            const float bh = bbox->data[i * 4 + 3];
            const float cx = (col + bx) * st;
            const float cy = (row + by) * st;
            const float fw = expf(bw) * st;
            const float fh = expf(bh) * st;

            FaceBox f;
            // letterbox 坐标 → 原图坐标：先减黑边偏移，再除以缩放比
            f.x = (cx - fw * 0.5f - ox) / scale;
            f.y = (cy - fh * 0.5f - oy) / scale;
            f.w = fw / scale;
            f.h = fh / scale;
            f.score = score;
            // 关键点解码与 bbox 同构：值相对 cell 原点，乘 stride 得 letterbox 坐标，
            // 再减黑边、除缩放比回到原图坐标。
            if (kps && (int)kps->data.size() >= (i + 1) * 10) {
                bool ok = true;
                for (int p = 0; p < 5; p++) {
                    const float kx = (col + kps->data[i * 10 + p * 2 + 0]) * st;
                    const float ky = (row + kps->data[i * 10 + p * 2 + 1]) * st;
                    f.kps[p * 2 + 0] = (kx - ox) / scale;
                    f.kps[p * 2 + 1] = (ky - oy) / scale;
                    if (!(f.kps[p * 2 + 0] > -1e6f && f.kps[p * 2 + 0] < 1e6f)) ok = false;
                }
                f.hasKps = ok;
            }
            cand.push_back(f);
        }
    }

    // 贪心 NMS
    for (size_t i = 0; i < cand.size(); i++)
        for (size_t j = i + 1; j < cand.size(); j++)
            if (cand[j].score > cand[i].score) std::swap(cand[i], cand[j]);
    for (size_t i = 0; i < cand.size(); i++) {
        if (cand[i].score <= 0) continue;
        faces.push_back(cand[i]);
        for (size_t j = i + 1; j < cand.size(); j++)
            if (cand[j].score > 0 && iouOf(cand[i], cand[j]) > nms)
                cand[j].score = 0;
    }
    lastMs_ = nowMs() - t0;
    if (out) { out->best = bestScore_; out->ms = lastMs_; }
    return true;
}

}  // namespace beautycore
