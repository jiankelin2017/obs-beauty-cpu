#pragma once
// LegacyRegion —— fuai.dll 语义区域提供者（皮肤分割）。
//
// 来源：从 LegacyBeauty（DaVinci OFX 版）v1.51 的 01_ofx插件源码/src/legacy_region.{h,cpp}
// 移植而来。原文件只依赖 Win32 + C 标准库，不依赖 OpenFX，因此可以整层搬进 OBS
// 插件而无需改动核心逻辑；本文件只补了两处 OBS 侧差异（见 findBundle 的说明）。
//
// 为什么需要它
// ------------
// v1.4 的「只磨皮肤区域」和「美白」都靠逐像素颜色判据（Cr/Cb + R>G>B）。实测
// 白色蕾丝上衣、木桌、米色墙都落在这个色域里 —— 面板美白 100 时非皮肤区有
// 40%~77.5% 的像素被提亮，白衣服直接被推到接近 255、纹理全丢。
// 详见 LegacyBeauty 仓库的 PHASE1_区域精准化探测报告.md。
//
// SDK 侧没有任何可用的区域接口：aitype 是精确枚举不是位掩码（OR 任何位都导致
// 人脸模型不加载），皮肤分割模型虽然一直在跑，但美颜道具不消费它的结果，
// 唯一的开关在 bundle 的 JS 控制器里，我们的集成路径走不到那一层。
//
// 所以这里直接驱动 fuai.dll 拿模型级皮肤分割：喂一张 RGBA，吐一张
// 192×256 的 float 概率图（整图各向异性拉伸，不是人脸局部裁剪）。
//
// 实测成本（1074×604，检出 1 张脸，detect_mode=0）
//   - 初始化（读 23MB bundle + tflite）：约 600 ms，放在引擎初始化时做
//   - 单次推理，**关掉人脸关键点**：约 2.55 ms   ← 2.1.1 起，每帧都跑
//   - 单次推理，带关键点（2.1.0 及以前）：约 11.46 ms
//   - 耗时与分辨率基本无关（模型输入尺寸固定），所以 2.1.0 只能靠每 3 帧
//     推理一次摊到 3.82 ms/帧，代价是掩码滞后 2 帧。
//   - 2.1.1 发现关键点占 8.91 ms（78%）且皮肤分割不依赖它（关掉后掩码
//     逐比特相同，0/49152 像素不同），于是每帧全跑：更便宜且零滞后。
//
// 副作用：关键点关掉后 GetNumFromResult 恒返回 0，lastFaces() 之后一直是 0。
// 该值只有 regionFaces() 一个出口且无人调用，日志里的人脸数走
// LegacyEngine::lastFaces()（来自 CNamaSDK）。
//
// 稳定性
// ------
// fuai 是逆向对接的闭源 DLL，跑在宿主进程里。所有调用都包 SEH。
// 3.0.12 起：单次访问违例（实测约 0.10%/次调用，与帧序号无关）只影响那一帧
// —— 沿用上一帧掩码，随后自动恢复；只有连续 kMaxFailStreak 次失败才把自己
// 标成 failed_、退回 v1.4 的颜色启发式。（3.0.11 及以前是一撞就永久放弃。）
//
// 分发注意（OBS 侧与 OFX 侧唯一实质差异）
// --------------------------------------
// fuai 需要**明文** bundle（Zip 头 "PK"）。OBS 安装包里带的是加密件
// （头 f35b0612），所以语义区域默认不可用，插件自动退回 v1.4 颜色启发式。
// 要启用，把 LegacyBeauty 仓库 05_解密模型数据/ai_face_processor_pc/ 下解出来的
// 明文 ai_face_processor_pc.bundle 拷到引擎目录并命名为
// ai_face_processor_pc_plain.bundle，或用 BEAUTY_REGION_BUNDLE 指定路径。

#include <string>
#include <vector>

class LegacyRegion {
public:
    static LegacyRegion& inst();

    // engineDir 里必须有 fuai.dll 与明文 bundle（见 findBundle）。
    // 失败时返回 false 并写 err；失败会被记住，不会每帧重试。
    bool ensureReady(const std::string& engineDir, std::string& err);
    bool ready() const { return ready_; }
    bool failed() const { return failed_; }
    const char* lastErr() const { return err_.c_str(); }

    // 逐帧入口：every 帧真正推理一次，其余帧复用上次掩码。
    // rgba 是 RGBA8，w*h*4 字节。返回掩码（maskW×maskH，0..255），
    // nullptr = 本次没有可用掩码（未就绪 / 失败 / 连续推理都没检出人脸）。
    const unsigned char* update(const unsigned char* rgba, int w, int h, int every);

    int maskW() const { return mw_; }
    int maskH() const { return mh_; }
    // 掩码里 >=128 的像素占全图的比例（0..1）。用来判断「这次分割是不是靠谱」。
    double coverage() const { return coverage_; }
    int lastFaces() const { return faces_; }
    double lastInferMs() const { return inferMs_; }
    long inferCount() const { return inferCount_; }
    // 2.2.1 时间平滑内部用的质心速度估计（掩码像素/帧，已 EMA）。
    // 3.0.5 起**不再**用它做平滑开关：质心对「形变」失明（脸在转、在点头、
    // 在靠近镜头时轮廓大改而质心几乎不动），只留作诊断量。
    double velEma() const { return vEma_; }
    // 3.0.5：掩码自身的帧间变化量（0..255 尺度，等于 255×翻转像素占比）。
    // 静止+噪声实测 0.06~0.11；缩放 1.15 倍的纯形变约 12。
    double rawChange() const { return rawChg_; }
    // 把 rawChg_ 归一化成 0..1 的「运动强度」：0 = 确定静止，1 = 确定在动。
    // 时间平滑与细节层 EMA 都用它当开关。
    double motion() const;

    void release();

private:
    LegacyRegion() {}
    ~LegacyRegion() {}
    LegacyRegion(const LegacyRegion&) = delete;
    LegacyRegion& operator=(const LegacyRegion&) = delete;

    bool loadDll(std::string& err);
    bool loadBundle(std::string& err);
    // 真正跑一次推理并刷新 mask_。调用前必须已 ready_。
    bool inferOnce(const unsigned char* rgba, int w, int h);
    // 3.0.12（P1）：推理失败时的统一出口（见 .cpp 长注释）。
    // 单次访问违例不再永久判死：有上一帧掩码就沿用并返回 true，
    // 连续 kMaxFailStreak 次才置 failed_。
    bool noteFail(const char* what);
    // 2.1.2：把 mask_ 软化后写进 maskSoft_（见 .cpp 里的长注释）
    void softenMask();
    // 3.0.4：原始掩码的 3 帧时域中值（多数表决），就地改写 mask_
    void medianRawMask();
    // 2.2.1：时间平滑（见 .cpp 里的长注释）
    void temporalSmooth();
    std::string findBundle() const;

    bool ready_ = false;
    bool failed_ = false;
    int failStreak_ = 0;   // 3.0.12：连续失败帧数，成功一次即清零
    std::string err_;
    std::string dir_;

    void* hDll_ = nullptr;
    void* proc_ = nullptr;     // FUAI face processor
    void* result_ = nullptr;   // FUAI result
    void* view_ = nullptr;     // FUAI image view
    std::vector<unsigned char> bundle_;

    int mw_ = 0, mh_ = 0;
    std::vector<unsigned char> mask_;      // mw_*mh_，0..255，fuai 原始输出
    // 2.1.2：软化后的掩码。fuai 的皮肤概率图实际是**硬二值**的（实测 92.65%
    // 的像素恰好是 0、6.88% 恰好是 255，中间值只占 0.47%），于是
    // applyRegionEffects 在皮肤边界上留下一条 1 掩码像素宽（1074 宽画面下约
    // 5.6 帧像素）的「原始帧 vs 美颜帧」硬台阶，applySharpen 的高频叠回会把
    // 它放大成亮/暗边线。掩码每帧跟踪人脸后这条线就跟着在皮肤上扫，看起来
    // 就是「脸颊处黑白灰快速跳」。
    // 这里用可分离 5-tap 二项式 [1,4,6,4,1]/16 把边界摊开，台阶变渐变。
    std::vector<unsigned char> maskSoft_;
    std::vector<int> maskTmp_;   // 软化用的横向累加缓冲，按 int 存避免溢出
    // 2.2.1：时间平滑状态。maskPrev_ 是上一帧实际输出的软化掩码；质心和
    // 速度估计用来判断「画面在动还是静止」，静止才强平滑（详见 .cpp 长注释）。
    std::vector<unsigned char> maskPrev_;
    // 3.0.4：原始（未软化）掩码的两帧历史 + 一帧暂存，供 medianRawMask() 做
    // 3 帧中值。三者都必须存**真实原始值** —— 存中值结果会变成中值套中值，
    // 时间上越糊越假。192x256 下三个缓冲共约 147 KB。
    // rawHist_ 是已积累的历史帧数（0/1/2），不足 2 帧时中值直接透传，
    // 避免开头两帧因为历史被首帧填满而「冻结」。
    std::vector<unsigned char> rawPrev1_, rawPrev2_, rawTmp_;
    int rawHist_ = 0;
    // 3.0.5：当前帧与上一帧**原始**掩码的平均绝对差（0..255）。这是「掩码
    // 自己在变多少」的直接度量，替代 2.2.1 的质心速度当平滑开关。
    // rawChgPrev_ 是它的上一帧值，用来区分「真运动」和「单帧尖峰」：
    //   真运动 → 两帧都在大改；单帧尖峰 → 只有这一帧大改。
    double rawChg_ = 0.0;
    double rawChgPrev_ = 0.0;
    // 3.0.5：连续「没返回掩码」的帧数。单帧丢失时沿用上一帧掩码，不要立刻
    // 关效果（见 inferOnce 里的说明）。
    int maskHold_ = 0;
    double cxPrev_ = -1.0, cyPrev_ = -1.0;   // 上一帧掩码质心（掩码像素），-1 = 无
    double vEma_ = 0.0;                      // 质心速度的平滑估计（掩码像素/帧）
    bool hasPrev_ = false;
    bool hasMask_ = false;
    long frameSeq_ = 0;
    int faces_ = 0;
    double coverage_ = 0.0;
    double inferMs_ = 0.0;
    long inferCount_ = 0;
};
