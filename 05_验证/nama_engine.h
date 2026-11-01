#pragma once
// LegacyEngine —— FaceUnity LegacySDK 的离屏驱动层（OBS 滤镜调用）。
//
// 来源：从 LegacyBeauty（DaVinci OFX 版）v1.51 的 01_ofx插件源码/src/legacy_engine.{h,cpp}
// 移植。原层只依赖 Win32 + opengl32 + gdi32，不依赖 OpenFX，因此可以整层搬进
// OBS 插件。相对原版只做了四处改动，均有注释标注：
//   1) 版本号 1.51 -> 2.0.0（删除 17 项美型属破坏性变更，见文件末尾说明）；
//   2) 参数表增加 remove_nasolabial_folds_strength（去法令纹，OBS 原有实测有效项）；
//   3) 资源目录从「DLL 同目录」改为 OBS 插件的 obs-nama-beauty 数据目录；
//   4) stderr 日志改走 legacy_log 钩子（OBS blog）。
// 其余逐行一致 —— 包括所有踩过坑的注释，那些是这套集成唯一的技术档案。
//
// 关键约束（都有出处，不是猜测）：
//   * LegacySDK 需要一个 current 的 OpenGL 上下文才能工作，所以这里自建一个
//     隐藏窗口 + wgl context（与旧 obs-nama-beauty.cpp 的 legacy_gl_init 一致）。
//   * 上下文是线程独占的：调用前必须 wglMakeCurrent 到自己的上下文，
//     调用完必须还原调用线程原本的上下文，否则会把宿主的 GL 状态踩坏。
//     旧 obs-nama-beauty.cpp 的注释记录过一次真实事故（UI 线程与渲染线程互踩
//     导致画面花掉 / 卡死），这里用一个全局互斥 + __declspec(thread) 还原规避。
//   * 全部 SDK 调用串行化：SDK 本身不是可重入的，OBS 的 render 可以是多线程。
//   * 每次 SDK 调用都走 SEH 兜底（见 legacy_engine.cpp 的 seh* 系列）。SDK 是逆向
//     对接的闭源 DLL，一旦在宿主进程里抛访问违例，宿主会整体崩掉；包一层
//     __try/__except 后最坏只是这一帧透传。

#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// 构建版本号 —— 唯一出处
// ---------------------------------------------------------------------------
// LegacyVersion() 只编码 MAJOR/MINOR（对外 ABI 语义不变）；完整显示版本
// （含 PATCH 位）看 BEAUTY_BUILD_STR，日志里的 "init OK (v3.0.7 ...)" 用它。
#define BEAUTY_BUILD_MAJOR 3
#define BEAUTY_BUILD_MINOR 0
#define BEAUTY_BUILD_PATCH 14
#define BEAUTY_BUILD_STR "3.0.14"

// 面板参数顺序（滤镜属性页滑块的顺序）
enum {
    P_BLUR = 0,      // blur_level              磨皮   sdk_max 6.0
    P_CLARITY,       // clarity                 清晰   sdk_max 1.0
    P_WHITEN,        // color_level             美白   sdk_max 2.0
    P_RED,           // red_level               红润   sdk_max 1.0
    P_SHARPEN,       // sharpen                 锐化   sdk_max 1.0
                     //   底层接线保留：磨皮=0 时它确实有效，旧工程的非零值不能丢。
    P_GLOBAL_SHARP,  // 无 SDK 项                 全局锐化 —— 把与「锐化」同一条
                     //   曲线的细节回填扩展到皮肤掩码**之外**。0 = 脸外逐字节
                     //   不变（默认，保持原「只动脸」硬指标）。
    P_THREED,        // face_threed             五官立体 sdk_max 1.0
    P_EYEBRIGHT,     // eye_bright              亮眼   sdk_max 1.0
    P_POUCH,         // remove_pouch_strength   去黑眼圈 sdk_max 1.0
    P_NASOLABIAL,    // remove_nasolabial_folds_strength 去法令纹 sdk_max 1.0
    P_COUNT
};

struct BeautySettings {
    double panel[P_COUNT];   // 面板刻度 0..100
    int blur_type;           // 1=双边滤波（实测最强，推荐）0=高斯 2=弱磨皮
    int skin_detect;         // 0/1 只磨皮肤区域（默认 1：不要把背景一起磨糊）

    BeautySettings() : blur_type(1), skin_detect(1) {
        // 首次拖到来源上的默认值：只开「磨皮 20」，其余九项 0。
        // 与 OFX 版 v1.51 的默认一致（旧 OBS 默认 磨皮70/美白15/红润30 已按
        // 产品要求下调 —— 强默认值会让用户第一眼就觉得"假"）。
        const double d[P_COUNT] = {20, 0, 0, 0, 0, 0, 0, 0, 0, 0};
        for (int i = 0; i < P_COUNT; i++) panel[i] = d[i];
    }

    // 十项效果全 0 —— 此时 SDK 输出与输入一致，可以直接透传，不必进 SDK。
    bool allZero() const {
        for (int i = 0; i < P_COUNT; i++)
            if (panel[i] != 0.0) return false;
        return true;
    }
};

class LegacyEngine {
public:
    static LegacyEngine& inst();

    // 资源目录（<OBS>/obs-plugins/64bit/obs-nama-beauty）里必须含
    // CNamaSDK.dll / fuai.dll / auth_package.bin 及 assets/model/、
    // assets/graphics/ 两个子目录。成功返回 true，失败时 err 描述原因。
    // 首次调用耗时约 1.7~2.0 秒（fuSetup + 人脸模型 + 美颜道具），所以调用方
    // 应当在「模块加载 / 滤镜创建」时预热，而不是等第一次渲染。
    // 线程安全：内部加锁并复检状态。
    bool ensureReady(std::string& err);
    // 滤镜创建时专用：加锁判断「是否需要预热」，并把「本次是否真的做了初始化」
    // 通过 didInit 报回（仅用于日志）。
    bool preheat(std::string& err, bool& didInit);
    bool ready() const { return ready_; }

    // SDK 是否抛过访问违例。一旦为真，本进程内不再调用 SDK（避免反复崩）。
    bool poisoned() const { return poisoned_; }
    // 初始化失败次数；达到上限后 ensureReady 直接失败，不再重付那 2 秒。
    int failCount() const { return failCount_; }
    // 创建 GL 上下文的线程 id（诊断用）
    unsigned long ownerThread() const { return ownerThread_; }

    // 逐帧处理。src / dst 都是 RGBA8，长度 w*h*4。允许 src == dst。
    bool process(const unsigned char* src, unsigned char* dst,
                 int w, int h, const BeautySettings& s);

    // ---- 每实例一个 SDK 道具（slot）----
    //
    // 引擎内部的道具与参数缓存以前是**进程级单例**：两个滤镜（磨皮 30 / 90）交替
    // 渲染时会互相覆盖参数，而且 applied_ 缓存每帧被冲掉，每帧白付 10 次 setter。
    // 现在每个滤镜实例独占一个 slot。
    //
    // acquireSlot 成功返回 >=0 的槽位号，失败返回 -1（err 说明原因）。
    // 归还后槽位进空闲池复用，不销毁 SDK 道具（池大小 = 并发实例峰值）。
    int  acquireSlot(std::string& err);
    void releaseSlot(int slot);
    // 进程级检测选项（fuSetDefaultRotationMode / 关键点质量 / 最大人脸数）。
    // SDK 这三个 setter 是进程全局的，多个滤镜实例共用同一份状态，最后一次
    // 调用生效；内部加锁 + SEH，只能在渲染线程调用。
    void setDetectOptions(int rotate, int landmarkQuality, int maxFaces);
    // OBS 的视频渲染是严格顺序的，不需要 advanceFrame 开关（保留参数只为
    // 与 OFX 版保持同一份实现，少一处 diff 少一处坑）。
    bool process(int slot, const unsigned char* src, unsigned char* dst,
                 int w, int h, const BeautySettings& s, bool advanceFrame = true);

    int lastFaces() const { return faces_; }
    int itemId() const { return item_; }
    const char* version() const { return ver_; }
    // 上一次失败的原因（成功时为空串）。供插件层把原因报给宿主。
    const char* lastErr() const { return failReason_.c_str(); }
    // 上一次 process 内 SDK 自身的耗时（毫秒，不含调用方的像素格式转换）
    double lastSdkMs() const { return lastSdkMs_; }

    // ---- 语义区域（fuai 皮肤分割）状态，供日志读取 ----
    // 不可用（缺 fuai.dll / 明文 bundle）时全部效果退回 v1.4 的颜色启发式，
    // 不会报错也不会崩溃。
    bool   regionActive() const { return regionActive_; }
    int    regionFaces() const;
    double regionCoverage() const;
    double regionInferMs() const;
    long   regionInferCount() const;
    const char* regionErr() const;

    // 释放 SDK 与 GL 资源。仅在宿主明确卸载插件时调用。
    void release();

private:
    LegacyEngine();
    ~LegacyEngine() {}
    LegacyEngine(const LegacyEngine&) = delete;
    LegacyEngine& operator=(const LegacyEngine&) = delete;

    bool ensurePath(std::string& err);
    bool ensureGL(std::string& err);
    bool ensureSDK(std::string& err);
    // 加锁版本：调用方必须**未**持有 mutex_。didInit 可为空。
    bool ensureReadyLocked(std::string& err, bool* didInit);
    // 创建一个新的美颜道具并写入模块级默认参数。调用前 GL 上下文必须已 current。
    bool createBeautyItemGL(int* outItem);
    bool enter();     // true = 已切到本引擎的 GL 上下文；false = 切换失败
    void leave();

    bool ready_ = false;
    bool pathDone_ = false;
    bool glDone_ = false;
    bool poisoned_ = false;
    int  failCount_ = 0;
    unsigned long ownerThread_ = 0;
    std::string failReason_;
    int faces_ = 0;
    const char* ver_ = "";
    double lastSdkMs_ = 0.0;

    std::string dir_;          // 插件 DLL 所在目录（.../obs-plugins/64bit）
    std::string assetDir_;     // 数据目录（.../obs-plugins/64bit/obs-nama-beauty）
    void* hModule_ = nullptr;  // CNamaSDK.dll
    void* hGL_ = nullptr;      // 隐藏窗口
    void* hDC_ = nullptr;
    void* hRC_ = nullptr;
    int item_ = 0;             // 第一个道具（诊断用；= slots_[0].item）
    int frameId_ = 0;
    void* mutex_ = nullptr;    // CRITICAL_SECTION，避免依赖 MSVC 版本的 std::mutex 布局
    std::string work_;         // 渲染临时缓冲（输出侧，已换成 BGRA）
    std::string bgScratch_;    // 输入侧 BGRA 副本（src 是调用方的，不能原地改）
    // 美白肤色掩码（1/4 分辨率）与羽化中间结果，跨帧复用，避免每帧堆分配。
    // 仅在语义区域不可用时（退回颜色启发式）才会用到。
    std::vector<unsigned char> whitenMask_;
    std::vector<unsigned char> whitenTmp_;

    // ---- 语义区域融合用的映射表 ----
    // 把 192×256 的皮肤掩码双线性采样到 w×h：每个 x/y 只算一次下标与权重，
    // 逐像素只剩查表与乘加。表很小（w+h 项），每帧重建的代价可以忽略。
    bool regionActive_ = false;      // 已成功初始化（不代表每帧都有掩码）
    bool regionInitDone_ = false;    // 已尝试过初始化（避免每帧重试）
    std::string regionErr_;          // 初始化失败原因（regionActive_=false 时有效）
    std::vector<int> mapX0_, mapX1_, mapWX_, mapY0_, mapY1_, mapWY_;
    // CPU 侧 unsharp mask 的中间缓冲（横/纵模糊的积分值），按帧大小增长后复用。
    // 3.0.2 起多一组 7-tap 的横向和（中频带回填用）与一列滑窗累加器。
    // 两个横向和缓冲用 unsigned short：3-tap 最大 765、7-tap 最大 1785，
    // 都装得下 —— 1080p 下每帧少读写 8MB 内存，实测省 ~1.5ms。
    std::vector<unsigned short> sharpenTmp_;
    std::vector<unsigned short> sharpenTmp7_;
    std::vector<int> sharpenCol7_;
    bool ensureRegion();

    // 加载进内存的 face_beautification.bundle，acquireSlot 新建道具时复用
    std::vector<unsigned char> beautyPkg_;

    // 每实例一个 SDK 道具 + 它自己「上一次真正写进 SDK 的参数」。
    // 参数未变化时跳过重复 setter（每帧省 10 次查表），且不同实例互不干扰。
    // 3.0.1 起还带自己的细节层 EMA 历史（见 applySharpen）：也是每实例一份，
    // 两个滤镜交替渲染时互不污染。
    struct Slot {
        int item = 0;
        BeautySettings applied;
        bool hasApplied = false;
        bool inUse = false;
        // 3.0.1：细节层时序 EMA 的上一帧高频层（回填用的 hv，范围
        // [-255,255]，短整型足够）。按帧大小增长后复用。
        std::vector<short> detailPrev;
        // 3.0.2：中频带（box3-box7）的上一帧值，同样过 EMA、同样每槽位一份。
        std::vector<short> midPrev;
        bool hasDetailPrev = false;
        // 3.0.10：磨皮强度混合的「时间平滑原图」srcT（全帧 RGBA，每槽位一份）。
        // 见 bgraToRgbaBlend 的长注释 —— 3.0.8 的混合按 (1-t) 把相机噪声注回脸上，
        // 这里把混合的原图端换成 srcT，只削时间白噪、不动静态纹理。
        std::vector<unsigned char> blendPrev;
        // srcT 失效标记：t=0/t=1 走短路分支时不更新 srcT，下一帧要整帧对齐一次，
        // 否则运动后会用上很久以前的历史，表现为拖影。
        bool blendSnap = true;
        // 3.0.10：faces 门控的滞回（见 kFaceHoldFrames / kFaceGateStep）。
        // 用户实测「整脸突然暗一下再回来」就是 faces 单帧抖 0 让美白整档归零。
        int faceHold = 0;
        double faceGate = 1.0;
    };
    std::vector<Slot> slots_;
};

// ---------------------------------------------------------------------------
// 自测入口：不经 OBS，直接跑通 加载→初始化→渲染→落盘 全链路。
// 输入是裸 RGBA8（宽×高×4 字节），输出同尺寸的裸 RGBA8（便于像素比对）。
// 返回 0 表示成功。故意用 C ABI，方便用 ctypes / LoadLibrary 调用
// （blur_test 下的探针脚本用的就是它）。
// ---------------------------------------------------------------------------
#ifdef __cplusplus
extern "C" {
#endif
__declspec(dllexport) int __stdcall LegacySelfTest(const char* engineDir,
                                                 const char* rawRgbaIn,
                                                 const char* rawRgbaOut,
                                                 int width, int height,
                                                 double blur, double whiten,
                                                 char* msgBuf, int msgCap);
__declspec(dllexport) unsigned long __stdcall LegacyVersion(void);

// 测试专用（只在本副本声明）：同进程多帧序列驱动，用来验证掩码滞后。
// inDir 下需有 seq_000.raw .. seq_(count-1).raw，输出写到 outDir 同名文件。
__declspec(dllexport) int __stdcall LegacySeqTest(const char* engineDir,
                                                const char* inDir,
                                                const char* outDir,
                                                int width, int height, int count,
                                                double blur, double whiten,
                                                char* msgBuf, int msgCap);
#ifdef __cplusplus
}
#endif
