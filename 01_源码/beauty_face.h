#pragma once
// ---------------------------------------------------------------------------
// beauty_face —— YuNet 人脸检测（ONNX Runtime 推理 + 自写后处理）
//
// 用途：替代 参考实现美颜库 的 fuFaceProcessor*，给皮肤掩码提供「人脸框」约束。
// 这是 S1 对拍得出的方案：肤色判据 ∩ 人脸框(grow=1.15) → IoU 0.707 / 精确率 0.875，
// 远好于纯肤色判据的 0.251 / 0.254。
//
// 模型：YuNet 2023mar（opencv_zoo，MIT 许可）。固定 640×640 输入、
// 12 个输出（cls/obj/bbox/kps × stride 8/16/32）。
//
// 为什么自己写后处理而不用 OpenCV 的 FaceDetectorYN：OpenCV 会额外带进来
// 二十多 MB 的库，而这里只需要 decode + NMS 一百多行。
// ---------------------------------------------------------------------------

#include <mutex>
#include <string>
#include <vector>

namespace beautycore {

// 一次检测的「副产物」：最高置信度与耗时。
//
// 为什么要单独从 detect() 带出来（1.0.13.4）：这两个值原本存在检测器成员上，
// 由 lastBestScore() / lastMs() 读。同一个 CoreEngine 被两个 slot 共用（渲染
// 线程跑同步检测、异步 worker 跑另一路），成员上那一份随时可能被**另一个 slot
// 的检测**改写 —— 日志里就会把 B 的置信度算到 A 的头上，调阈值时被带偏。
// 现在结果直接落到调用方（DetState.detBest），读的人拿到的一定是自己那次的值。
struct DetMeta {
    float best = 0.0f;   // 本次候选里的最高分，不受 conf 阈值与 NMS 影响
    double ms = 0.0;     // 本次 detect 的总耗时（含 letterbox 与后处理）
};

struct FaceBox {
    float x = 0, y = 0, w = 0, h = 0;   // 原图坐标
    float score = 0;
    // 1.0.5.0（头歪补偿）：人脸在画面内的**平面内倾角**（度，逆时针为正）。
    //
    // 非 0 时 x/y/w/h 是这张脸**转过 roll 之后**的轴对齐外接矩形 —— 检测在
    // 「旋转后坐标系」里给的是一个正立的紧框（rw × rh），反变换回源坐标后只能
    // 退化成外接矩形。直接拿外接矩形的 w/h 去画掩码，45° 时宽度会被撑大
    // (1.68 倍、面积 2.8 倍)，磨皮糊到脸外面去，ROI 也跟着白涨一倍。
    // 所以把「脸自己的宽高」和「倾角」一起带出来，让掩码按倾斜矩形画。
    //
    // roll == 0 时 rw/rh 恒为 0，所有下游退回 w/h —— 0/90/180/270 逐字节不变。
    float roll = 0;
    float rw = 0, rh = 0;               // 倾斜矩形自身的宽高（未外接膨胀）
    // 1.0.13.6：源（含方向补偿）转过多少度，只取 0 / 90 / 270。
    //
    // 为什么需要它：invRotateFace() 在 90°/270° 整数倍上会**对调盒的 w 与 h**
    // （那时盒的 w 其实是脸的高）。这是个离散事实，必须由检测端直接告诉下游。
    //
    // 1.0.13.5 的 beauty_warp.cpp 曾用 |cos(phi)| >= |sin(phi)| 去猜这件事，
    // 拿连续量猜离散事实 —— 45° 时那两个数只差 0.4%（实测 0.7085 vs 0.7057），
    // 关键点抖 0.2° 就把脸的宽高判反（fw 107.5 ↔ 142.2，相差 32%），画面当场
    // 闪一下。正立和 90/270 只是恰好猜对，所以只有歪头时才暴露。
    //
    // 语义：90 / 270 = 盒宽高已被对调；0 = 没对调（含 180°，它只是转半圈，
    // 宽高不变）。roll != 0 时下游改用 rw/rh，本字段不参与。
    int srcRot = 0;
    // YuNet 的 5 个关键点（原图坐标），顺序为：
    //   0 右眼  1 左眼  2 鼻尖  3 右嘴角  4 左嘴角
    // 用途：构造「五官保护区」，让磨皮在眼睛和嘴巴上减弱。
    // 这是 lumina-beauty 的 kComposeShader 里 uSmoothProtect 的做法。
    float kps[10] = {0};
    bool hasKps = false;
};

class FaceDetector {
public:
    bool load(const char* modelPath, std::string& err);
    bool loaded() const;
    void release();

    // 推理输入边长。
    //
    // 重要事实：我们用的 YuNet 2023mar ONNX **把输入声明成了固定 640x640**
    // （ORT 会报 `Got: 512 Expected: 640`）。OpenCV 能跑 320 是因为它的 dnn
    // 引擎不认模型声明的固定维度，会自己重做 shape 推断 —— 这是 OpenCV 的
    // 行为，不是模型的能力。所以本函数对固定 shape 的模型是**空操作**。
    //
    // 想真正降分辨率只有两条路：换一个原生动态导出的模型，或改模型文件的
    // dim_param 后重新做 shape 推断（后者风险高，网络内部 reshape 依赖具体
    // 尺寸）。在拿到动态模型之前，别指望这条参数能提速。
    void setInputSize(int px);
    bool inputSizeFixed() const { return fixedSize_; }
    int inputSize() const { return inputSize_; }

    // src 是紧凑或带 stride 的图。检出的人脸框以**原图坐标**返回。
    //
    // rotateDeg（1.0.3.0，从 GPU 版 2.13.1 移植）：先把源图绕自身中心旋转该角度
    // 再送进模型。**1.0.5.0 起接受任意角度**（此前只认 0/90/180/270）——
    // 目的是让「头歪 45°」也能检测（YuNet 对平面内倾斜的容忍边界在 30~40° 之间，
    // 45° 时一个框都出不来，见 05_验证/ab20261109_head_roll.md）。
    // 90 的整数倍仍走原来的整数分支，**逐字节不变**。
    // 旋转发生在 letterbox 的重采样里，**不额外分配旋转缓冲**（4K 一帧 33 MB，
    // 转一份要两次全帧读写）。
    // ⚠ 开旋转时返回的坐标落在「旋转后整图」坐标系（画布尺寸由 rotCanvasSize()
    // 给出），调用方必须用 invRotateFace 反变换回源坐标 —— 见 beauty_core.cpp。
    // conf / nms 是阈值：0.6 / 0.3 与 OpenCV 的默认一致。
    //
    // stride：每像素字节数。传 4 可以直接喂 OBS 的 RGBA 帧，**跳过「先转一份
    // 全分辨率 RGB」的中间缓冲** —— 1080p 下这一份缓冲要写 600 万字节，而
    // 检测只需要 640x640 的图，那份中间缓冲纯属浪费。
    bool detect(const unsigned char* src, int w, int h,
                std::vector<FaceBox>& faces, std::string& err,
                float conf = 0.6f, float nms = 0.3f, int stride = 3,
                float rotateDeg = 0.0f, DetMeta* out = nullptr);

    // 下面两个读的是「最近一次 detect」的成员副本，只给单线程探针（face_probe.cpp）
    // 用。引擎里请用 detect() 的 out 参数 —— 多 slot 并发时这里的值属于谁不定。
    double lastMs() const { return lastMs_; }

    // 本帧所有候选里的最高置信度（**不受 conf 阈值影响**，也不受 NMS 影响）。
    // 用途：检不出脸时判断到底是「模型没看出有脸」还是「看出来了但没到阈值」——
    // 这两种情况的处理完全不同（前者要调尺寸，后者要调阈值）。
    float lastBestScore() const { return bestScore_; }

private:
    void releaseLocked();                // 调用方已持锁的版本，避免 load() 自锁

    // 1.0.13.4：检测器是**整个 CoreEngine 共用一份**的（单例 → 全进程一份）。
    //
    // detect() 会把 640×640×3 的中间图写进成员缓冲 resized_ / input_，再拿它的
    // 指针去推理。两个 slot 同时进来时这不是「结果不准」而是**内存安全**问题：
    // 一方在 resized_.resize() 里重新分配，另一方还握着旧指针往里写 —— 典型的
    // use-after-free，轻则掩码全黑，重则堆破坏。
    //
    // 所以这里把整段 detect（letterbox + 张量排布 + 推理 + 后处理）串行化。
    // 代价是第二个 slot 的检测排队（640×640 一轮实测 2~3 ms，YuNet 很快）；
    // 收益是这段代码从「靠调用时序侥幸不出事」变成「怎么并发都对」。
    // 更彻底的做法是每个 slot 一套 ONNX 会话（内存换并发），留待真机双实例
    // 观感确认后再定 —— 那是资源决策，不是正确性决策。
    mutable std::mutex mtx_;
    void* model_ = nullptr;              // OnnxModel*（避免头文件互相包含）
    std::vector<float> input_;
    std::vector<unsigned char> resized_;
    int inputSize_ = 640;
    float bestScore_ = 0.f;
    bool fixedSize_ = false;   // 模型声明了固定输入尺寸
    double lastMs_ = 0.0;
};

// 旋转画布尺寸：源图 sw×sh 转 rot 度后，画布要多大才装得下整幅图。
// 检测侧（letterboxRgbRot）与 core 侧（invRotateFace）必须用同一对数算中心，
// 差 0.5 像素检测框就整体偏一格 —— 所以这里是唯一出处。
// 90 的整数倍退化为宽高互换，与 1.0.3.0 完全一致。
void rotCanvasSize(float rot, int sw, int sh, float& rw, float& rh);

}  // namespace beautycore
