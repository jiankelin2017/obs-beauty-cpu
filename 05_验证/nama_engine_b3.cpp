// legacy_engine.cpp —— LegacyEngine 实现（OBS 版）。
//
// 从 LegacyBeauty（DaVinci OFX 版）v1.51 的 legacy_engine.cpp 移植，改动只有：
//   * 资源路径走 OBS 的 obs-nama-beauty 数据目录（见 ensurePath / ensureSDK）；
//   * stderr 输出改走 legacy_log 钩子；
//   * 参数表多一项 remove_nasolabial_folds_strength（见 keys[] / sdkMax[]）。
// 所有 SDK 函数都是 cdecl；签名来自 BeautyCore.cs 与旧 obs-nama-beauty.cpp，
// 两者对同一个 DLL 的用法一致，可以交叉印证。

#include "legacy_engine.h"
#include "beauty_log.h"
#include "legacy_region.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <string>
#include <vector>

#ifndef LOAD_WITH_ALTERED_SEARCH_PATH
#define LOAD_WITH_ALTERED_SEARCH_PATH 0x8
#endif

// ---------------------------------------------------------------------------
// LegacySDK 函数指针
// ---------------------------------------------------------------------------
typedef int (*fn_fuSetup)(void*, int, void*, void*, int);
typedef const char* (*fn_fuGetVersion)(void);
typedef int (*fn_fuIsLibraryInit)(void);
typedef int (*fn_fuGetSystemError)(void);
typedef const char* (*fn_fuGetSystemErrorString)(int);
typedef void (*fn_fuSetLogLevel)(int);
typedef int (*fn_fuLoadAIModelFromPackage)(const unsigned char*, int, int);
typedef void (*fn_fuSetFaceProcessorDetectMode)(int);
typedef void (*fn_fuFaceProcessorSetFaceLandmarkQuality)(int);
typedef void (*fn_fuSetDefaultRotationMode)(int);
typedef int (*fn_fuSetMaxFaces)(int);
typedef int (*fn_fuFaceProcessorGetNumResults)(void);
typedef int (*fn_fuCreateItemFromPackage)(const unsigned char*, int);
typedef void (*fn_fuDestroyAllItems)(void);
typedef int (*fn_fuItemSetParamd)(int, const char*, double);
typedef int (*fn_fuItemSetParams)(int, const char*, const char*);
typedef int (*fn_fuRenderItemsEx)(int, void*, int, void*, int, int, int, const int*, int);
typedef void (*fn_fuOnDeviceLost)(void);
typedef void (*fn_fuDestroyLibData)(void);

namespace {
fn_fuSetup g_fuSetup = nullptr;
fn_fuGetVersion g_fuGetVersion = nullptr;
fn_fuIsLibraryInit g_fuIsLibraryInit = nullptr;
fn_fuGetSystemError g_fuGetSystemError = nullptr;
fn_fuGetSystemErrorString g_fuGetSystemErrorString = nullptr;
fn_fuSetLogLevel g_fuSetLogLevel = nullptr;
fn_fuLoadAIModelFromPackage g_fuLoadAIModelFromPackage = nullptr;
fn_fuSetFaceProcessorDetectMode g_fuSetFaceProcessorDetectMode = nullptr;
fn_fuFaceProcessorSetFaceLandmarkQuality g_fuFaceProcessorSetFaceLandmarkQuality = nullptr;
fn_fuSetDefaultRotationMode g_fuSetDefaultRotationMode = nullptr;
fn_fuSetMaxFaces g_fuSetMaxFaces = nullptr;
fn_fuFaceProcessorGetNumResults g_fuFaceProcessorGetNumResults = nullptr;
fn_fuCreateItemFromPackage g_fuCreateItemFromPackage = nullptr;
fn_fuDestroyAllItems g_fuDestroyAllItems = nullptr;
fn_fuItemSetParamd g_fuItemSetParamd = nullptr;
fn_fuItemSetParams g_fuItemSetParams = nullptr;
fn_fuRenderItemsEx g_fuRenderItemsEx = nullptr;
fn_fuOnDeviceLost g_fuOnDeviceLost = nullptr;
fn_fuDestroyLibData g_fuDestroyLibData = nullptr;

const int FUAITYPE_FACEPROCESSOR = 0x100;

// ---------------------------------------------------------------------------
// 关于第三个参数：它是**精确枚举值，不是位掩码**（2026-10-24 实测，别再试）
//
// 曾经想用「把 FUAITYPE_FACEPROCESSOR_SKINSEGMENT 之类按位或进去」的办法，
// 让 CNamaSDK 顺便把皮肤分割模型也加载起来。实测结论是行不通：
//
//   aitype=0x100  -> 预热 859ms, faces=1, sdk=5.0ms   （正常）
//   aitype=0x101  -> 预热 313ms, faces=0, sdk=2.2ms   （人脸模型根本没加载）
//
// 1<<0 … 1<<31 逐位 + 6 组组合，**全部**表现为后者。所以 OR 进任何额外位都只是
// 让这个值变成 SDK 不认识的类型，结果是人脸检测整体失效 —— 而且画面看起来
// 仍然「有磨皮」，因为磨皮的肤色掩码是逐像素颜色判据、不依赖人脸检测，
// 所以从像素差异上几乎看不出来，极易误判成「参数无效」。
// 判据必须看日志的 faces= 与预热耗时，不能看画面。
//
// 另外，皮肤分割模型**本来就在跑**：初始化日志里有
// `fuai/face/face_processor.h:200 Perform SetUseSkinSeg`。缺的从来不是模型，
// 而是「美颜道具去消费分割结果」的开关，那个开关只存在于 bundle 的 JS 控制器里
//（face_beautification/files/script.js），我们的集成路径没走到那一层。
// 详见 LegacyBeauty 仓库 02_测试夹具beauty_probe\PHASE1_区域精准化探测报告.md 第 5.4 节。
// ---------------------------------------------------------------------------
// FU_FORMAT_RGBA_BUFFER —— 用 0 作为 in/out format 实测通过。
// ⚠️ 注意：常量值 0 本身没问题，但这个 SDK 版本按 **BGRA byte order** 解释
// format 0 的缓冲区。实测（照片 A7300538，640×394，同一帧同一次初始化）：
//     R/G/B 顺序输入 → faces=0（检不出人脸）
//     B/G/R 顺序输入 → faces=1（正常检出）
// 43 张真实照片里 39 张原先 faces=0，把通道换成 BGRA 后全部正常检出。
// 也就是说以前「检测不到人脸 → skin_detect 不生效 → 变相全局磨皮」的根因
// 有一半在这里：不是人脸小，是通道序错了，AI 模型看到的是一张颜色错乱的脸。
// 转换在 SDK 边界上做（rgbaToBgra / bgraToRgba），不进插件其它部分。
const int FU_FORMAT_RGBA_BUFFER = 0;

// ---------------------------------------------------------------------------
// 全局滤镜：默认关闭
//
// face_beautification 道具里挂着一个作用于**整帧**的色调滤镜（filter_name +
// filter_level）。早期实现照抄旧 obs-nama-beauty.cpp，把 filter_name 设成
// "ziran2"、filter_level 设成 0.4，并且「只要有任意一项效果不为 0 就把滤镜打开」。
//
// 这不是一个中性的开关，实测（640×394 纯灰 128 输入，无人脸）：
//   filter_level=0.0 → 输出 128,128,128（逐字节不变）
//   filter_level=0.1 → +4,+3,+3
//   filter_level=0.2 → +8,+7,+7
//   filter_level=0.4 → +16,+14,+14
// 灰阶 ramp 上是一条抬暗部的曲线：输入 25 → 34、128 → 144、229 → 230，
// 即**整帧（含背景、衣服、字幕）被提亮**，而不是只处理人脸。
// 用户把「磨皮」从 0 拉到 1 时，画面整体会突然亮一截 —— 这正是要修的 bug。
//
// 因此 2.0 起滤镜永久关闭：filter_name 用 "origin"（等价于无滤镜），
// filter_level 恒 0，属性页上也不再暴露这两个设置（旧预设里的值被忽略）。
// 这与 OFX 版 v1.51 的决定一致；另一个理由是语义区域融合只认皮肤掩码，
// 一个整帧滤镜会被收窄成"只染皮肤"，行为不可预期。
//
// 代价：不再有原插件那种全局色调美化。九项效果本身不受影响 —— 磨皮、清晰、
// 美白、红润在滤镜关闭时依然生效（已用棋盘格 / 灰阶图逐项验证）。
// ---------------------------------------------------------------------------
const char* const kFilterName = "origin";
const double kFilterLevel = 0.0;

// ---------------------------------------------------------------------------
// 通道序转换：宿主侧一律 RGBA，SDK 侧按 BGRA 解释（见 FU_FORMAT_RGBA_BUFFER 的说明）
//
// 只在 SDK 边界上交换 R/B：进 SDK 前 rgbaToBgra，出 SDK 后 bgraToRgba。
// 写成一个循环是为了让编译器自动向量化；每帧两遍全帧扫描，1080p 约 0.2ms。
// 刻意不做「检测到输入已是 BGRA 就跳过」的优化 —— 没有可靠的判据，
// 而一次多余的交换只是 0.2ms，猜错的代价是整帧人脸检不出。
// ---------------------------------------------------------------------------
inline void rgbaToBgra(unsigned char* p, size_t n) {
    for (size_t i = 0; i < n; i += 4) {
        unsigned char t = p[i];
        p[i] = p[i + 2];
        p[i + 2] = t;
    }
}

inline void bgraToRgba(unsigned char* p, size_t n) {
    for (size_t i = 0; i < n; i += 4) {
        unsigned char t = p[i];
        p[i] = p[i + 2];
        p[i + 2] = t;
    }
}

// ---------------------------------------------------------------------------
// 3.0.8 磨皮强度混合：out = src + (sdkOut - src) * t，顺便把 B/R 换回来。
//
// 为什么要绕这一道（2026-10-25 实测，面板磨皮=50，掩码内 1/2/3px 细节保留率）：
//
//   blur_level 0.02 → 68.3%   0.3 → 66.8%   0.6 → 66.3%   1.0 → 66.9%
//   blur_level 2.0  → 70.4%   2.4 → 71.1%   3.0 → 72.0%   3.5 → 72.9%
//   blur_level 4.5  → 75.7%   5.0 → 76.3%   6.0 → 78.1%
//   面板磨皮 0 → 100.0%（完全不磨），面板磨皮 1（SDK 仅 0.06）→ 68.1%
//
// 也就是说 blur_level 全行程只在 66%~78% 之间摆动、低端还非单调，真正起作用的
// 只是「0 = 关 / >0 = 开」这个开关；真正的强度杠杆是 blur_type（弱磨皮 94.5%
// / 高斯 84.6% / 双边 72.0%）。blur_scale、heavy_blur、nonskin_blur_scale 这几个
// 参数在这个 bundle 里都不存在（下发后保留率一位不差）。
//
// 结论：把「强度」从 SDK 手里拿回来，在 CPU 侧按 t 线性混合原图与 SDK 输出。
// t 完全由面板磨皮决定，滑块因此第一次有了真正的 0~100 连续动态范围：
//   t=0 → 100%（不磨）   t=0.5（50 档）→ 约 86%   t=1（100 档）→ 78.1%
// 旧版 50 档是 72%，新版 50 档 86%，正对着第三方「人像磨皮 50」的纹理水平。
//
// 混合在全帧上做是安全的：applyRegionEffects 会把掩码外（m=0）的像素逐字节
// 还原成输入，所以掩码外本来就等于 src，混合是恒等变换；掩码内的过渡带本来
// 就是按 m 插值的，先混后插值等价于混得更轻，不会出现台阶。
//
// 性能：与 bgraToRgba 合成一遍扫描（全帧两遍读写变一遍）。t=1 走纯交换，
// t=0 直接 memcpy，中间档实测与 3.0.7 的纯交换版同一量级（差 <0.5ms）。
//
// ---------------------------------------------------------------------------
// 3.0.10：把混合的「原图端」换成时间平滑后的原图 srcT。
//
// 用户报「开启效果后脸部屏闪」。实测（±5 噪声输入、静帧 10 帧、掩码内 29590 px，
// 口径 = 脸内逐像素帧间差的均值）：
//
//     3.0.9 磨皮 25（t=0.25）→ 2.93      3.0.7 磨皮 50（无混合）→ 1.01
//     3.0.9 磨皮 50（t=0.50）→ 2.22      输入原始噪声           → 3.64
//     3.0.9 磨皮 75（t=0.75）→ 1.68
//
// 完全落在直线上：noise(t) = (1-t)·σ_src + t·σ_sdk，σ_src=3.64、σ_sdk≈0.81
// （0.5×3.64 + 0.5×0.81 = 2.22，与实测一位不差）。也就是说这条混合按 (1-t)
// 的权重把**相机时间白噪**原封不动注回脸上，磨皮档位越低注得越多。用户当时
// 磨皮 50 且锐化/清晰都是 0 —— 细节层那条降噪 EMA（3.0.1 加的）根本没开，
// 噪声零抑制。作为量级参照：3.0.1 只注入 0.8 级噪粒就被报「屏闪严重」，
// 现在是 2.22 级。
//
// 为什么不能只对回填残差 r=t(sdk-src) 做 EMA（试过，**更差**，2.22 → 3.53）：
// src 与 -t·src 这两项的时间白噪本来是相互抵消的，把残差平滑掉等于只留下
// src 的噪声、抵消项没了。
//
// 正确做法是换掉混合的「原图端」：
//     out = (1-t)·srcT + t·sdk,   srcT = β·src + (1-β)·srcT
// 稳态下 srcT 等于无噪的底图（白噪被平均掉），静态纹理 100% 保留（EMA 的
// 稳态值就是输入本身），只有时间不相关的分量被压。展开后与上面那个式子
// 逐项等价，所以只多一次乘加、不改变 t=0/t=1 的端点行为。
// 离线仿真（β=0.25）：脸内帧间差 2.22 → 0.86，比 3.0.7 的 1.01 还低；
// β=1 时与 3.0.8 逐位相同（可用来核对实现）。
//
// β 与细节层共用 detailBetaFromVel：静止 β=0.25（噪声 ×0.38），头一动 β→1
// 完全退回 3.0.8 的行为 —— 运动时既没有拖影，也不需要降噪（运动本身就把
// 噪点掩掉了）。这与 3.0.1 细频带、3.0.2 中频带、3.0.7 逐像素 β 是同一套思路。
// ---------------------------------------------------------------------------
inline void bgraToRgbaBlend(unsigned char* out, const unsigned char* src,
                            unsigned char* srcT, size_t n,
                            int t256, int beta256) {
    if (t256 >= 256) {                        // t=1：保留 SDK 原始力度
        bgraToRgba(out, n);
        return;
    }
    if (t256 <= 0) {                          // t=0：完全不磨，直接还原输入
        memcpy(out, src, n);
        return;
    }
    const int inv = 256 - t256;
    const int ibeta = 256 - beta256;
    for (size_t i = 0; i + 3 < n; i += 4) {
        // 交换前 out 是 BGRA：out[i]=B、out[i+1]=G、out[i+2]=R。
        const int b = out[i];
        const int g = out[i + 1];
        const int r = out[i + 2];
        // srcT 原地推进一帧
        int t0 = (src[i]     * beta256 + srcT[i]     * ibeta + 128) >> 8;
        int t1 = (src[i + 1] * beta256 + srcT[i + 1] * ibeta + 128) >> 8;
        int t2 = (src[i + 2] * beta256 + srcT[i + 2] * ibeta + 128) >> 8;
        srcT[i]     = (unsigned char)t0;
        srcT[i + 1] = (unsigned char)t1;
        srcT[i + 2] = (unsigned char)t2;
        // out = src + (sdk-src)·t + (1-t)·(srcT-src) = t·sdk + (1-t)·srcT
        // 两项系数和为 256，结果天然落在 [0,255]，不需要额外 clamp。
        out[i]     = (unsigned char)(src[i]     +
                     (((r - src[i])     * t256 + (t0 - src[i])     * inv + 128) >> 8));
        out[i + 1] = (unsigned char)(src[i + 1] +
                     (((g - src[i + 1]) * t256 + (t1 - src[i + 1]) * inv + 128) >> 8));
        out[i + 2] = (unsigned char)(src[i + 2] +
                     (((b - src[i + 2]) * t256 + (t2 - src[i + 2]) * inv + 128) >> 8));
        // A 通道不参与：SDK 输出恒为 255，混不混都一样。
    }
}

// 初始化连续失败几次之后就不再重试。每次重试都要付约 2 秒（fuSetup + 模型 + 道具），
// 让它跟着每一帧反复发生会把宿主拖死。
const int kMaxInitFail = 3;

// ---------------------------------------------------------------------------
// 诊断注入口：BEAUTY_EXTRA_PARAMS / BEAUTY_EXTRA_PARAMS_FILE
//
// 形如 "use_new_whiten=1;color_level_v2=0.5"（分号分隔，值为 double）。
// 这些参数在 SDK 里存在但**没有出现在任何公开文档里**（是从 CNamaSDK.dll 的
// 字符串池里挖出来的），要判断「哪一组开关能让美白只作用于人脸」只能逐个试。
//
// 两个来源：
//   BEAUTY_EXTRA_PARAMS      环境变量，进程内只解析一次（诊断用）
//   BEAUTY_EXTRA_PARAMS_FILE 文件，**每次下发前重新读**。测量脚本可以在同一个
//                          进程里换文件内容来扫参数组合，不用反复重启
//                          滤镜/重建 SDK 实例（初始化要 2 秒一扫太慢）。
//
// 语义：
//   * 创建美颜道具时下发一次；
//   * 每次面板参数变化时再下发一次（保证与其它参数同批生效）；
//   * 走文件来源时**每帧都下发**，这样只改文件不改面板参数也能生效。
// 不设置这两个环境变量时行为与以前**完全一致**（不解析、不下发、零开销）。
// ---------------------------------------------------------------------------
struct ExtraParam {
    std::string key;
    double value;
};

// 解析 "k=v;k2=v2"。空白会被去掉；无法解析的片段直接跳过。
static void parseExtraParamText(const std::string& s, std::vector<ExtraParam>& out) {
    size_t pos = 0;
    while (pos < s.size()) {
        size_t sc = s.find(';', pos);
        if (sc == std::string::npos) sc = s.size();
        std::string one = s.substr(pos, sc - pos);
        pos = sc + 1;
        size_t eq = one.find('=');
        if (eq == std::string::npos) continue;
        std::string k = one.substr(0, eq);
        std::string v = one.substr(eq + 1);
        size_t b = k.find_first_not_of(" \\t");
        size_t e = k.find_last_not_of(" \\t");
        if (b == std::string::npos) continue;
        k = k.substr(b, e - b + 1);
        b = v.find_first_not_of(" \\t");
        e = v.find_last_not_of(" \\t");
        if (b == std::string::npos) continue;
        v = v.substr(b, e - b + 1);
        ExtraParam p;
        p.key = k;
        p.value = atof(v.c_str());
        out.push_back(p);
    }
}

static const char* extraParamsFile() {
    static int cached = -1;
    static std::string path;
    if (cached < 0) {
        cached = 0;
        const char* p = getenv("BEAUTY_EXTRA_PARAMS_FILE");
        if (p && *p) {
            path = p;
            cached = 1;
        }
    }
    return cached ? path.c_str() : nullptr;
}

static const std::vector<ExtraParam>& extraParams() {
    static std::vector<ExtraParam> cached;
    static bool inited = false;
    const char* file = extraParamsFile();
    if (file) {
        std::vector<ExtraParam> now;
        FILE* f = nullptr;
        errno_t e = fopen_s(&f, file, "rb");
        if (e == 0 && f) {
            char buf[4096];
            size_t n = fread(buf, 1, sizeof(buf) - 1, f);
            fclose(f);
            buf[n] = 0;
            parseExtraParamText(std::string(buf), now);
        }
        cached.swap(now);
        return cached;
    }
    if (!inited) {
        inited = true;
        const char* env = getenv("BEAUTY_EXTRA_PARAMS");
        if (env && *env) {
            parseExtraParamText(std::string(env), cached);
        }
    }
    return cached;
}

// 逐帧是否还要切换 GL 上下文。
// fuRenderItemsEx 走的是 FU_FORMAT_RGBA_BUFFER —— 输入输出都是 CPU 内存指针，
// 原理上渲染阶段不需要 GL 上下文（上下文只在 fuSetup / 模型加载时需要）。
// 但 SDK 内部有可能顺手创建 GL 纹理，所以默认保持「每帧切换」的保守做法。
//
// 设 BEAUTY_ENGINE_NO_GLLOCK=1 可跳过逐帧切换。这个开关存在的意义是把
// 「每帧两次 wglMakeCurrent 到底值不值」变成可测的：OBS 自己的渲染线程上
// 通常已经有它自己的 GL 上下文，我们切走再切回会带来两次隐式 flush。
static bool skipGlLock() {
    static int cached = -1;
    if (cached < 0) {
        const char* v = getenv("BEAUTY_ENGINE_NO_GLLOCK");
        cached = (v && v[0] == '1' && v[1] == 0) ? 1 : 0;
    }
    return cached == 1;
}

// 线程局部：保存调用线程原本的 GL 上下文，用完必须还原
__declspec(thread) HDC t_savedDC = nullptr;
__declspec(thread) HGLRC t_savedRC = nullptr;
__declspec(thread) bool t_enterOk = false;

// ---------------------------------------------------------------------------
// SEH 兜底
//
// LegacySDK 是逆向对接的闭源 DLL。它一旦在宿主进程里抛访问违例（0xC0000005），
// 整个 OBS 都会跟着死。所以每个 SDK 入口都包一层 __try/__except，
// 代价是这一帧透传，而不是宿主崩掉。
//
// 注意：下面这些函数体内**不能出现需要析构的 C++ 对象**，否则 MSVC 报 C2712。
// 所以它们只收裸指针和标量，参数名也刻意用 a/b/c 这种不依赖外部的形式。
// ---------------------------------------------------------------------------
volatile LONG g_sehHit = 0;   // 最近一次调用是否被 SEH 兜住

int sehSetup(int* outRet, void* auth, int authLen) {
    __try {
        *outRet = g_fuSetup(nullptr, 0, nullptr, auth, authLen);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehCreateItem(int* outItem, void* pkg, int len) {
    __try {
        *outItem = g_fuCreateItemFromPackage((const unsigned char*)pkg, len);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehSetParamd(int item, const char* key, double v) {
    __try {
        g_fuItemSetParamd(item, key, v);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehSetParams(int item, const char* key, const char* val) {
    __try {
        g_fuItemSetParams(item, key, val);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

// 把诊断参数下发到 SDK 道具。
static void applyExtraParams(int item, bool force) {
    const std::vector<ExtraParam>& v = extraParams();
    if (!force && v.empty()) return;
    for (size_t i = 0; i < v.size(); i++) {
        const char* k = v[i].key.c_str();
        double val = v[i].value;
        sehSetParamd(item, k, val);
        NALOG(BEAUTY_LOG_INFO, "[nama] 诊断参数 %s = %g", k, val);
    }
}

int sehRender(int* outRet, int fmtOut, void* pOut, int fmtIn, void* pIn,
              int w, int h, int frameId, int* items, int n) {
    __try {
        *outRet = g_fuRenderItemsEx(fmtOut, pOut, fmtIn, pIn, w, h, frameId, items, n);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehLoadFaceModel(int* outRet, const unsigned char* pkg, int len) {
    __try {
        // 第三个参数是精确枚举，只能传 FUAITYPE_FACEPROCESSOR，不能按位或。
        *outRet = g_fuLoadAIModelFromPackage(pkg, len, FUAITYPE_FACEPROCESSOR);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehFaceSetup(void) {
    __try {
        g_fuSetFaceProcessorDetectMode(0);
        g_fuFaceProcessorSetFaceLandmarkQuality(1);
        g_fuSetMaxFaces(4);
        g_fuSetDefaultRotationMode(0);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehGetNumFaces(int* outN) {
    __try {
        *outN = g_fuFaceProcessorGetNumResults();
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

// 进程级检测选项一次性下发。SDK 这三个 setter 都是进程全局的。
int sehDetectOptions(int rotate, int landmarkQ, int maxFaces) {
    __try {
        g_fuSetDefaultRotationMode(rotate);
        g_fuFaceProcessorSetFaceLandmarkQuality(landmarkQ);
        g_fuSetMaxFaces(maxFaces);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehDestroy(void) {
    __try {
        g_fuDestroyAllItems();
        g_fuOnDeviceLost();
        g_fuDestroyLibData();
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

// ---------------------------------------------------------------------------
// 美白：按肤色掩码在 CPU 侧提亮（只动皮肤/人脸，不动背景）
//
// 为什么不用 SDK 自带的美白通道（color_level / color_level_v2）：
// 实测 5 张真实照片（640×394，A/B 各热身 3 帧、逐像素差分），两条通道都是
// **整帧**作用，没有任何参数能把它限到人脸——
//   color_level：横幅照片 99% 像素被改，人脸∩内容 11.25 vs 非人脸∩内容 11.17
//                （几乎无差别），连没人脸的照片也 96% 被改；
//   color_level_v2 + use_new_whiten：只在竖幅照片上看着像"限定人脸列"，
//                其实那是 letterbox 黑边的假象——内容区照样 99% 被改；
//   use_new_whiten/whiten_v2/beauty_mask_v/skin_detect/lower_quality/
//   manual_scale：全部无效或本身惰性。V≥0.65 还会退化成连黑边都改的全局。
//
// 为什么不用 fuFaceProcessorGetResultHeadMask（官方 CNamaSDK.h 有这个导出）：
//   插件曾按它实现「只提亮头部掩码」，但实测本 SDK 版本在 fuRenderItemsEx
//   之后对 index=0 调用**恒返回 nullptr**（mw=mh=0），即使同一帧 faces=1。
//   可能还需要未文档化的前置开关，风险太大，所以退回 CPU 肤色掩码。
//
// 于是改走插件自己这条线：渲染前把 SDK 美白恒关（见 process 里的
// sehSetParamd(item,"color_level",0)），渲染完成后按肤色掩码提亮：
//   * 有脸 → 只动皮肤（掩码羽化过，边界不硬）；
//   * 无脸 → 直接跳过（顺带修掉无人脸照片的整幅提亮）。
//
// 性能是硬约束：全分辨率掩码（逐像素判定 + 3×3 膨胀 + 5×5 羽化）在 1080p
// 实测 **38 ms/帧**，把 70fps 直接拖到 16fps。因此：
//   * 掩码在 1/4 分辨率上算（每 4×4 块取一个样本），3×3 均值羽化，
//     应用时双线性放大回全分辨率；
//   * 掩码缓冲由引擎复用，稳定后零堆分配；
//   * 提亮量按掩码值预生成 256 项整数表，逐像素只有乘加，无浮点。
// 精度取舍：4px 的掩码粒度对「整张脸 / 整片皮肤」足够，羽化后没有硬边。
// 已知局限：掩码是肤色启发式，画面里大面积的肤色物体（木桌、米色墙）
// 也会被轻微提亮；没有可靠的人脸框之前这是可接受的折中。
//
// 公式 c += (255-c) · k · m · (c/255)：按亮度加权——皮肤提得动，
// 头发/纯黑背景几乎不动（c=0 时恒为 0），m 是双线性采样的肤色掩码。
// ---------------------------------------------------------------------------
static const int kWhitenMaskDown = 4;   // 掩码降采样倍率（1080p → 约 13 万点）
static void applyWhiten(unsigned char* rgba, int w, int h,
                        double strength, int nFaces,
                        std::vector<unsigned char>& mask,
                        std::vector<unsigned char>& tmp) {
    if (strength <= 0.0 || nFaces <= 0)
        return;   // 没人脸就不动：既不全局提亮，也不误伤无人脸画面
    const double kMax = 0.19;   // 3.0.9 跟随语义掩码路径再降（0.34 → 0.19）
    double k = strength / 100.0 * kMax;
    if (k <= 0.0) return;

    const int mw = (w + kWhitenMaskDown - 1) / kWhitenMaskDown;
    const int mh = (h + kWhitenMaskDown - 1) / kWhitenMaskDown;
    const size_t mn = (size_t)mw * (size_t)mh;
    if (mask.size() < mn) mask.resize(mn);
    if (tmp.size() < mn) tmp.resize(mn);

    // ---- 第一 pass：低分辨率肤色掩码（每 4×4 块取一个样本）------------
    int hits = 0;
    for (int y = 0; y < mh; y++) {
        const unsigned char* row = rgba + (size_t)(y * kWhitenMaskDown) * (size_t)w * 4;
        unsigned char* m = &mask[(size_t)y * (size_t)mw];
        for (int x = 0; x < mw; x++) {
            const unsigned char* p = row + (size_t)(x * kWhitenMaskDown) * 4;
            int R = p[0], G = p[1], B = p[2];
            int Y = (66 * R + 129 * G + 25 * B + 128) >> 8;
            int Cb = ((-38 * R - 74 * G + 112 * B + 128) >> 8) + 128;
            int Cr = ((112 * R - 94 * G - 18 * B + 128) >> 8) + 128;
            bool skin = (Cr >= 133 && Cr <= 173 && Cb >= 77 && Cb <= 127 &&
                         R > G && G > B && R > 80 && Y > 60 && Y < 235);
            m[x] = skin ? 255 : 0;
            if (skin) hits++;
        }
    }
    if (hits == 0) return;   // 没有肤色像素：整帧一个字节都不动

    // ---- 第二 pass：3×3 均值羽化（可分离，边界复制）-------------------
    for (int y = 0; y < mh; y++) {          // 水平
        const unsigned char* s = &mask[(size_t)y * (size_t)mw];
        unsigned char* t = &tmp[(size_t)y * (size_t)mw];
        for (int x = 0; x < mw; x++) {
            int x0 = x > 0 ? x - 1 : 0;
            int x1 = x + 1 < mw ? x + 1 : mw - 1;
            t[x] = (unsigned char)((s[x0] + s[x] + s[x1]) / 3);
        }
    }
    for (int y = 0; y < mh; y++) {          // 垂直（结果写回 mask）
        int y0 = y > 0 ? y - 1 : 0;
        int y1 = y + 1 < mh ? y + 1 : mh - 1;
        const unsigned char* a = &tmp[(size_t)y0 * (size_t)mw];
        const unsigned char* b = &tmp[(size_t)y * (size_t)mw];
        const unsigned char* c = &tmp[(size_t)y1 * (size_t)mw];
        unsigned char* m = &mask[(size_t)y * (size_t)mw];
        for (int x = 0; x < mw; x++)
            m[x] = (unsigned char)((a[x] + b[x] + c[x]) / 3);
    }

    // ---- 第三 pass：把 k 与掩码值合成整数表 ---------------------------
    int tLut[256];
    for (int i = 0; i < 256; i++)
        tLut[i] = (int)(k * (double)i * 16777216.0 / 65025.0);

    const char* dbgEnv = getenv("BEAUTY_MASK_DEBUG");
    const bool dbg = (dbgEnv && dbgEnv[0] == '1');
    size_t cov = 0;

    // ---- 第四 pass：双线性放大掩码 + 提亮 -----------------------------
    for (int y = 0; y < h; y++) {
        const int qy = y >> 2, ry = y & 3;
        const unsigned char* r0 = &mask[(size_t)qy * (size_t)mw];
        const unsigned char* r1 = &mask[(size_t)(qy + 1 < mh ? qy + 1 : qy) * (size_t)mw];
        unsigned char* px = rgba + (size_t)y * (size_t)w * 4;
        for (int x = 0; x < w; x++, px += 4) {
            const int qx = x >> 2, rx = x & 3;
            const int x1 = qx + 1 < mw ? qx + 1 : qx;
            const int top = r0[qx] * (4 - rx) + r0[x1] * rx;
            const int bot = r1[qx] * (4 - rx) + r1[x1] * rx;
            const int mv = (top * (4 - ry) + bot * ry) >> 4;
            const int t = tLut[mv];
            if (t == 0) continue;
            if (mv > 127) cov++;
            for (int c = 0; c < 3; c++) {
                int v = px[c];
                px[c] = (unsigned char)(v + ((v * (255 - v) * t) >> 24));
            }
        }
    }

    if (dbg)
        NALOG(BEAUTY_LOG_INFO, "[nama] 美白掩码 低分辨率=%dx%d 覆盖=%.1f%% k=%.3f",
              mw, mh, 100.0 * (double)cov / (double)((size_t)w * (size_t)h), k);
}

// 语义掩码的推理频率。2.1.1 起每帧都跑。
//
// 【2.1.0 及以前为什么是 3】当时开着人脸关键点，fuai 单次推理 11.46 ms
// （1074×604，detect_mode=0），而且与分辨率基本无关（模型输入尺寸固定），
// 只能靠降频摊薄：N=3 → 3.82 ms/帧。代价是掩码滞后 2 帧，30 fps 下约 66 ms，
// 人脸左右移动时美白/磨皮的边界明显跟不上。
//
// 【2.1.1 起为什么能改成 1】成本拆解发现关键点一个人占了 8.91 ms（78%），
// 而皮肤分割模型和关键点模型是并联支路 —— 关掉 SetUseFaceLandmark 后
// GetSkinSegResult 照样出图，且逐比特相同（0/49152 像素不同），单次降到
// 2.55 ms。于是每帧全跑：2.55 ms/帧，比旧的 3.82 ms/帧还便宜，且零滞后。
//
// 位移跟随实测：图像左右各移 60 px，掩码质心 +60.3 / −60.9 px。
// 无人脸时不会误判（裁掉人脸覆盖度 0.00073，纯棕色场 0.00000）。
const int kRegionEvery = 1;

// ---------------------------------------------------------------------------
// 语义区域融合（v1.5）：一趟遍历同时做两件事
//
//   1) 按皮肤掩码把 SDK 的效果收回去 —— m=0 的像素逐字节还原成输入，
//      于是「背景、衣服、木桌」完全不动（这是 v1.4 做不到的：SDK 双边档下
//      非肤色区仍有 93% 像素被改）。
//   2) 按同一掩码做美白提亮 —— 掩码来自 fuai 的语义分割，不再是 Cr/Cb 颜色判据，
//      所以白衣服、米色墙不会被提亮。
//
// 掩码是 fuai 的 192×256 皮肤概率图（整图各向异性拉伸，不是人脸局部裁剪），
// 双线性采样到全分辨率。每个 x/y 的下标与权重预先算好，逐像素只剩查表与乘加。
//
// ⚠️ OBS 2.0 的前提：本插件已删除全部 17 项美型（几何形变）。若将来要把
// 美型加回来，**不能**直接套这个函数 —— 形变是像素位移，用掩码把掩码外
// 区域贴回原图会在形变边界切出重影。详见升级方案文档。
// ---------------------------------------------------------------------------
static void buildMaskMap(int w, int h, int mw, int mh,
                         std::vector<int>& x0, std::vector<int>& x1,
                         std::vector<int>& wx, std::vector<int>& y0,
                         std::vector<int>& y1, std::vector<int>& wy) {
    x0.resize((size_t)w); x1.resize((size_t)w); wx.resize((size_t)w);
    y0.resize((size_t)h); y1.resize((size_t)h); wy.resize((size_t)h);
    for (int x = 0; x < w; x++) {
        int i0 = 0, f = 0;
        if (mw > 1 && w > 1) {
            const long long q = ((long long)x * (mw - 1) * 65536) / (w - 1);
            i0 = (int)(q >> 16);
            f = (int)(((q & 0xFFFF) * 256) / 65536);
            if (i0 >= mw - 1) { i0 = mw - 1; f = 0; }
        }
        x0[x] = i0;
        x1[x] = (i0 + 1 < mw) ? i0 + 1 : i0;
        wx[x] = f;
    }
    for (int y = 0; y < h; y++) {
        int i0 = 0, f = 0;
        if (mh > 1 && h > 1) {
            const long long q = ((long long)y * (mh - 1) * 65536) / (h - 1);
            i0 = (int)(q >> 16);
            f = (int)(((q & 0xFFFF) * 256) / 65536);
            if (i0 >= mh - 1) { i0 = mh - 1; f = 0; }
        }
        y0[y] = i0;
        y1[y] = (i0 + 1 < mh) ? i0 + 1 : i0;
        wy[y] = f;
    }
}

static void applyRegionEffects(unsigned char* out, const unsigned char* src,
                               int w, int h, double whitenStrength,
                               double redStrength,
                               bool limitToSkin,
                               const unsigned char* mask, int mw, int mh,
                               std::vector<int>& x0, std::vector<int>& x1,
                               std::vector<int>& wx, std::vector<int>& y0,
                               std::vector<int>& y1, std::vector<int>& wy) {
    if (!mask || mw <= 0 || mh <= 0) return;
    if (!limitToSkin && whitenStrength <= 0.0 && redStrength <= 0.0) return;

    // 与颜色启发式那条路同一个标定。
    //
    // 2.0.2 是 kMax=0.40，实测面板 100 只把皮肤亮度抬 +5.76，面板 55 只有
    // +3.28 —— 而 OBS 美颜摄像头 2.4.2 在美白 55 上就有 +5.66。同等观感下
    // 我们的美白要开满才追平对方的 55，强度差了约一倍。
    //
    // 2.1.0 提到 0.70：面板 55 ≈ +5.7（追平），面板 100 ≈ +10。
    // 提亮走 v*(255-v) 的钟形曲线，中点附近斜率最大、两端自然收敛，
    // 所以拉高 k 不会把高光直接削平。
    // 3.0.8：同档位提亮下调约 17%（0.70 → 0.58）。
    // 3.0.9：再降 45%（0.58 → 0.32）。依据是在 fuai 皮肤掩码内实测：
    //   0.58 时美白 50 档把脸抬 **+15.04 级**、100 档约 **+30 级**
    //   （100 档把 Y≈146 推到 176，已经贴住高光饱和区）。
    //   0.32 后 50 档约 +8.3、100 档约 +16.6，才是「美白 50」该有的量级。
    // 注意：历史上用 measure_all_effects.py 测到的 +8.19 / +6.75 是被稀释过的
    // 数字 —— 它用肤色启发式，集合里混进了掩码外根本没被改的像素。真实观感
    // 要看掩码内的均值，两者差约 2.2 倍。
    const double kMax = 0.32;
    const double k = whitenStrength <= 0.0 ? 0.0 : whitenStrength / 100.0 * kMax;
    int tLut[256];
    for (int i = 0; i < 256; i++)
        tLut[i] = (int)(k * (double)i * 16777216.0 / 65025.0);

    // ---- 红润（2.2.0 新增，CPU 侧）----------------------------------------
    //
    // 为什么必须自己做：SDK 的 red_level **根本不加红**。实测（固定皮肤像素集）：
    //   1074x604  red_level=0.75 -> 覆盖 0.35%，dRed -0.11（R+0.10/G-1.27/B+0.21，
    //                              纯粹是压绿 + 压暗），怼到 2.0 覆盖 40% 但
    //                              dRed 仍是 -0.21
    //   640x394   red_level=0.75 -> 覆盖 0.04%，dRed +0.52；1.0 -> 覆盖 0.88%
    // 也就是说这一档在 SDK 里是死的，而第三方（OBS 美颜摄像头 2.4.2）的红润 30
    // 肉眼可见。我们不是"偏弱"，是**零**。所以从 2.2.0 起 red_level 不再下发给
    // SDK（它只会带来 -0.4~-0.9 的压暗），全部改在这里按掩码做。
    //
    // 做法与美白同构：钟形曲线 + 同一张掩码。区别是**抬 R 同时压 B** ——
    // 只抬 R 会把肤色推向橘黄，压一点 B 才是"血气/红润"。
    // 标定（只在**掩码满覆盖**的真实皮肤像素上测，YCbCr 肤色集会把均值稀释
    // 0.36 倍，2026-10-25 踩过）：面板 55 ≈ dRed +4，面板 100 ≈ dRed +9，
    // 对应第三方红润 30 档的观感区间。
    const double kRedMaxR = 0.13;    // R 抬升系数（面板 100）
    const double kRedMaxB = 0.068;   // B 压低系数（面板 100）
    const double kr = redStrength <= 0.0 ? 0.0 : redStrength / 100.0 * kRedMaxR;
    const double kb = redStrength <= 0.0 ? 0.0 : redStrength / 100.0 * kRedMaxB;
    int tRLut[256], tBLut[256];
    for (int i = 0; i < 256; i++) {
        tRLut[i] = (int)(kr * (double)i * 16777216.0 / 65025.0);
        tBLut[i] = (int)(kb * (double)i * 16777216.0 / 65025.0);
    }

    buildMaskMap(w, h, mw, mh, x0, x1, wx, y0, y1, wy);

    for (int y = 0; y < h; y++) {
        unsigned char* row = out + (size_t)y * w * 4;
        const unsigned char* srow = src + (size_t)y * w * 4;
        const unsigned char* m0 = mask + (size_t)y0[y] * mw;
        const unsigned char* m1 = mask + (size_t)y1[y] * mw;
        const int fy = wy[y];
        for (int x = 0; x < w; x++, row += 4, srow += 4) {
            const int fx = wx[x];
            const int a0 = m0[x0[x]], a1 = m0[x1[x]];
            const int b0 = m1[x0[x]], b1 = m1[x1[x]];
            const int top = a0 * (256 - fx) + a1 * fx;
            const int bot = b0 * (256 - fx) + b1 * fx;
            const int mv = (top * (256 - fy) + bot * fy) >> 16;   // 0..255

            if (limitToSkin) {
                // m256：0→0、255→256。保证满掩码时逐字节等于 SDK 输出，
                // 也保证零掩码时逐字节等于输入（背景不动）。
                const int m256 = mv + (mv >> 7);
                if (m256 == 0) {
                    row[0] = srow[0]; row[1] = srow[1]; row[2] = srow[2];
                } else {
                    for (int c = 0; c < 3; c++) {
                        const int d = (int)row[c] - (int)srow[c];
                        row[c] = (unsigned char)((int)srow[c] + ((d * m256) >> 8));
                    }
                }
            }
            if (k > 0.0) {
                const int t = tLut[mv];
                if (t != 0) {
                    for (int c = 0; c < 3; c++) {
                        const int v = row[c];
                        row[c] = (unsigned char)(v + ((v * (255 - v) * t) >> 24));
                    }
                }
            }
            if (kr > 0.0) {
                const int tr = tRLut[mv];
                if (tr != 0) {
                    const int v = row[0];
                    int r = v + ((v * (255 - v) * tr) >> 24);
                    if (r > 255) r = 255;      // 钟形本身收敛，这里只是兜底
                    row[0] = (unsigned char)r;
                }
            }
            if (kb > 0.0) {
                const int tb = tBLut[mv];
                if (tb != 0) {
                    const int v = row[2];
                    int b2 = v - ((v * (255 - v) * tb) >> 24);
                    if (b2 < 0) b2 = 0;
                    row[2] = (unsigned char)b2;
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// 细节回填（3.0.0 重写；2.1.0~2.2.1 时叫 applySharpen，做的是「对磨完的图
// 做 3x3 unsharp」）。
//
// 【旧实现为什么不够】SDK 的双边过滤先把高频抹掉了，unsharp 再对磨完的图做
// 高通放大已经没有输入可放大 —— 实测磨皮 75 时锐化从 0 推到 100 只能把细节
// 能量拉回 +0.46，观感上就是「糊」。第三方（OBS 美颜摄像头 2.4.2）同参数下
// 细节能量是我们的 3 倍（连背景区都差 2~4 倍），它的锐化显然作用在磨皮之前
// 或做了频率分离。
//
// 【新实现：频率分离】高频层从**原图**取，不从磨完的图取：
//     h = src - box3x3(src)       原图里的细纹理（毛孔/眉眼/发丝）
//     out += alpha * h            alpha = 锐化滑块 0..1
// 于是两个滑块彻底解耦：磨皮决定「大尺度抹掉多少」（瑕疵/色斑/块状不均匀），
// 锐化决定「最细一段纹理放回多少」。磨皮 75 + 锐化 50 = 皮肤仍然光滑，但
// 毛孔和边缘细节回来 —— 立体感就是这么来的。alpha=1 时 3x3 频带全额回填。
//
// 为什么用 3x3 而不是更宽的核：只回填最细的频带，相机噪点和大块结构不会被
// 一起放大。核宽是调参旋钮（要更「通透」就加宽），不是现在要动的。
//
// 仍然只作用于皮肤掩码内（mv 加权），掩码外一个字节都不碰 —— 与
// applyRegionEffects 的承诺一致（背景/衣服/字幕不许动）。第三方是全局锐化，
// 但我们把「背景零改动」当作不可撕毁的保证，用掩码内回填换细节。
// 代价与旧版相同：两趟横向 + 一趟纵向下采样，1080p 约 2~3 ms。
//
// 【3.0.1 补丁：噪点不回填】频率分离把「立体感」找回来了，但也把原图里的
// **相机噪点**一起叠回磨完的脸：噪点帧间独立，脸就呈"沸腾"式闪动
// （2026-10-25 用户实测报告「脸部屏闪严重」；±5 噪声探针测得回填给整帧
// 帧间差异带来 +6.6% 的细粒度高频分量，折算到脸部约 0.8 级/像素的新鲜
// 噪粒）。噪点与细纹理在**幅值**上重叠（±2~6 级 vs 2~8 级），软阈值分不
// 开；但**时间特性**正交：噪点是白噪、静脸纹理帧间相关。所以高频层过一层
// 速度自适应的时序 EMA（见下面 kDetailBetaStill 一组常量与
// detailBetaFromVel）：静帧白噪幅值 x0.33、纹理无损，头一动 beta 升到 1
// 完全不平滑。掩码外也更新 EMA 历史，避免掩码边缘对陈旧值。
//
// 【3.0.2 补丁：中频带回填】3.0.1 之后用户仍反馈「同参数下脸比对方平」。
// 2026-10-25 做了一次同渲染器对比（两路塞进同一个 OBS 预览，排除预览锐度
// 差异）：图1 = 第三方先、我方后（两路都过我们一次），图2 = 仅我方。既然
// 输出差异只反映输入差异，就直接读出了对方链路的**频带增益**：
//     r1（1~2px）  对方是原始画面的 2.4 倍
//     r2/r3（3~7px）对方是原始画面的 1.6~1.7 倍
// 也就是说对方在细/中频上是**放大**，而我们这条链只有衰减、没有增益 ——
// 3x3 回填最多把细频带还原到 1.0 倍（alpha 上限 1），5~15px 那一段根本
// 碰不到，被双边滤波抹掉就永久丢失。这才是「平」的结构性原因。
//
// 所以这里补一层带通，把中频段也做成可增益：
//     h_mid = box3(src) - box7(src)        r≈1.5 ~ 3.5px 那一段
//     out  += gamma * h_mid                gamma = 锐化/100 * kMidGain
// 锐化 50 时 gamma = 0.65，配合已有的 1.0 倍保留，正好把该频带推到原图的
// 1.65 倍 —— 与实测目标对齐。细频带**故意**不加增益：那一档里噪点和纹理
// 幅值重叠，放大 1.4 倍就是 3.0.0 那次「脸部屏闪」重演；中频带回的是结构，
// 不是噪粒。
//
// 中频带用 1/64 级定点计算，不是整级。原因见下面 kMidGain 附近：整级截断
// 带来的 ±0.5 级量化抖动被增益放大后，会在平坦区变成可见噪点；先提高精度，
// 就不需要额外加门限（时间方向的噪点本来就由 EMA 管）。
//
// 「清晰」滑块从 SDK 的 clarity 改接到这里。它原来是全行程只有 +0.23 细节、
// 却会把**整帧**提亮 +2.84（连背景一起），既没用又违反「背景零改动」的承诺。
// 现在它是中频增益的额外旋钮，且只作用在掩码内。
// ---------------------------------------------------------------------------

// ---- 3.0.1：细节层时序 EMA 参数 --------------------------------------------
// 对回填的高频层做跨帧指数平滑：
//     h_t = beta * h_new + (1 - beta) * h_prev
// 白噪稳态幅值 x sqrt(beta/(2-beta))，beta=0.2 -> x0.33（抑噪 67%）；
// 静态纹理是相关信号，EMA 稳态增益为 1（无损）。
//
// 运动判据：3.0.5 起改用 LegacyRegion::motion()（0..1，来自掩码自身的帧间
// 变化量 rawChg，见 legacy_region.cpp 里 kChgLo 的注释）。
// 为什么换掉质心速度：质心对**形变**失明 —— 脸在转、在点头、在靠近镜头时
// 轮廓大改而质心几乎不动，判据一直认为「静止」，细节层就带着 5 帧的时序
// 常数拖影（掩码跟上了、细节层还在拖，观感上是「脸上的纹理在滑」）。
// 换成 rawChg 后，静止+噪声实测 0.059~0.107 → motion 0（beta 保持 stillBeta，
// 抑噪能力与 3.0.3/3.0.4 完全一致）；形变 ×1.15 时 rawChg ≈ 12 → motion 1
// （beta 立刻到 1，零拖影）。阈值 0.15 / 0.40 是归一化后的 motion 单位，
// 对应 rawChg 0.79 / 1.44 —— 约静止噪声上限的 7~13 倍，判据干净。
static const double kDetailBetaStill = 0.20;   // 静止时的平滑强度
static const double kDetailVelStill  = 0.15;   // motion 低于此值按静止处理
static const double kDetailVelFull   = 0.40;   // motion 高于此值完全不平滑

// 3.0.2：中频带单独用更强的平滑。为什么不是同一个 beta —— 实测 ±5 噪声下
// 中频回填把整帧帧间粗糙度从 1.350 抬到 1.750（+30%），而 3.0.0 那次被用户
// 报「脸部屏闪严重」的版本在这个指标上只有 +6.6%。原因是中频带的**增益**
// 大（锐化50 时 1.4 倍）：带通噪声本身只有 0.30σ，但乘 1.4 后又回到 0.42σ，
// 与 3.0.0 细频带（0.5×0.94σ）同量级。中频带回的是弥散的肤色起伏，允许更
// 长的时序常数而不显拖影，所以这里把静止 beta 压到 0.08（噪声 ×0.20，比细
// 频带再低 40%）；速度判据共用，头一动仍然立刻放到 1。
static const double kMidBetaStill = 0.08;

// 3.0.10：磨皮强度混合那条 srcT 的静止 β。
// 选 0.25 的依据是「降到 3.0.7 以下但不换观感」：离线仿真（±5 噪声、磨皮 50）
// 脸内帧间差 2.22 → 0.86，3.0.7 是 1.01；再往下压（0.15）只多降 0.1，但稳态
// 收敛要 6 帧以上，头停下来的那几帧会更明显地「由糊转清」。
static const double kBlendBetaStill = 0.25;

// 3.0.10：faces 门控的滞回。用户实测「整脸突然暗一下再回来」= faces 抖一帧、
// 美白整档归零。实测美白 50 对脸内亮度贡献 +8.31 级（161.21 vs 152.90），
// 单帧阶跃就有 8 级，比噪声型屏闪（2.2 级）显眼 4 倍。
// 做法：faces>0 立刻置 1；faces==0 先保持 kFaceHoldFrames 帧（≈133ms@30fps），
// 之后按 kFaceGateStep 缓降（8 帧走完，≈267ms）。真人离开画面时本来也会被
// 掩码兜住（cov→0 → 整帧还原），所以这里慢一点没有副作用。
static const int kFaceHoldFrames = 4;
static const double kFaceGateStep = 0.125;

// 3.0.7：细节层的**逐像素**自适应 β。为什么全局门控不够 —— 用户报
// 「人脸移动时眼镜有多重延迟的重影」。眼镜是高对比细纹，它的运动在全分辨率
// 细节信号上非常明显，但在 192x256 的掩码轮廓上几乎看不出来，于是全局门控
// 一直按「静止」处理：细频 β=0.20（5 帧常数）、中频 β=0.08（12.5 帧常数），
// 稳态拖尾 = (1-β)/β × v，中频要拖 11.5 倍速度。再叠上掩码 EMA 自己的常数，
// 几层各拖各的，看起来就是「多重」重影。
//
// 换成看**细节信号自身**的帧间差 |Δh|（逐像素、逐通道）。实测分布：
//     ±2 静止噪声  细频 p99 4  max 7    中频 p99 2  max 4
//     ±5 静止噪声  细频 p99 10 max 15   中频 p99 4  max 7
//     ±12 静止噪声 细频 p99 22 max 36   中频 p99 8  max 18
//     运动（slow/mid/fast）细频 p99 13~14 max 83~102
//                            中频 p99 21~24 max 101~131
// 分离点很清楚：噪声全部 ≤15（±5 细频），而眼镜这类强边缘能到 80~130。
// 于是 Lo 以下保持静止强平滑（降噪能力不变），Hi 以上完全放开（强边缘零拖影），
// 中间线性过渡。中频带是 1/64 定点，阈值要乘 64。
//
// 阈值由残影扫描 + DLL 内部细节层探针共同定稿（残影 = |平滑后的 h − 当前真实 h|，
// 取 |Δh| 达到强边缘门限的像素均值）。DLL 实测（slow 缓动，单位=级）：
//     旧规则（全局 β）：细频 15.5 / 中频 15.0
//     10/16, 6/16     ：细频  2.35 / 中频  2.41
//     10/12, 6/10     ：细频  1.14 / 中频  1.14   ← 采用
// 后两组在 ±5 静止噪声上的细节残影完全相同（自适应分支没有被噪声触发），
// 所以收紧 Hi 只影响真正运动的边缘，不拿静止降噪换拖影。
// 12/32 只能把细频压到约 8 级；8/12 会明显削弱 ±5 降噪，均不取。
static const int kFineAdaptLo = 10;
static const int kFineAdaptHi = 12;
static const int kMidAdaptLo  = 6 * 64;
static const int kMidAdaptHi  = 10 * 64;

static double detailBetaFromVel(double v, double stillBeta) {
    if (v <= kDetailVelStill) return stillBeta;
    if (v >= kDetailVelFull)  return 1.0;
    const double t = (v - kDetailVelStill) / (kDetailVelFull - kDetailVelStill);
    return stillBeta + (1.0 - stillBeta) * t;
}

// ---- 3.0.2：中频带（3~7px）回填参数 ----------------------------------------
// 增益标定来自同渲染器对比：对方 r2/r3 是原始画面的 1.6~1.7 倍，我们这条链
// 在中频上是 1.0 倍（98.9% 保留），缺口约 0.65。
//
// 2026-10-25 实测校准（掩码内 mean|img-box_r|，静态帧，磨皮50；软膝前的 3.0.2 数据）：
//     纯磨皮               r1  72.0%  r2  76.6%  r3  79.1%
//     锐化50  (gamma 1.40) r1 138.9%  r2 149.8%  r3 149.4%
//     锐化50+清晰100        r1 154.1%  r2 168.4%  r3 168.4%
//     锐化100 (gamma 2.80) r1 193.1%  r2 209.0%  r3 207.2%
// 目标是 r2/r3 到 165%（对方实测值）。kMidGain=2.8 让默认档（锐化50）落到
// 150%，剩下的缺口交给「清晰」——清 100 正好 168%，两条滑块合起来覆盖到
// 目标而默认不过冲（中频带同时携带肤色不匀，推太狠会显「脏/凹凸」）。
// 细频带（alpha）仍卡在 1.0 不放大：那一档噪点与纹理幅值重叠，3.0.0 的
// 屏闪就是 alpha=0.5 且无时序平滑时爆的；中频带回的是结构，不是噪粒。
//
// 3.0.3 起 2.80 → 3.30：软膝截断把 r2 从 149.8% 压到 137.9%（截掉的都是
// 轮廓，本来就该截），这里把增益补回去 —— 锐化50 约 148%、清 100 约 166%。
static const double kMidGain      = 3.30;   // 中频带基准增益（乘 锐化/100）
static const double kMidGainExtra = 1.00;   // 「清晰」100 时再叠加的量

// 关于「平坦区门限」：最初在这里设了 |h_mid| <= 1 丢、>= 3 全额的门限，想
// 压掉平坦区的量化抖动。实测掩码内 |h_mid| 中位数只有 1 级、p75 是 2 级，
// 该门限平均只放过 23.8%，等于把回填整体吃掉。根因不是「噪声大」，而是
// box3/box7 各自截断到整级带来的 ±0.5 级量化抖动被当成信号放大。
// 现在改成**提高精度**解决：中频带用 1/64 级定点计算（见下面 b3_64/b7_64），
// 量化噪声降到 1% 以下，门限就不需要了 —— 时间方向的噪点本来就由 EMA 管。

// ---- 3.0.3：细节层软膝截断（修「脸颊交界处轻微屏闪」）---------------------
// 现象：3.0.2 装机后用户报「脸颊交界处还是有轻微屏闪」，并圈出了左脸颊与
// 背景交界的那一条。逐帧测量（zone_flicker.py，±2 噪声，按掩码分区）：
//     过渡带 >4 级跳变像素  磨皮50 41 个 → 磨皮50+锐化50 204 个（5 倍）
//     跳变像素的掩码值      中位 83（就是交界处那些半掩码像素）
//     跳变幅度              中位 5 级、最大 8 级
// 机制：皮肤掩码在皮肤/背景交界处是**中间值**（fuai 的概率在 0.5 附近），
// 而那里的 h 是**边缘**不是纹理 —— 实测掩码内回填量 p99 达 51 级、峰值
// 122 级。掩码本身每帧还有 ~13 级摆动（2.2.1 的 EMA 只能压到这个程度），
// 122 × 13/255 ≈ 6 级 —— 与实测跳变完全对上。所以不是噪声问题，是
// 「强回填 × 掩码摆动」在轮廓上的乘积效应。
//
// 解法不是再压掩码（那会重新引入 2.2.1 治好的滞后），而是把细节层截断：
// 纹理本来就在 2~15 级，边缘动辄 50~120 级，放大它们既产生闪烁又产生光晕。
// 用软膝而不是硬截断，避免在 |h| 跨过阈值时切出断层：
//     |v| <= k        → 原样
//     |v| >  k        → k + (|v|-k)·k/|v|，渐近到 2k（连续、一阶连续）
// 实测代价（掩码内部细节保留率，锐化50）：
//     不截断         r1 168.6%  r2 171.2%  r3 168.5%   回填 p99 51.5 / max 122
//     k=12/10        r1 156.4%  r2 155.7%  r3 153.2%   回填 max 约 35
//     k=8/6          r1 146.8%  r2 143.8%  r3 141.3%   回填 max 23
// 取 12/10：交界处跳变从 ~6 级降到 ~1.8 级，立体感只掉约 13 个百分点，
// 缺的部分把「清晰」往上推就能补回来（清晰只加中频增益，同样受截断保护）。
static const int kFineKnee = 12;
static const int kMidKnee  = 10;

static inline int softKnee(int v, int k) {
    const int a = v < 0 ? -v : v;
    if (a <= k) return v;
    const int c = k + ((a - k) * k) / a;   // k .. 2k
    return v < 0 ? -c : c;
}

static void applySharpen(unsigned char* out, const unsigned char* src,
                         int w, int h, double strength, double midGain,
                         const unsigned char* mask, int mw, int mh,
                         const std::vector<int>& x0, const std::vector<int>& x1,
                         const std::vector<int>& wx, const std::vector<int>& y0,
                         const std::vector<int>& y1, const std::vector<int>& wy,
                         std::vector<unsigned short>& tmp,
                         std::vector<unsigned short>& tmp7,
                         std::vector<int>& col7,
                         std::vector<short>& detailPrev,
                         std::vector<short>& midPrev,
                         bool& hasPrev, double betaFine, double betaMid) {
    if (!mask || mw <= 0 || mh <= 0 || w < 3 || h < 3) return;
    // 面板 100 → 3x3 频带全额回填。alpha 就是「原图细节保留比例」。
    // 上限**故意**保持 1.0：细频带里噪点与纹理幅值重叠，放大 1.4 倍就是
    // 3.0.0 那次「脸部屏闪」重演。
    double amt = strength / 100.0;
    if (amt < 0.0) amt = 0.0;
    if (amt > 1.0) amt = 1.0;
    const int a = (int)(amt * 256.0);

    // 3.0.2：中频带增益，由调用方算好传进来（0 = 不回填中频）。
    double gm = midGain;
    if (gm < 0.0) gm = 0.0;
    if (gm > 3.0) gm = 3.0;
    const int g = (int)(gm * 256.0 + 0.5);
    if (a <= 0 && g <= 0) return;

    const size_t n = (size_t)w * h;
    // 只按尺寸扩容、不每帧清零：这两个缓冲随后被完整覆盖，清零纯属浪费
    // （1080p 每帧各 8MB，memset 白扔一两毫秒）。
    if (tmp.size()  != n * 3)         tmp.assign(n * 3, 0);
    if (tmp7.size() != n * 3)         tmp7.assign(n * 3, 0);
    if (col7.size() != (size_t)w * 3) col7.assign((size_t)w * 3, 0);

    // 3.0.1：细节层 EMA 的上一帧缓冲（hv ∈ [-255,255]，短整型）。
    // 尺寸变化（分辨率切换）→ 历史作废；「本帧没回填」时调用方也会把
    // hasPrev 置 false（无人脸 / 磨皮或锐化为 0），复出时不会对上陈旧历史。
    if (detailPrev.size() != n * 3) {
        detailPrev.assign(n * 3, 0);
        hasPrev = false;
    }
    // 3.0.2：中频带同样的历史，单独一份（两带频段与幅值都不同，不能混用）。
    if (midPrev.size() != n * 3) {
        midPrev.assign(n * 3, 0);
        hasPrev = false;
    }
    // 两带各自的时序平滑强度（见 kMidBetaStill：中频带需要更狠）。
    const bool useEmaFine = (betaFine < 1.0);
    const bool useEmaMid  = (betaMid < 1.0);
    const int biFine = (int)(betaFine * 256.0 + 0.5);   // 定点 0..256
    const int biMid  = (int)(betaMid * 256.0 + 0.5);

    // ---- 横向：3-tap 与 7-tap 一起算，都作用在**原图**上 ------------------
    // （旧版模糊的是输出图，那是它无效的原因）
    // 3-tap 给细频带 h_fine = src - box3；7-tap 再给中频带
    // h_mid = box3 - box7。7-tap 用滑窗，每像素只加一次减一次。
    for (int y = 0; y < h; y++) {
        const unsigned char* row = src + (size_t)y * w * 4;
        unsigned short* t3 = &tmp[(size_t)y * w * 3];
        unsigned short* t7 = &tmp7[(size_t)y * w * 3];
        // 7-tap 滑窗（边界复制）的初始窗口是列 clamp(-3..3)；
        // 右移一格：加 clamp(x+4)、减 clamp(x-3)。与 3-tap 合在同一趟里做，
        // 少一遍整行扫描（1074×604 上省 0.8ms 左右）。
        int s0 = 0, s1 = 0, s2 = 0;
        for (int k = -3; k <= 3; k++) {
            const int xx = k < 0 ? 0 : (k >= w ? w - 1 : k);
            const unsigned char* p = row + xx * 4;
            s0 += p[0]; s1 += p[1]; s2 += p[2];
        }
        for (int x = 0; x < w; x++) {
            const int xm = x > 0 ? x - 1 : 0;
            const int xp = x + 1 < w ? x + 1 : w - 1;
            const unsigned char* p0 = row + xm * 4;
            const unsigned char* p1 = row + x * 4;
            const unsigned char* p2 = row + xp * 4;
            t3[x * 3 + 0] = p0[0] + p1[0] + p2[0];
            t3[x * 3 + 1] = p0[1] + p1[1] + p2[1];
            t3[x * 3 + 2] = p0[2] + p1[2] + p2[2];
            t7[x * 3 + 0] = s0;
            t7[x * 3 + 1] = s1;
            t7[x * 3 + 2] = s2;
            const int xa = (x + 4 < w) ? x + 4 : w - 1;
            const int xs = (x > 3) ? x - 3 : 0;
            const unsigned char* pa = row + xa * 4;
            const unsigned char* ps = row + xs * 4;
            s0 += pa[0] - ps[0];
            s1 += pa[1] - ps[1];
            s2 += pa[2] - ps[2];
        }
    }

    // ---- 纵向：3 行给 box3，7 行滑窗给 box7，然后两带一起回填 --------------
    // col7 是 7-tap 横向和的列方向滑窗累加器：从第 0 行的窗口（行号
    // clamp(-3..3)）起步，每下移一行只加新行、减旧行。
    for (size_t i = 0; i < col7.size(); i++) col7[i] = 0;
    for (int k = -3; k <= 3; k++) {
        const int yy = k < 0 ? 0 : (k >= h ? h - 1 : k);
        const unsigned short* r7 = &tmp7[(size_t)yy * w * 3];
        for (int i = 0; i < w * 3; i++) col7[i] += r7[i];
    }

    for (int y = 0; y < h; y++) {
        if (y > 0) {
            const int ya = (y + 3 < h) ? y + 3 : h - 1;   // clamp(y+3)
            const int ys = (y > 4) ? y - 4 : 0;           // clamp(y-4)
            const unsigned short* ra = &tmp7[(size_t)ya * w * 3];
            const unsigned short* rs = &tmp7[(size_t)ys * w * 3];
            for (int i = 0; i < w * 3; i++) col7[i] += ra[i] - rs[i];
        }
        unsigned char* row = out + (size_t)y * w * 4;
        const unsigned char* srow = src + (size_t)y * w * 4;
        const int ym = y > 0 ? y - 1 : 0;
        const int yp = y + 1 < h ? y + 1 : h - 1;
        const unsigned short* tm = &tmp[(size_t)ym * w * 3];
        const unsigned short* tc = &tmp[(size_t)y * w * 3];
        const unsigned short* tp = &tmp[(size_t)yp * w * 3];
        const unsigned char* m0 = mask + (size_t)y0[y] * mw;
        const unsigned char* m1 = mask + (size_t)y1[y] * mw;
        const int fy = wy[y];
        for (int x = 0; x < w; x++, row += 4, srow += 4) {
            const int fx = wx[x];
            const int a0 = m0[x0[x]], a1 = m0[x1[x]];
            const int b0 = m1[x0[x]], b1 = m1[x1[x]];
            const int top = a0 * (256 - fx) + a1 * fx;
            const int bot = b0 * (256 - fx) + b1 * fx;
            const int mv = (top * (256 - fy) + bot * fy) >> 16;
            // 按掩码强度混合：mv=255 时全额回填，半掩码只回一半，
            // 避免在皮肤/非皮肤边界切出硬边。mv=0 时 am=gm2=0，同样不碰输出。
            const int am = (a * mv) >> 8;
            const int gm2 = (g * mv) >> 8;
            // 3.0.1：高频层先算、先过时序 EMA、先存历史 —— 掩码外也更新，
            // 免得掩码边缘像素下次进入掩码时对上好几帧前的陈旧历史。
            short* dpf = &detailPrev[(size_t)y * w * 3 + (size_t)x * 3];
            short* dpm = &midPrev[(size_t)y * w * 3 + (size_t)x * 3];
            for (int c = 0; c < 3; c++) {
                const int i3 = x * 3 + c;
                const int s3 = tm[i3] + tc[i3] + tp[i3];
                const int blur3 = s3 / 9;
                int hf = (int)srow[c] - blur3;   // 细频带 1~2px（不是输出图！）
                // 中频带用 1/64 级定点：box3 与 box7 各自截断到整级会带来
                // ±0.5 级量化抖动，乘以增益后就是平坦区上可见的噪点/色阶。
                // 两路都先乘 64 再除，差值精度 1/64 级。
                const int b3_64 = (s3 * 64 + 4) / 9;
                const int b7_64 = (col7[i3] * 64 + 24) / 49;
                int hm = b3_64 - b7_64;          // 中频带 3~7px（1/64 级）
                // 3.0.7：β 在全局值的基础上再按 |Δh| 逐像素抬高。
                // 平坦区 |Δh| 小 → 仍是全局的强平滑（降噪不变）；
                // 眼镜等强边缘 |Δh| 大 → β 直接到 1（零拖影）。
                if (useEmaFine && hasPrev) {
                    const int pv = (int)dpf[c];
                    const int dd = hf > pv ? hf - pv : pv - hf;
                    int b = biFine;
                    if (dd > kFineAdaptLo) {
                        const int t = dd >= kFineAdaptHi ? 256
                            : ((dd - kFineAdaptLo) * 256) / (kFineAdaptHi - kFineAdaptLo);
                        b = biFine + (((256 - biFine) * t) >> 8);
                    }
                    hf = (hf * b + pv * (256 - b) + 128) >> 8;
                }
                if (useEmaMid && hasPrev) {
                    const int pv = (int)dpm[c];
                    const int dd = hm > pv ? hm - pv : pv - hm;
                    int b = biMid;
                    if (dd > kMidAdaptLo) {
                        const int t = dd >= kMidAdaptHi ? 256
                            : ((dd - kMidAdaptLo) * 256) / (kMidAdaptHi - kMidAdaptLo);
                        b = biMid + (((256 - biMid) * t) >> 8);
                    }
                    hm = (hm * b + pv * (256 - b) + 128) >> 8;
                }
                dpf[c] = (short)hf;
                dpm[c] = (short)hm;
                if (am <= 0 && gm2 <= 0) continue;   // 掩码外不碰（历史已更新）
                // 3.0.3：回填前对细节层做软膝截断。历史存的是截断前的原始值，
                // 免得截断的非线性被 EMA 反复作用。
                int add = (am * softKnee(hf, kFineKnee)) >> 8;
                if (gm2 > 0)
                    add += (gm2 * softKnee(hm, kMidKnee * 64)) >> 14;   // hm 是 1/64 级
                int r = row[c] + add;
                if (r < 0) r = 0;
                if (r > 255) r = 255;
                row[c] = (unsigned char)r;
            }
        }
    }
    hasPrev = true;   // 缓冲已填满，下一帧起可平滑
}

// 毫秒级单调时钟（GetTickCount64 只有 15.6ms 精度，量 4.5ms 的渲染不够用）
double nowMs() {
    static LARGE_INTEGER freq = [] {
        LARGE_INTEGER f;
        QueryPerformanceFrequency(&f);
        return f;
    }();
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)freq.QuadPart;
}

bool readFileBinary(const std::string& path, std::vector<unsigned char>& out) {
    FILE* f = nullptr;
    errno_t e = fopen_s(&f, path.c_str(), "rb");
    if (e != 0 || !f) return false;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (n <= 0) { fclose(f); return false; }
    out.resize((size_t)n);
    size_t got = fread(&out[0], 1, (size_t)n, f);
    fclose(f);
    return got == (size_t)n;
}

void setLastErr(char* buf, int cap, const char* fmt, ...) {
    if (!buf || cap <= 0) return;
    va_list args;
    va_start(args, fmt);
    vsnprintf_s(buf, (size_t)cap, _TRUNCATE, fmt, args);
    va_end(args);
}
}  // namespace

// ---------------------------------------------------------------------------
// 构造 / 互斥
// ---------------------------------------------------------------------------
LegacyEngine::LegacyEngine() {
    CRITICAL_SECTION* cs = new CRITICAL_SECTION;
    InitializeCriticalSectionAndSpinCount(cs, 0x400);
    mutex_ = cs;
}

LegacyEngine& LegacyEngine::inst() {
    // C++11 魔法静态：**指针**的动态初始化由编译器保证只执行一次且线程安全
    // （MSVC 2015+ 默认 /Zc:threadSafeInit）。
    //
    // 旧写法 `static LegacyEngine* s = nullptr; if (!s) s = new LegacyEngine();`
    // 里那句 if 赋值没有任何保护：滤镜创建（UI 线程）与渲染（渲染线程）
    // 首次并发时会各 new 一个引擎，进程里于是有两个 GL 上下文 / 两套 item /
    // 两份参数缓存互相踩，且其中一个永久泄漏。
    //
    // 这里把 new 放进初始化式，既拿到魔法静态的线程安全，又保持「对象刻意不析构」
    // 的行为（避免宿主 FreeLibrary 时静态析构与渲染线程赛跑）。
    static LegacyEngine* s = new LegacyEngine();
    return *s;
}

// ---------------------------------------------------------------------------
// 资源目录定位：以本 DLL 自身位置为准，这样插件装到哪都能找到引擎
//
// OBS 布局（installer/stage/install.bat 装出来的样子）：
//   <OBS>/obs-plugins/64bit/obs-nama-beauty.dll           <- dir_
//   <OBS>/obs-plugins/64bit/obs-nama-beauty/CNamaSDK.dll  <- assetDir_
//   <OBS>/obs-plugins/64bit/obs-nama-beauty/fuai.dll
//   <OBS>/obs-plugins/64bit/obs-nama-beauty/auth_package.bin
//   <OBS>/obs-plugins/64bit/obs-nama-beauty/assets/model/ai_face_processor_pc.bundle
//   <OBS>/obs-plugins/64bit/obs-nama-beauty/assets/graphics/face_beautification.bundle
// ---------------------------------------------------------------------------
bool LegacyEngine::ensurePath(std::string& err) {
    if (pathDone_) return true;

    HMODULE self = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&LegacyVersion, &self);
    if (self) {
        char path[MAX_PATH] = {0};
        GetModuleFileNameA(self, path, MAX_PATH);
        std::string s(path);
        size_t p = s.find_last_of("\\/");
        dir_ = (p == std::string::npos) ? "." : s.substr(0, p);
    } else {
        dir_ = ".";
    }

    // 允许用环境变量覆盖，方便在没装进 OBS 目录时做测试
    const char* override = getenv("BEAUTY_ENGINE_DIR");
    if (override && *override) dir_ = override;

    // 数据目录：DLL 同级的 obs-nama-beauty 子目录
    assetDir_ = dir_ + "\\obs-nama-beauty";
    const char* aover = getenv("BEAUTY_ENGINE_ASSET_DIR");
    if (aover && *aover) assetDir_ = aover;

    pathDone_ = true;
    if (dir_.empty() || assetDir_.empty()) {
        err = "定位引擎目录失败";
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// 隐藏窗口 + WGL 上下文（与旧 obs-nama-beauty.cpp 的 legacy_gl_init 一致）
// ---------------------------------------------------------------------------
bool LegacyEngine::ensureGL(std::string& err) {
    if (glDone_) return true;

    HMODULE self = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&LegacyVersion, &self);

    WNDCLASSA wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = DefWindowProcA;
    wc.hInstance = (HINSTANCE)(self ? self : GetModuleHandleA(nullptr));
    wc.lpszClassName = "LegacyBeautyHiddenGL";
    RegisterClassA(&wc);  // 重复注册会失败，忽略即可

    HWND hwnd = CreateWindowExA(0, wc.lpszClassName, "", 0, 0, 0, 1, 1,
                                nullptr, nullptr, wc.hInstance, nullptr);
    if (!hwnd) { err = "CreateWindowExA 失败"; return false; }
    HDC dc = GetDC(hwnd);
    if (!dc) { err = "GetDC 失败"; return false; }

    PIXELFORMATDESCRIPTOR pfd;
    ZeroMemory(&pfd, sizeof(pfd));
    pfd.nSize = sizeof(pfd);
    pfd.nVersion = 1;
    pfd.dwFlags = PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER | PFD_DRAW_TO_WINDOW;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cAlphaBits = 8;
    pfd.cDepthBits = 24;
    pfd.cStencilBits = 8;
    pfd.iLayerType = PFD_MAIN_PLANE;

    int fmt = ChoosePixelFormat(dc, &pfd);
    if (!fmt) { err = "ChoosePixelFormat 失败"; return false; }
    if (!SetPixelFormat(dc, fmt, &pfd)) { err = "SetPixelFormat 失败"; return false; }
    HGLRC rc = wglCreateContext(dc);
    if (!rc) { err = "wglCreateContext 失败"; return false; }

    hGL_ = hwnd;
    hDC_ = dc;
    hRC_ = rc;
    glDone_ = true;
    // 记下是谁创建的上下文。OBS 的 video_render 来自图形线程而不是加载线程，
    // 这个值只用于诊断：WGL 允许上下文在非并发的情况下换线程。
    ownerThread_ = (unsigned long)GetCurrentThreadId();
    return true;
}

bool LegacyEngine::enter() {
    t_savedDC = wglGetCurrentDC();
    t_savedRC = wglGetCurrentContext();
    // 切换失败时原本的上下文仍然 current，此时绝不能再去 leave()，
    // 否则等于用一对旧值做了一次无意义的 wglMakeCurrent。
    t_enterOk = (wglMakeCurrent((HDC)hDC_, (HGLRC)hRC_) != FALSE);
    return t_enterOk;
}

void LegacyEngine::leave() {
    if (!t_enterOk) return;
    wglMakeCurrent(t_savedDC, t_savedRC);
    t_enterOk = false;
}

// ---------------------------------------------------------------------------
// 加载 SDK / 授权 / 人模型 / 美颜 bundle
// ---------------------------------------------------------------------------
bool LegacyEngine::ensureSDK(std::string& err) {
    char tmp[MAX_PATH + 128] = {0};

    std::string dll = assetDir_ + "\\CNamaSDK.dll";
    // LOAD_WITH_ALTERED_SEARCH_PATH：让 CNamaSDK.dll 能在自己旁边找到 fuai.dll
    HMODULE h = LoadLibraryExA(dll.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!h) {
        sprintf_s(tmp, "LoadLibrary 失败: %s (err=%lu)", dll.c_str(), GetLastError());
        err = tmp;
        return false;
    }
    hModule_ = h;

#define LOAD(f)                                            \
    g_##f = (fn_##f)GetProcAddress(h, #f);                 \
    if (!g_##f) { err = "缺少导出函数 " #f; return false; }

    LOAD(fuSetup)
    LOAD(fuGetVersion)
    LOAD(fuIsLibraryInit)
    LOAD(fuGetSystemError)
    LOAD(fuGetSystemErrorString)
    LOAD(fuSetLogLevel)
    LOAD(fuLoadAIModelFromPackage)
    LOAD(fuSetFaceProcessorDetectMode)
    LOAD(fuFaceProcessorSetFaceLandmarkQuality)
    LOAD(fuSetDefaultRotationMode)
    LOAD(fuSetMaxFaces)
    LOAD(fuFaceProcessorGetNumResults)
    LOAD(fuCreateItemFromPackage)
    LOAD(fuDestroyAllItems)
    LOAD(fuItemSetParamd)
    LOAD(fuItemSetParams)
    LOAD(fuRenderItemsEx)
    LOAD(fuOnDeviceLost)
    LOAD(fuDestroyLibData)
#undef LOAD

    std::vector<unsigned char> auth, faceModel;
    if (!readFileBinary(assetDir_ + "\\auth_package.bin", auth) ||
        !readFileBinary(assetDir_ + "\\assets\\model\\ai_face_processor_pc.bundle", faceModel) ||
        !readFileBinary(assetDir_ + "\\assets\\graphics\\face_beautification.bundle", beautyPkg_)) {
        err = "资源文件缺失（需要 auth_package.bin / assets/model/ai_face_processor_pc.bundle / "
              "assets/graphics/face_beautification.bundle，目录 " +
              assetDir_ + "）";
        return false;
    }

    if (!enter()) {
        err = "wglMakeCurrent 失败（无法切到本引擎的 GL 上下文）";
        return false;
    }

    g_fuSetLogLevel(2);

    int r = 0;
    if (!sehSetup(&r, auth.empty() ? nullptr : &auth[0], (int)auth.size())) {
        InterlockedExchange(&g_sehHit, 1);
        leave();
        err = "fuSetup 抛访问违例（SDK 与本机不兼容或授权异常）";
        return false;
    }
    if (r == 0) {
        leave();
        sprintf_s(tmp, "fuSetup 失败 (err=%d)", g_fuGetSystemError());
        err = tmp;
        return false;
    }
    ver_ = g_fuGetVersion() ? g_fuGetVersion() : "";

    int lmRet = 0;
    if (!sehLoadFaceModel(&lmRet, faceModel.empty() ? nullptr : &faceModel[0],
                          (int)faceModel.size()) ||
        !sehFaceSetup()) {
        InterlockedExchange(&g_sehHit, 1);
        leave();
        err = "人脸模型加载抛访问违例";
        return false;
    }
    if (lmRet == 0)
        NALOG(BEAUTY_LOG_WARNING, "[nama] 警告 fuLoadAIModelFromPackage 返回 0，人脸模型未加载");

    // 创建第一个道具（同时放进 slot 池，供第一个滤镜实例使用）。
    int first = 0;
    if (!createBeautyItemGL(&first)) {
        InterlockedExchange(&g_sehHit, 1);
        leave();
        sprintf_s(tmp, "fuCreateItemFromPackage 失败 item=%d err=%d", first,
                  g_fuGetSystemError());
        err = tmp;
        return false;
    }
    slots_.clear();
    Slot s0;
    s0.item = first;
    slots_.push_back(s0);
    item_ = first;
    leave();

    return true;
}

bool LegacyEngine::createBeautyItemGL(int* outItem) {
    *outItem = 0;
    if (!sehCreateItem(outItem, beautyPkg_.empty() ? nullptr : &beautyPkg_[0],
                       (int)beautyPkg_.size())) {
        InterlockedExchange(&g_sehHit, 1);
        return false;
    }
    if (*outItem <= 0) return false;

    // 模块级默认。两处刻意偏离旧 obs-nama-beauty.cpp：
    //   filter_name/level -> origin/0（见 kFilterName 的说明）；
    //   skin_detect 默认 1（只磨皮肤，别把背景一起磨糊）。
    sehSetParamd(*outItem, "is_opengl_es", 0);  // 桌面 GL，否则 SDK 渲染出全黑
    sehSetParamd(*outItem, "use_landmark", 1);
    sehSetParamd(*outItem, "skin_detect", 1);
    // face_shape=4 / face_shape_level=0：美型模块预加载但总增益为零。
    // 2.0 已删除全部美型滑块，这套配置原样保留（实测过的配置，不动它）。
    sehSetParamd(*outItem, "face_shape", 4);
    sehSetParamd(*outItem, "face_shape_level", 0.0);
    sehSetParams(*outItem, "filter_name", kFilterName);
    sehSetParamd(*outItem, "filter_level", kFilterLevel);
    sehSetParamd(*outItem, "color_level", 0.0);   // SDK 美白恒关（整帧），改走 CPU 掩码
    sehSetParamd(*outItem, "heavy_blur", 0);
    // 诊断注入口（默认空 → 什么都不做）
    applyExtraParams(*outItem, true);
    return true;
}

bool LegacyEngine::ensureReady(std::string& err) {
    return ensureReadyLocked(err, nullptr);
}

bool LegacyEngine::preheat(std::string& err, bool& didInit) {
    didInit = false;
    return ensureReadyLocked(err, &didInit);
}

bool LegacyEngine::ensureReadyLocked(std::string& err, bool* didInit) {
    if (didInit) *didInit = false;

    EnterCriticalSection((CRITICAL_SECTION*)mutex_);
    bool ok = false;
    do {
        if (ready_) { ok = true; break; }
        if (poisoned_) {
            err = "SDK 已因访问违例停用，本进程内不再调用";
            break;
        }
        if (failCount_ >= kMaxInitFail) {
            err = failReason_.empty() ? "引擎初始化已放弃" : failReason_;
            break;
        }
        // 到这里才是真的「需要且允许」做一次初始化
        if (didInit) *didInit = true;
        err.clear();
        if (!ensurePath(err)) break;
        if (!ensureGL(err)) break;
        if (!ensureSDK(err)) break;
        ensureRegion();          // 语义区域：失败只降级，不影响引擎就绪
        ok = true;
    } while (0);

    if (ok) {
        ready_ = true;
        failCount_ = 0;
    } else if (didInit && *didInit) {
        // 只有真的尝试过初始化才累计失败次数（poisoned / 已放弃 不算）
        failCount_++;
        failReason_ = err;
    }
    LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
    return ready_;
}

// ---------------------------------------------------------------------------
// 语义区域（fuai 皮肤分割）
//
// 只在引擎就绪时试一次。失败不设 err、不计数、不影响 ready_ —— 缺 fuai.dll 或
// 缺明文 bundle 是完全正常的情况（安装包里只有加密件），此时全部效果退回
// v1.4 的颜色启发式，行为与 1.4 逐字节一致。
//
// 耗时约 600 ms（读 23 MB bundle + 建 tflite 解释器），与 SDK 的 1.7 s 初始化
// 叠在一起，所以务必只在预热路径里跑（ensureReadyLocked 只会真正初始化一次）。
// ---------------------------------------------------------------------------
bool LegacyEngine::ensureRegion() {
    if (regionInitDone_) return regionActive_;
    regionInitDone_ = true;

    // 诊断开关：BEAUTY_REGION_OFF=1 强制退回 v1.4 行为，用于 A/B 对比同一段素材。
    const char* off = getenv("BEAUTY_REGION_OFF");
    if (off && off[0] == '1') {
        regionErr_ = "被 BEAUTY_REGION_OFF=1 关闭";
        regionActive_ = false;
        NALOG(BEAUTY_LOG_INFO, "[nama] 语义区域被 BEAUTY_REGION_OFF=1 关闭");
        return false;
    }

    LegacyRegion& r = LegacyRegion::inst();
    std::string err;
    if (!r.ensureReady(assetDir_, err)) {
        regionErr_ = err;
        regionActive_ = false;
        NALOG(BEAUTY_LOG_INFO, "[nama] 语义区域不可用，退回颜色启发式：%s", err.c_str());
        return false;
    }
    regionActive_ = true;
    NALOG(BEAUTY_LOG_INFO, "[nama] 语义区域就绪（fuai 皮肤分割，关键点已关，每帧推理）");
    return true;
}

// 这几个只被日志和测试夹具读取，都是无锁的只读快照 —— 读到上一帧的值
// 完全够用，不值得为它加锁。
int LegacyEngine::regionFaces() const { return LegacyRegion::inst().lastFaces(); }
double LegacyEngine::regionCoverage() const { return LegacyRegion::inst().coverage(); }
double LegacyEngine::regionInferMs() const { return LegacyRegion::inst().lastInferMs(); }
long LegacyEngine::regionInferCount() const { return LegacyRegion::inst().inferCount(); }
const char* LegacyEngine::regionErr() const { return regionErr_.c_str(); }

// ---------------------------------------------------------------------------
// 每实例槽位
// ---------------------------------------------------------------------------
int LegacyEngine::acquireSlot(std::string& err) {
    // 先确保引擎就绪（内部加锁并复检；已就绪时只是两次入/出锁，代价极低）
    if (!ensureReadyLocked(err, nullptr)) return -1;

    EnterCriticalSection((CRITICAL_SECTION*)mutex_);
    int idx = -1;
    for (size_t i = 0; i < slots_.size(); i++) {
        if (!slots_[i].inUse) { idx = (int)i; break; }
    }
    if (idx < 0) {
        // 空闲池空了：新建一个道具。GL 上下文只在创建时需要。
        if (!enter()) {
            LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
            err = "wglMakeCurrent 失败（无法为实例创建道具）";
            return -1;
        }
        int it = 0;
        bool cok = createBeautyItemGL(&it);
        leave();
        if (!cok) {
            LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
            err = "创建美颜道具失败";
            return -1;
        }
        Slot s;
        s.item = it;
        slots_.push_back(s);
        idx = (int)slots_.size() - 1;
    }
    slots_[idx].inUse = true;
    // 归还过的槽位可能残留上一个实例的参数指纹，标为「未应用」强制重下发
    slots_[idx].hasApplied = false;
    LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
    return idx;
}

void LegacyEngine::releaseSlot(int slot) {
    EnterCriticalSection((CRITICAL_SECTION*)mutex_);
    if (slot >= 0 && slot < (int)slots_.size()) {
        slots_[slot].inUse = false;
        slots_[slot].hasApplied = false;
    }
    LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
}

void LegacyEngine::setDetectOptions(int rotate, int landmarkQuality, int maxFaces) {
    std::string err;
    if (!ensureReady(err)) return;   // 内部加锁并复检
    EnterCriticalSection((CRITICAL_SECTION*)mutex_);
    if (!poisoned_ && (!skipGlLock() ? enter() : true)) {
        sehDetectOptions(rotate, landmarkQuality, maxFaces);
        leave();
    }
    LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
}

// ---------------------------------------------------------------------------
// 逐帧处理
// ---------------------------------------------------------------------------
bool LegacyEngine::process(const unsigned char* src, unsigned char* dst,
                         int w, int h, const BeautySettings& s) {
    // 自测旧接口：自动占用一个默认槽位（OBS 侧不用，保留给探针脚本）。
    static int defaultSlot = -1;
    if (defaultSlot < 0) {
        std::string e;
        int sl = acquireSlot(e);
        if (sl < 0) {
            failReason_ = e;
            return false;
        }
        defaultSlot = sl;
    }
    return process(defaultSlot, src, dst, w, h, s, true);
}

bool LegacyEngine::process(int slot, const unsigned char* src, unsigned char* dst,
                         int w, int h, const BeautySettings& s, bool advanceFrame) {
    std::string err;
    if (!ensureReady(err)) {
        failReason_ = err;
        return false;
    }
    if (w <= 0 || h <= 0 || !src || !dst) {
        failReason_ = "尺寸或指针不合法";
        return false;
    }

    EnterCriticalSection((CRITICAL_SECTION*)mutex_);

    if (poisoned_) {
        LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
        failReason_ = "SDK 已因访问违例停用";
        return false;
    }
    if (slot < 0 || slot >= (int)slots_.size() || slots_[slot].item <= 0) {
        LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
        failReason_ = "无效的引擎槽位";
        return false;
    }
    Slot& sl = slots_[slot];
    const int item = sl.item;

    // 帧级临时缓冲：SDK 要求输出缓冲独立，不能原地覆盖。
    // memcpy 还有一个作用：SDK 若没有写满全缓冲（例如无人脸时），剩下的像素
    // 保持为输入值而不是垃圾 —— 这是刻意的，不是多余拷贝，别删。
    //
    // 注意这里**不要**预先交换 out。它的用途有两个：
    //   1) SDK 没写满时的兜底内容（此时它应该是 RGBA，因为后面要原样交给 dst）；
    //   2) SDK 的输出缓冲（此时 SDK 会按 BGRA 写它）。
    // 所以交换只做一次，放在 SDK 写完之后（见本函数末尾的 bgraToRgba）。
    // 以前在这里先 rgbaToBgra、末尾又 bgraToRgba，等于交换两次，输出颜色是反的。
    size_t need = (size_t)w * (size_t)h * 4;
    if (work_.size() < need) work_.resize(need);
    unsigned char* out = (unsigned char*)&work_[0];
    memcpy(out, src, need);

    // 3.0.10：混合用的时间平滑原图 srcT。尺寸变了（分辨率切换）必须整帧
    // 重灌当前帧，否则新区域会是 0（黑块）或上一分辨率的错位内容。
    if (sl.blendPrev.size() != need) {
        sl.blendPrev.assign(src, src + need);
        sl.blendSnap = true;
    }

    // 面板值 → SDK 值：value = panel / 100 * sdk_max
    static const char* keys[P_COUNT] = {
        "blur_level", "clarity",  "color_level", "red_level",
        "sharpen",    "face_threed", "eye_bright", "remove_pouch_strength",
        "remove_nasolabial_folds_strength"
    };
    static const double sdkMax[P_COUNT] = {3.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0};

    // 逐帧的 GL 上下文切换可以被 BEAUTY_ENGINE_NO_GLLOCK=1 关掉。
    // 关掉时 leave() 会自动变成空操作（t_enterOk 保持 false），无需额外判断。
    if (!skipGlLock() && !enter()) {
        LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
        failReason_ = "wglMakeCurrent 失败";
        return false;
    }

    double t0 = nowMs();

    // 参数没变就不重复下发 —— 每帧 10 次 setter 都是 SDK 内部的字符串查表。
    // 缓存是**每槽位**的，两个实例交替渲染也不会互相冲掉。
    bool changed = !sl.hasApplied || sl.applied.blur_type != s.blur_type ||
                   sl.applied.skin_detect != s.skin_detect;
    if (!changed) {
        for (int i = 0; i < P_COUNT; i++)
            if (sl.applied.panel[i] != s.panel[i]) { changed = true; break; }
    }

    if (changed) {
        sehSetParamd(item, "blur_type", (double)s.blur_type);
        sehSetParamd(item, "skin_detect", (double)s.skin_detect);
        for (int i = 0; i < P_COUNT; i++) {
            if (i == P_WHITEN) continue;   // 美白不下发 SDK，见 applyWhiten
            // 2.2.0 起红润也不下发：SDK 的 red_level 实测不加红（覆盖 <1%、
            // dRed ≤ +0.65），只会带来 -0.4~-0.9 的压暗。改由 applyRegionEffects
            // 在 CPU 侧按掩码做（抬 R 压 B 的钟形曲线）。
            if (i == P_RED) continue;
            // 3.0.2 起清晰也不下发：SDK 的 clarity 全行程只 +0.23 细节，却会把
            // **整帧**（含背景/字幕）提亮 +2.84 —— 既没用又违反「背景零改动」。
            // 它改作 applySharpen 里中频带的增益旋钮，只在皮肤掩码内生效，
            // 因此需要磨皮 > 0 才有意义（磨皮为 0 时没有可回填的抹除量）。
            if (i == P_CLARITY) continue;
            // 磨皮开启时 SDK 的 sharpen 被 blur 完全掩盖（实测贡献为 0），
            // 这一档改由 CPU 侧 applySharpen 做频率分离式细节回填（3.0.0）。
            // 磨皮为 0 时仍交给 SDK —— 实测无磨皮时 SDK 锐化比 CPU 版强
            // （dDetail +2.17 vs +1.06），没有理由换弱的。
            if (i == P_SHARPEN && s.panel[P_BLUR] > 0.0) continue;
            double v = s.panel[i];
            if (v < 0) v = 0;
            if (v > 100) v = 100;
            // 3.0.8：磨皮强度不再由 blur_level 承担。实测这个参数全行程只在
            // 66%~78% 保留率之间摆动、低端还非单调（见 bgraToRgbaBlend 的表），
            // 它真正的作用只是「0 = 关 / >0 = 开」。所以这里恢复成最简单的
            // 线性映射（0 档必须落到 0 才能真正关掉 SDK 的磨皮），强度改由
            // 渲染后的 bgraToRgbaBlend 按面板值线性混合原图来实现。
            double sdkValue = v / 100.0 * sdkMax[i];
            sehSetParamd(item, keys[i], sdkValue);
        }
        // SDK 自带美白恒关：实测 color_level 是整帧提亮（人脸 11.25 /
        // 背景 11.17 无差别，没人脸的照片也 96% 被改），没有任何参数能
        // 把它限到人脸。美白改由 applyWhiten 按肤色掩码在 CPU 侧完成。
        sehSetParamd(item, "color_level", 0.0);
        // 全局滤镜恒关（见 kFilterName / kFilterLevel 的说明）。
        sehSetParams(item, "filter_name", kFilterName);
        sehSetParamd(item, "filter_level", kFilterLevel);
        // 诊断注入口：与其它参数同批下发（默认空 → 什么都不做）
        applyExtraParams(item, false);
        sl.applied = s;
        sl.hasApplied = true;
    } else {
        // 走文件来源的诊断参数：每帧重新读一次文件并下发，
        // 这样外部只换文件内容就能换参数组合（测量脚本用）。
        if (extraParamsFile()) applyExtraParams(item, true);
    }

    // 非顺序渲染时不推进帧序，避免人脸跟踪的时序状态漂移。
    const int useFrame = advanceFrame ? frameId_ : 0;

    int items[1] = {item};
    int ret = 0;
    // 输入换成 BGRA 再交给 SDK：src 是宿主给的 RGBA，且不能原地改（调用方可能
    // 复用同一块缓冲），所以复制一份到 bgScratch_ 再换。
    // 不换的话人脸检测基本失效 —— 实测 43 张真实照片里 39 张 faces=0。
    if (bgScratch_.size() < need) bgScratch_.resize(need);
    unsigned char* inBgra = (unsigned char*)&bgScratch_[0];
    memcpy(inBgra, src, need);
    rgbaToBgra(inBgra, need);

    if (!sehRender(&ret, FU_FORMAT_RGBA_BUFFER, out,
                   FU_FORMAT_RGBA_BUFFER, (void*)inBgra,
                   w, h, useFrame, items, 1)) {
        // SDK 抛访问违例：把引擎标成毒化状态，本进程内不再调用 SDK。
        // 不这么做的话，后续每一帧都会再崩一次，OBS 会被反复骚扰。
        poisoned_ = true;
        leave();
        LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
        failReason_ = "fuRenderItemsEx 抛访问违例，已停用 SDK";
        return false;
    }
    if (advanceFrame) frameId_++;
    lastSdkMs_ = nowMs() - t0;

    int faces = 0;
    // 3.0.10：查询失败（SEH 兜住的访问违例）不等于「画面里没人脸」。以前直接
    // 归 0，等于让一次查询失败把美白/红润整档关掉一帧 —— 和 faces 抖 0 是
    // 同一个观感（整脸暗一下）。失败时沿用上一帧。
    if (!sehGetNumFaces(&faces)) faces = faces_;
    faces_ = faces < 0 ? 0 : faces;
    leave();

    if (ret == 0) {
        LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
        char t[128];
        sprintf_s(t, "render 返回 0 (err=%d)", g_fuGetSystemError ? g_fuGetSystemError() : -1);
        failReason_ = t;
        return false;
    }
    // ---- 语义掩码 ----------------------------------------------------------
    // 放在 leave() 之后：fuai 是我们不认识的第三方 DLL，**不让它碰我们的 GL
    // 上下文**。enter()/leave() 存在的意义就是把宿主/SDK 的 GL 状态隔离开，
    // 让一个闭源 AI 库在这个窗口里插手是自找麻烦。
    //
    // 这里有个坑值得记下来（2026-10-24）：把这段夹在 sehRender 与 leave()
    // 之间、让上下文保持 current，也能跑通，结果完全一样。真正导致「第一次
    // render 就整进程静默消失」的不是上下文，而是 sehGetSkin 里那个
    // `int extra[4]` —— fuai 实际往里写 6 个 int，栈上越界踩坏 /GS cookie，
    // 触发 __fastfail(0xC0000409)，SEH 和 VEH 都兜不住。详见 legacy_region.cpp。
    const unsigned char* mask = nullptr;
    int mw = 0, mh = 0;
    double cov = 0.0;
    if (regionActive_) {
        LegacyRegion& r = LegacyRegion::inst();
        mask = r.update(src, w, h, kRegionEvery);
        if (mask) {
            mw = r.maskW();
            mh = r.maskH();
            cov = r.coverage();
        }
    }

    // ---- 磨皮强度混合（3.0.8 引入，3.0.10 改为带时间平滑原图）--------------
    // 输出也是 BGRA，换回 RGBA 再交给调用方。这一步必须排在所有 CPU 后处理
    // 之前 —— 美白、细节回填都要作用在真正要输出的那张脸上，而不是作用在
    // 混合前的重磨皮版本上。
    //
    // 3.0.10 起特意排在语义掩码更新**之后**：β 的判据 motion() 读 rawChg_，
    // 而 rawChg_ 只在掩码推理里更新。放在掩码之前 β 就永远滞后一帧 —— 运动
    // 起始的第一帧拿到的还是上一帧的「静止」判据 → β=0.25 → srcT 是上一帧的
    // 原图，实测 20px/帧平移下边缘出现 ±72 级的单帧拖影（与用户报的
    // 「遮罩跟不上 / 重影」同族）。掩码推理只读 src、不碰 out，交换顺序
    // 对结果没有别的影响。
    {
        int t256 = 256;
        if (s.panel[P_BLUR] > 0.0) {
            double tv = s.panel[P_BLUR];
            if (tv > 100.0) tv = 100.0;
            t256 = (int)(tv * 2.56 + 0.5);
        }
        // 3.0.10：混合的原图端用时间平滑后的 srcT（见 bgraToRgbaBlend）。
        // 只有中间档才需要维护它；两个端点走短路分支时不更新，所以要打
        // blendSnap 标记，下次进中间档时整帧对齐一次，避免用上陈旧历史。
        int beta256 = 256;
        if (t256 > 0 && t256 < 256) {
            if (sl.blendSnap) {
                sl.blendSnap = false;          // β=1 → srcT 整帧对齐到当前 src
            } else {
                const double beta =
                    detailBetaFromVel(LegacyRegion::inst().motion(), kBlendBetaStill);
                beta256 = (int)(beta * 256.0 + 0.5);
            }
            bgraToRgbaBlend(out, src, (unsigned char*)&sl.blendPrev[0], need,
                            t256, beta256);
        } else {
            sl.blendSnap = true;
            bgraToRgbaBlend(out, src, (unsigned char*)&sl.blendPrev[0], need,
                            t256, 256);
        }
    }

    // ---- 区域融合 ----------------------------------------------------------
    // 三种情况**不能混为一谈**（2026-10-24 实测踩过）：
    //
    //  1) 有掩码、覆盖度正常 → 按掩码合成。
    //  2) 有掩码、但覆盖度 ≈0 → fuai 在说「这一帧没有皮肤」。这时候必须
    //     **什么都不做**，绝不能退回全帧磨皮：无脸、无人像的素材就撞在这里 ——
    //     掩码全 0，而 SDK 自己的颜色掩码认为 54% 的像素是皮肤，退回老路等于
    //     把整张图磨糊。拿全 0 掩码走一遍 applyRegionEffects 即可：
    //     m=0 的像素逐字节还原成输入，结果就是整帧不动。
    //     例外：SDK 明明检出了人脸、fuai 却说没皮肤 —— 两边判断冲突，更像
    //     fuai 偶发失败。这时退回颜色启发式，至少不会让人脸突然没效果。
    //  3) 拿不到掩码（fuai 不可用 / 连续推理都失败）→ 退回 v1.4 颜色启发式，
    //     也就是 BEAUTY_REGION_OFF=1 时的行为。
    //
    // 注意 src 是 RGBA，正好是 fuai 要的格式（kFmtRGBA），不用像 SDK 那样换序。
    // 掩码缓冲与映射表都是引擎成员，因此只能在锁内用；OBS 的 video_render
    // 本就串行。
    const bool haveMask = (mask && mw > 0 && mh > 0);
    const bool noSkin = haveMask && cov < 0.001;

    // 3.0.10：faces 门控从「硬开关」改成「滞回 + 缓降」。
    // 用户实测的屏闪形态是「整脸突然暗一下再回来」，正是 faces 单帧抖 0 让
    // 美白整档归零（实测美白 50 = 脸内 +8.31 级）。SDK 的人脸跟踪在转头、
    // 遮挡、曝光突变的单帧上确实会漏检，而掩码那边有 3 帧中值 + EMA 兜着，
    // 所以以前只有亮度这一路会整档跳。
    // 规则：faces>0 立刻回满；faces==0 先保持 kFaceHoldFrames 帧，再按
    // kFaceGateStep 缓降。真实离开画面时掩码也会跟着 cov→0，整帧还原，
    // 所以这里慢半拍没有副作用。
    if (faces_ > 0) {
        sl.faceHold = 0;
        sl.faceGate = 1.0;
    } else if (sl.faceHold < kFaceHoldFrames) {
        sl.faceHold++;                       // 保持上一帧的 faceGate 不变
    } else if (sl.faceGate > 0.0) {
        sl.faceGate -= kFaceGateStep;
        if (sl.faceGate < 0.0) sl.faceGate = 0.0;
    }
    const bool faceOn = (sl.faceGate > 0.5);

    if (haveMask && !(noSkin && faceOn)) {
        // 美白沿用 v1.4 的门槛：**没检出人脸就不提亮**。
        //
        // 语义掩码本身是整帧的（没有脸也会给出皮肤色区域），如果不加这个门槛，
        // 把镜头对着米色墙 / 皮沙发也会被提亮 —— 那正是这一轮要修掉的毛病，
        // 只是换了个触发条件。掩码负责「在皮肤内」，faces 负责「画面里确实有人」。
        // 3.0.10：强度按 faceGate 连续缩放，不再 0/1 二值跳变。
        const double whiten = s.panel[P_WHITEN] * sl.faceGate;
        // 红润同样以「检出人脸」为前提，且不再依赖 SDK 的 red_level（那个参数
        // 实测不加红，只会压暗，见 applyRegionEffects 里的实测记录）。
        const double red = s.panel[P_RED] * sl.faceGate;
        applyRegionEffects(out, src, w, h, whiten, red,
                           s.skin_detect != 0,
                           mask, mw, mh,
                           mapX0_, mapX1_, mapWX_, mapY0_, mapY1_, mapWY_);
        // 磨皮开启时 SDK 的 sharpen 会被 blur 完全吃掉（实测贡献为 0），
        // 所以这一档由上面的 applySharpen 在 CPU 侧补，两者不重复。
        // 磨皮为 0 时仍走 SDK（行为与 2.0 一致），那条路径在参数下发处放行。
        //
        // 3.0.0：CPU 这条路从「对磨完的图做 unsharp」改写为「频率分离式细节
        // 回填」—— 高频层从原图 src 取（见 applySharpen 的长注释）。
        // 3.0.1：回填的高频层过一层速度自适应的时序 EMA，把原图高频里的
        // 相机噪点（时间白噪）压掉、静态纹理（时间相关）保留 —— 否则磨皮
        // 把脸抹光滑之后锐化又把噪点叠回来，脸部呈"沸腾"式闪动。
        // 3.0.2：「清晰」也走这条路（它原来是 SDK 的 clarity，实测全行程只
        // +0.23 细节却全帧提亮 +2.84，已改作中频带回填的增益旋钮）。
        if (s.panel[P_BLUR] > 0.0 &&
            (s.panel[P_SHARPEN] > 0.0 || s.panel[P_CLARITY] > 0.0)) {
            // 中频增益：锐化 50 / 清晰 0 → 0.65，把 3~7px 频带推到原图 1.65 倍
            // （对方实测值）。清晰 100 再叠 kMidGainExtra。
            const double midGain = (s.panel[P_SHARPEN] / 100.0) *
                                   (kMidGain + s.panel[P_CLARITY] / 100.0 * kMidGainExtra);
            applySharpen(out, src, w, h, s.panel[P_SHARPEN], midGain,
                         mask, mw, mh,
                         mapX0_, mapX1_, mapWX_, mapY0_, mapY1_, mapWY_,
                         sharpenTmp_, sharpenTmp7_, sharpenCol7_,
                         sl.detailPrev, sl.midPrev, sl.hasDetailPrev,
                         detailBetaFromVel(LegacyRegion::inst().motion(), kDetailBetaStill),
                         detailBetaFromVel(LegacyRegion::inst().motion(), kMidBetaStill));
        } else {
            // 本帧没有回填 → EMA 历史作废，免得下次开锐化时对上陈旧值。
            sl.hasDetailPrev = false;
        }
    } else {
        sl.hasDetailPrev = false;   // 同上（老路径 / 无可用掩码）
        // v1.4 老路径：颜色启发式美白（无脸则什么都不做）。
        // 3.0.10：强度同样按 faceGate 缩放，且「有没有脸」也用滞回后的判断 ——
        // 否则 faces 抖一帧就会在这条路上也整档跳。
        applyWhiten(out, w, h, s.panel[P_WHITEN] * sl.faceGate,
                    faceOn ? 1 : 0, whitenMask_, whitenTmp_);
    }

    if (dst != out) memcpy(dst, out, need);
    LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
    return true;
}

void LegacyEngine::release() {
    if (!ready_) return;
    EnterCriticalSection((CRITICAL_SECTION*)mutex_);
    if (enter()) {
        sehDestroy();
        leave();
    }
    if (hRC_) { wglDeleteContext((HGLRC)hRC_); hRC_ = nullptr; }
    if (hDC_ && hGL_) { ReleaseDC((HWND)hGL_, (HDC)hDC_); hDC_ = nullptr; }
    if (hGL_) { DestroyWindow((HWND)hGL_); hGL_ = nullptr; }
    if (hModule_) { FreeLibrary((HMODULE)hModule_); hModule_ = nullptr; }
    ready_ = false;
    glDone_ = false;
    pathDone_ = false;
    // fuDestroyAllItems 已经把池里所有道具销毁，槽位全部作废
    slots_.clear();
    beautyPkg_.clear();
    // 语义区域：清掉掩码与状态，下次 ensureReady 会重新初始化。
    // 不这么做的话 regionActive_ 仍为 true 但 update() 恒返回 nullptr，
    // 会静默退化成「只有颜色启发式美白、磨皮不再限区域」。
    LegacyRegion::inst().release();
    regionActive_ = false;
    regionInitDone_ = false;
    mapX0_.clear(); mapX1_.clear(); mapWX_.clear();
    mapY0_.clear(); mapY1_.clear(); mapWY_.clear();
    LeaveCriticalSection((CRITICAL_SECTION*)mutex_);
}

// ---------------------------------------------------------------------------
// 自测入参路径是 UTF-8（ctypes / Python 的惯例），但引擎内部走 ANSI 窄路径
// （fopen_s / LoadLibraryExA）。源码放在中文目录时 LoadLibrary 会 err=126。
// 这里在入口统一转成 ACP，自测在中文路径下也能跑。
// ---------------------------------------------------------------------------
static std::string utf8ToAcp(const char* s) {
    if (!s || !*s) return std::string();
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, nullptr, 0);
    if (n <= 0) return std::string(s);
    std::wstring w((size_t)n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s, -1, &w[0], n);
    int m = WideCharToMultiByte(CP_ACP, 0, w.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (m <= 0) return std::string(s);
    std::string a((size_t)m, '\0');
    WideCharToMultiByte(CP_ACP, 0, w.c_str(), -1, &a[0], m, nullptr, nullptr);
    a.resize((size_t)m - 1);   // 去掉结尾 '\0'
    return a;
}

extern "C" {

unsigned long __stdcall LegacyVersion(void) {
    return (unsigned long)((BEAUTY_BUILD_MAJOR << 16) | BEAUTY_BUILD_MINOR);
}

// engineDir 传**数据目录**（含 CNamaSDK.dll 的那一层，即 obs-nama-beauty/）。
int __stdcall LegacySelfTest(const char* engineDir, const char* rawIn, const char* rawOut,
                           int width, int height, double blur, double whiten,
                           char* msgBuf, int msgCap) {
    if (msgBuf && msgCap > 0) msgBuf[0] = 0;
    if (!rawIn || !rawOut || width <= 0 || height <= 0) {
        setLastErr(msgBuf, msgCap, "参数不合法");
        return 2;
    }
    const std::string engineDirA = utf8ToAcp(engineDir);
    const std::string rawInA = utf8ToAcp(rawIn);
    const std::string rawOutA = utf8ToAcp(rawOut);
    if (!engineDirA.empty()) {
        _putenv_s("BEAUTY_ENGINE_ASSET_DIR", engineDirA.c_str());
    }

    FILE* f = nullptr;
    if (fopen_s(&f, rawInA.c_str(), "rb") != 0 || !f) {
        setLastErr(msgBuf, msgCap, "打不开输入文件：%s", rawInA.c_str());
        return 3;
    }
    size_t need = (size_t)width * (size_t)height * 4;
    std::vector<unsigned char> buf(need);
    size_t got = fread(&buf[0], 1, need, f);
    fclose(f);
    if (got != need) {
        setLastErr(msgBuf, msgCap, "输入字节不足：需要 %zu，实际 %zu", need, got);
        return 4;
    }

    BeautySettings s;
    for (int i = 0; i < P_COUNT; i++) s.panel[i] = 0;  // 自测只验证被指定的两项
    s.panel[P_BLUR] = blur;
    s.panel[P_WHITEN] = whiten;
    // 与插件 UI 默认一致：精准美肤开（截图里是勾选状态）
    s.skin_detect = 1;
    // ---- measurement-only hook (NOT in production source) ----
    // panel.txt format: "idx[:value],idx[:value]"
    //   0,4        -> both driven by the `blur` argument
    //   0:75,4:50  -> each with its own value
    {
        FILE* pf = nullptr;
        if (fopen_s(&pf, "C:\\legacy_e2e\\panel.txt", "r") == 0 && pf) {
            char line[256] = {0};
            if (fgets(line, sizeof(line), pf)) {
                for (int i = 0; i < P_COUNT; i++) s.panel[i] = 0;
                char* ctx = nullptr;
                for (char* tok = strtok_s(line, ",", &ctx); tok;
                     tok = strtok_s(nullptr, ",", &ctx)) {
                    int idx = -1;
                    double val = blur;
                    char* colon = strchr(tok, ':');
                    if (colon) {
                        *colon = 0;
                        val = atof(colon + 1);
                    }
                    idx = atoi(tok);
                    if (idx >= 0 && idx < P_COUNT) s.panel[idx] = val;
                }
            }
            fclose(pf);
        }
    }
    s.blur_type = 1;

    double t0 = nowMs();
    std::string err;
    LegacyEngine& e = LegacyEngine::inst();
    if (!e.ensureReady(err)) {
        setLastErr(msgBuf, msgCap, "初始化失败：%s", err.c_str());
        return 5;
    }
    double initMs = nowMs() - t0;

    std::vector<unsigned char> out(need);
    t0 = nowMs();
    bool ok = e.process(&buf[0], &out[0], width, height, s);
    double procMs = nowMs() - t0;
    if (!ok) {
        setLastErr(msgBuf, msgCap, "render 失败：%s", e.lastErr());
        return 6;
    }

    if (fopen_s(&f, rawOutA.c_str(), "wb") != 0 || !f) {
        setLastErr(msgBuf, msgCap, "写不了输出文件：%s", rawOutA.c_str());
        return 7;
    }
    fwrite(&out[0], 1, need, f);
    fclose(f);

    setLastErr(msgBuf, msgCap,
               "OK ver=%s item=%d faces=%d init=%.0fms process=%.1fms sdk=%.1fms",
               e.version() ? e.version() : "?", e.itemId(), e.lastFaces(),
               initMs, procMs, e.lastSdkMs());
    return 0;
}

// ---------------------------------------------------------------------------
// 测试专用：多帧序列驱动（只存在于 C:\legacy_e2e 的测试副本，不进生产源码）。
//
// 用来验证「掩码滞后」BUG：在同一个进程里连续处理 count 帧，每帧写一个输出。
// 单帧的 LegacySelfTest 看不出跨帧滞后 —— 每次都是新进程、掩码必然是最新的。
// ---------------------------------------------------------------------------
int __stdcall LegacySeqTest(const char* engineDir, const char* inDir, const char* outDir,
                          int width, int height, int count,
                          double blur, double whiten, char* msgBuf, int msgCap) {
    if (msgBuf && msgCap > 0) msgBuf[0] = 0;
    if (!inDir || !outDir || width <= 0 || height <= 0 || count <= 0) {
        setLastErr(msgBuf, msgCap, "参数不合法");
        return 2;
    }
    const std::string inA = utf8ToAcp(engineDir ? engineDir : "");
    if (!inA.empty()) _putenv_s("BEAUTY_ENGINE_ASSET_DIR", inA.c_str());

    BeautySettings s;
    for (int i = 0; i < P_COUNT; i++) s.panel[i] = 0;
    s.panel[P_BLUR] = blur;
    s.panel[P_WHITEN] = whiten;
    s.blur_type = 1;
    // 与插件 UI 默认一致：精准美肤开
    s.skin_detect = 1;
    // ---- measurement-only hook: panel.txt (NOT in production source) ----
    {
        FILE* pf = nullptr;
        if (fopen_s(&pf, "C:\\legacy_e2e\\panel.txt", "r") == 0 && pf) {
            char line[256] = {0};
            if (fgets(line, sizeof(line), pf)) {
                for (int i = 0; i < P_COUNT; i++) s.panel[i] = 0;
                char* ctx = nullptr;
                for (char* tok = strtok_s(line, ",", &ctx); tok;
                     tok = strtok_s(nullptr, ",", &ctx)) {
                    int idx = -1;
                    double val = blur;
                    char* colon = strchr(tok, ':');
                    if (colon) {
                        *colon = 0;
                        val = atof(colon + 1);
                    }
                    idx = atoi(tok);
                    if (idx >= 0 && idx < P_COUNT) s.panel[idx] = val;
                }
            }
            fclose(pf);
        }
    }

    LegacyEngine& e = LegacyEngine::inst();
    std::string err;
    if (!e.ensureReady(err)) {
        setLastErr(msgBuf, msgCap, "初始化失败：%s", err.c_str());
        return 5;
    }

    const size_t need = (size_t)width * (size_t)height * 4;
    std::vector<unsigned char> in(need), out(need), prevBuf;
    double totalMs = 0.0, maxMs = 0.0;
    for (int k = 0; k < count; k++) {
        char ip[1024], op[1024];
        sprintf_s(ip, "%s\\seq_%03d.raw", inDir, k);
        sprintf_s(op, "%s\\seq_%03d.raw", outDir, k);
        FILE* f = nullptr;
        if (fopen_s(&f, ip, "rb") != 0 || !f) {
            setLastErr(msgBuf, msgCap, "打不开 %s", ip);
            return 3;
        }
        if (fread(&in[0], 1, need, f) != need) {
            fclose(f);
            setLastErr(msgBuf, msgCap, "%s 字节不足", ip);
            return 4;
        }
        fclose(f);
        double t0 = nowMs();
        if (!e.process(&in[0], &out[0], width, height, s)) {
            setLastErr(msgBuf, msgCap, "第 %d 帧 render 失败：%s", k, e.lastErr());
            return 6;
        }
        double ms = nowMs() - t0;
        totalMs += ms;
        if (ms > maxMs) maxMs = ms;
        // ---- measurement-only hook: 帧间差异 + 状态日志 ----
        {
            const unsigned char* prev = (k == 0) ? &in[0] : &prevBuf[0];
            long long sumAbs = 0;
            int chgPx = 0, mx = 0;
            for (size_t i = 0; i < need; i += 4) {
                int pm = 0;
                for (int c = 0; c < 3; c++) {
                    int dd = (int)out[i + c] - (int)prev[i + c];
                    if (dd < 0) dd = -dd;
                    sumAbs += dd;
                    if (dd > pm) pm = dd;
                }
                if (pm > 2) chgPx++;
                if (pm > mx) mx = pm;
            }
            FILE* lf = nullptr;
            if (fopen_s(&lf, "C:\\legacy_e2e\\seq_log.txt", "a") == 0 && lf) {
                fprintf(lf,
                        "seq=%d faces=%d cov=%.4f infer=%ld meanAbs=%.4f chgPx=%d maxDiff=%d\n",
                        k, e.lastFaces(), e.regionCoverage(),
                        e.regionInferCount(),
                        (double)sumAbs / (double)((need / 4) * 3), chgPx, mx);
                fclose(lf);
            }
            if (prevBuf.size() < need) prevBuf.resize(need);
            memcpy(&prevBuf[0], &out[0], need);
        }
        if (fopen_s(&f, op, "wb") != 0 || !f) {
            setLastErr(msgBuf, msgCap, "写不了 %s", op);
            return 7;
        }
        fwrite(&out[0], 1, need, f);
        fclose(f);
    }
    setLastErr(msgBuf, msgCap,
               "OK frames=%d avg=%.1fms max=%.1fms inferCnt=%ld inferMs=%.2f cov=%.4f",
               count, totalMs / count, maxMs,
               e.regionInferCount(), e.regionInferMs(), e.regionCoverage());
    return 0;
}






































}  // extern "C"
