// legacy_region.cpp —— fuai.dll 驱动实现（OBS 版）。
//
// 从 LegacyBeauty（DaVinci OFX 版）v1.51 的 01_ofx插件源码/src/legacy_region.cpp
// 移植。与原版的唯一差别：stderr 追踪输出改走 legacy_log 钩子（无钩子时仍回
// stderr），其余逐行一致。函数签名来自 05_解密模型数据\REVERSE_REPORT.md
// （Ghidra + ctypes 双重验证），调用顺序照 _tools\extract_face_assets.py 的
// FuAI 封装，两者交叉印证。

#include "legacy_region.h"
#include "beauty_log.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <cmath>

// 时间平滑参数（2.2.1，见 temporalSmooth 上面的长注释）：
//   kEmaStill   —— 画面静止时的 EMA 系数。0.25 把白噪声型抖动压到约 0.39 倍
//                  （标准差），等效 6~7 帧平均窗；静止时无滞后代价。
//   kMotionFull —— 质心速度超过它（掩码像素/帧）就完全关闭平滑。1.5 掩码
//                  像素 ≈ 8.4 帧像素/帧（1074 宽），正常头部运动都在此速度
//                  以下或附近，而静态+噪声的质心抖动只有 0.01~0.10。
//
// 3.0.3 把 kEmaStill 从 0.25 降到 0.10。原因：用户报「脸颊交界处轻微屏闪」，
// 逐项拆解（±2 噪声，独立进程，过渡带掩码 1~249 的帧间 >4 级像素数）：
//     空跑(无效果)      0        仅磨皮50        40
//     仅美白+红润     593        磨50+锐50      197
// 美白/红润那条路是 `src + (sdkOut-src)*m256>>8` —— 边界处就是「原图 ↔ 磨过
// 的图」的交叉淡化，而 d=(sdkOut-src) 在皮肤/背景交界处很大，于是掩码每帧
// 13 级摆动被放大成 5~8 级跳变。掩码自身的摆动 Δ ≈ 52*alpha（实测 alpha=0.25
// 时 13 级），压到 0.10 就只剩约 5 级。滞后代价只落在「接近静止」这一段：
// 速度判据没变，v=0.3 掩码px/帧时 alpha 已回到 0.28（与旧值持平）。
//
// 3.0.4 再加一层 3 帧时域中值（medianRawMask，作用在**原始**二值掩码上），
// 因为 EMA 只能摊薄、不能消掉孤立尖峰：实测原始掩码过渡带帧间 max 达 196，
// EMA(0.10) 之后 max 仍有 20，正是用户看到的「频率低了但还在闪」。
// 加中值后帧间残差 0.95 → 0.69、max 20 → 17，静止时生效、运动时按 kMotionFull
// 自动关掉（详见 medianRawMask 上面的长注释）。3.0.5 起改用 rawChg 门控，
// 且判据换成「连续两帧都在大改才算真运动」，单帧尖峰不再被误判成运动。
//
// 3.0.5 换掉平滑开关。用户反馈「偶尔一两次的闪」+「快速移动时遮罩跟不上脸型」，
// 两个症状同源：α 被锁在 0.10（时间常数 10 帧 ≈ 167 ms @60fps），
// 稳态拖尾 = (1-α)/α × v = **9v 掩码像素 ≈ 50v 帧像素**（192→1074，5.6 倍），
// 掩码边缘只要以 1 掩码像素/帧移动就有 50 帧像素拖尾。
// 而原来的开关是**质心速度**，它对「形变」失明：脸在转、在点头、在靠近镜头时
// 轮廓大面积改变而质心仍只有 0.01~0.10（静止+噪声实测 0.001~0.003），门控判定
// 「静止」，α 一直停在 0.10 —— 于是「抗闪」和「跟得上」直接对撞。
// 改成按**掩码自身变化量** rawChg = mean|raw_cur - raw_prev1| 开关：
//     静止+噪声   实测 0.059~0.107（0.6~0.7% 像素翻转）→ motion 0 → α=0.10
//     纯形变(×1.15) 约 12（≈32% 掩码面积变化）        → motion 1 → α=1 零拖尾
// 分离度 100 倍以上，阈值放中间，两头都留足余量。
static const double kEmaStill   = 0.10;
static const double kMotionFull = 1.5;      // 仅用于质心速度的诊断量，不再当开关
// rawChg / err 的开关区间（0..255 尺度）。3.0.6 重新标定 —— 3.0.5 的死区
// 太宽（chg 0.40~3.00、err 0.30~1.50），中等速度的持续形变整段落在灰色区，
// α 只有 0.15~0.4，稳态拖尾 (1-α)/α·v 折合约 15 帧像素，就是用户报的
// 「快速移动时遮罩跟不上脸型」。
// 死区下限由**噪声地板**决定，不能再降（实测输出掩码帧间残差，过渡带）：
//     ±2 噪声  rawChg 最大 0.107   err 最大 0.092
//     ±5 噪声  rawChg 最大 0.190   err 最大 0.189   ← 差灯光下摄像头的量级
//     ±12 噪声 rawChg 最大 0.391   err 最大 0.344   （画面已不可用）
// 所以取 chg 0.35 / err 0.32（≈±5 地板的 1.8 倍），上限从 3.0/1.5 收到
// 1.0/0.8 把斜率加大 —— 实测（人脸线性放大 1.20/1.12/1.05 三档）：
//     稳态拖尾  0.94/0.71/0.87 → 0.00/0.00/0.32 级
//     噪声残差  ±2 0.082、±5 0.251 两档完全不变
static const double kChgLo = 0.35;
static const double kChgHi = 1.00;
static const double kErrLo = 0.32;
static const double kErrHi = 0.80;
// 3.0.5：连续这么多帧没拿到掩码才真正关效果（单帧丢失沿用上一帧掩码）。
// 3.0.10：2 → 6（≈200ms@30fps）。2 帧太短：只要 fuai 连丢三帧，就会掉到
// 「无掩码」分支，而那条分支不做掩码还原 —— SDK 的磨皮会铺满整幅画面
// （背景一起糊），是整屏级的变化，比掩码本身迟一点严重得多。
// 真人离开画面时 cov 会先掉到 0，走的是「全 0 掩码 = 整帧还原」，不会因为
// 这个延长而留下残影。
static const int kMaskHoldFrames = 6;
// 3.0.12（P1）：连续失败多少帧才判定 fuai 彻底不可用。
//
// 依据（2026-10-25 实测，100 个独立进程 / 3000 次推理调用）：访问违例是
// **每次调用约 0.10% 的独立随机事件**，与调用序号无关 —— 同一进程里出现过
// 间隔 2 帧的两次违例，10 帧短测的冻结帧散布在第 0/1/4/6/7 帧。所以
// 「预热烧掉前几次调用」在原理上就不可能奏效（3.0.12 试过，已删）。
// 连败 12 帧按独立事件估概率约 1e-24，真出现只可能是引擎状态已经坏了，
// 这时才退回 3.0.11 的永久放弃行为。
static const int kMaxFailStreak = 12;

namespace {

// ---------------------------------------------------------------------------
// fuai 导出（__cdecl）
// ---------------------------------------------------------------------------
typedef void* (*fn_newProc)(const char*, int);
typedef void* (*fn_newResult)(void);
typedef void* (*fn_newView)(void);
typedef void  (*fn_initView)(void*, int, int, int, int,
                             void*, int, void*, int, void*, int);
typedef void  (*fn_setViewData)(void*, int, void*);
typedef void  (*fn_process)(void*, void*, void*);
typedef int   (*fn_getNum)(void*);
typedef float* (*fn_getSkinSeg)(void*, void*, int*, int*, int*);
typedef void  (*fn_setInt)(void*, int);

fn_newProc     g_newProc = nullptr;
fn_newResult   g_newResult = nullptr;
fn_newView     g_newView = nullptr;
fn_initView    g_initView = nullptr;
fn_setViewData g_setViewData = nullptr;
fn_process     g_process = nullptr;
fn_getNum      g_getNum = nullptr;
fn_getSkinSeg  g_getSkinSeg = nullptr;
fn_setInt      g_setMaxFaces = nullptr;
fn_setInt      g_setDetectMode = nullptr;
fn_setInt      g_setUseLandmark = nullptr;
fn_setInt      g_setUseHead = nullptr;
fn_setInt      g_setUseHair = nullptr;
fn_setInt      g_setUseSkin = nullptr;

// 图像格式枚举（FUAI_ImageViewInit 的第 2 个参数）
// 0=UNKOWN 1=RGB 2=BGR 3=RGBA 4=BGRA 5=GRAY ...
const int kFmtRGBA = 3;

double nowMsLocal() {
    static LARGE_INTEGER freq = [] {
        LARGE_INTEGER f;
        QueryPerformanceFrequency(&f);
        return f;
    }();
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)freq.QuadPart;
}

std::string utf8ToAcpLocal(const std::string& s) {
    if (s.empty()) return s;
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    if (n <= 0) return s;
    std::wstring w((size_t)n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
    int m = WideCharToMultiByte(CP_ACP, 0, w.c_str(), n, nullptr, 0, nullptr, nullptr);
    if (m <= 0) return s;
    std::string a((size_t)m, '\0');
    WideCharToMultiByte(CP_ACP, 0, w.c_str(), n, &a[0], m, nullptr, nullptr);
    return a;
}

bool readAll(const std::string& path, std::vector<unsigned char>& out) {
    FILE* f = nullptr;
    if (fopen_s(&f, utf8ToAcpLocal(path).c_str(), "rb") != 0 || !f) return false;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (n <= 0) { fclose(f); return false; }
    out.resize((size_t)n);
    size_t got = fread(&out[0], 1, (size_t)n, f);
    fclose(f);
    if (got != (size_t)n) { out.clear(); return false; }
    return true;
}

// ---- 逐调用追踪 ----------------------------------------------------------
// BEAUTY_REGION_TRACE=1 时把每一步写进日志并立刻输出。
// 用来定位「进程直接消失」这类问题 —— SEH 只能兜住本线程的访问违例，
// fuai 内部起的 worker 线程崩了是兜不住的，只能靠最后一条日志判断死在哪。
bool traceOn() {
    static int on = -1;
    if (on < 0) {
        const char* e = getenv("BEAUTY_REGION_TRACE");
        on = (e && e[0] == '1') ? 1 : 0;
    }
    return on == 1;
}

void trace(const char* fmt, ...) {
    if (!traceOn()) return;
    va_list ap;
    va_start(ap, fmt);
    char buf[1024];
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    NALOG(BEAUTY_LOG_DEBUG, "[region] %s", buf);
}

// ---- 致命异常探针 --------------------------------------------------------
// BEAUTY_REGION_TRACE=1 时装一个 VEH。用途：fuai 有些崩溃 SEH 兜不住（另一个
// 线程里炸、/GS cookie 被踩、栈溢出），进程会静默消失、连 WER 事件都没有。
// VEH 在所有 SEH 之前被调用，能把异常码和出错地址打出来，至少知道死因。
LONG CALLBACK regionVeh(EXCEPTION_POINTERS* ep) {
    const DWORD code = ep->ExceptionRecord->ExceptionCode;
    void* addr = ep->ExceptionRecord->ExceptionAddress;
    char mod[MAX_PATH] = {0};
    HMODULE hm = nullptr;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                               GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)addr, &hm) && hm)
        GetModuleFileNameA(hm, mod, MAX_PATH);
    NALOG(BEAUTY_LOG_ERROR, "[region][VEH] 异常 code=0x%08X addr=%p module=%s",
          (unsigned)code, addr, mod[0] ? mod : "?");
    return EXCEPTION_CONTINUE_SEARCH;
}

void installVehOnce() {
    static bool done = false;
    if (done || !traceOn()) return;
    done = true;
    AddVectoredExceptionHandler(1, regionVeh);
    trace("VEH 已安装");
}

// ---- SEH 薄封装 -----------------------------------------------------------
// __try/__except 不能和需要栈展开的 C++ 对象共存，所以每个都做成裸函数。

int sehProcess(void* proc, void* view, void* result) {
    __try {
        g_process(proc, view, result);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehGetNum(void* result, int* out) {
    __try {
        *out = g_getNum(result);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

// 返回 1 成功；0 抛异常；2 返回空指针或尺寸非法
int sehGetSkin(void* proc, void* view, float** ptr, int* w, int* h) {
    __try {
        // -------------------------------------------------------------------
        // 这个 extra 缓冲是踩过坑的地方，别改小（2026-10-24）
        //
        // 05_解密模型数据\_tools\extract_face_assets.py 里是
        //     extra = (ctypes.c_int * 4)()
        // 那是**堆**对象。fuai 往这个指针写的东西明显不止 4 个 int —— 堆上越界
        // 只是悄悄踩坏相邻内存，看不出来；放到栈上就会踩坏 /GS 栈 cookie，
        // 函数返回时 __security_check_cookie 直接 __fastfail(0xC0000409)，
        // 这个终止**绕过 VEH 也绕过 SEH**，表现为「进程静默消失、连 WER 事件
        // 都没有」。这就是为什么同样一段调用序列在 Python 里好好的，
        // 搬到 C++ 里第一次 render 就整进程没了。
        //
        // 现在给 1 KB 余量。若以后又出现 0xC0000409，先把这里再放大。
        // -------------------------------------------------------------------
        int extra[256] = {0};
        // 追踪模式下用哨兵量出 fuai 实际写了多少个 int（只诊断用，不影响生产）
        const int kProbe = 256;
        if (traceOn())
            for (int i = 0; i < kProbe; i++) extra[i] = 0x7F7F7F7F;
        *ptr = g_getSkinSeg(proc, view, w, h, extra);
        if (traceOn()) {
            int last = -1;
            for (int i = 0; i < kProbe; i++)
                if (extra[i] != 0x7F7F7F7F) last = i;
            trace("extra 被写到下标 %d（%d 个 int，缓冲 %d）", last, last + 1, kProbe);
        }
        if (!*ptr || *w <= 0 || *h <= 0) return 2;
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

int sehInitView(void* view, int w, int h, void* buf, int stride) {
    __try {
        // 契约照 extract_face_assets.FuAI.process：先 InitView 只给 stride（缓冲指针留空），
        // 再用 SetViewData 把第 0 平面指过去。stride 传 0 会让 SDK 按错的行距读。
        g_initView(view, kFmtRGBA, w, h, 0, nullptr, stride, nullptr, 0, nullptr, 0);
        g_setViewData(view, 0, buf);
        return 1;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

}  // namespace

LegacyRegion& LegacyRegion::inst() {
    static LegacyRegion s;
    return s;
}

std::string LegacyRegion::findBundle() const {
    // 1) 显式指定
    const char* env = getenv("BEAUTY_REGION_BUNDLE");
    if (env && *env) return std::string(env);
    // 2) 引擎目录旁，按优先级从高到低
    //
    // 第一项必须和安装包布局一致：SDK 资源放在
    //   <assetDir>\assets\model\ai_face_processor_pc.bundle
    // （见 LegacyEngine 里 fuLoadAIModelFromPackage 的路径），所以明文件默认
    // 也放在同一个 assets\model\ 目录下，只把文件名换成 _plain 后缀。
    // 之前这里漏了 assets\ 这一级，导致安装完仍然 region=off —— 日志表现为
    // "找不到明文 bundle"，但文件其实就躺在 assets\model 里。
    const char* names[] = {
        "\\assets\\model\\ai_face_processor_pc_plain.bundle",  // 安装包布局
        "\\ai_face_processor_pc_plain.bundle",                 // fuai.dll 同目录
        "\\model\\ai_face_processor_pc_plain.bundle",
        "\\assets\\model\\ai_face_processor_pc.bundle",
        "\\ai_face_processor_pc.bundle",
        "\\model\\ai_face_processor_pc.bundle",
    };
    for (int i = 0; i < 6; i++) {
        std::string p = dir_ + names[i];
        DWORD a = GetFileAttributesA(utf8ToAcpLocal(p).c_str());
        if (a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY)) return p;
    }
    return std::string();
}

bool LegacyRegion::loadDll(std::string& err) {
    // ---------------------------------------------------------------------
    // 直接加载 fuai.dll，和 CNamaSDK 共用同一份模块实例。
    //
    // 曾经担心过冲突：CNamaSDK.dll 的导入表里就有 fuai.dll（PE 导入表核对过），
    // 我们 LoadLibrary("fuai.dll") 拿回来的是同一个实例，两边各自建一个
    // FaceProcessor，共用 fuai 的全局状态（auth / GLLoader / tflite 池）。
    //
    // 实测结论：**不冲突**。曾经试过复制一份改名 fuai_region.dll 做模块隔离，
    // 崩得一模一样 —— 说明当时那个「第一次 render 就整进程静默消失」跟共享
    // 状态无关，真凶是 sehGetSkin 里 `int extra[4]` 的栈越界（见那个函数的
    // 注释）。修掉之后共享实例完全正常，所以这 29 MB 的副本不需要了。
    // ---------------------------------------------------------------------
    std::string p = dir_ + "\\fuai.dll";
    std::wstring wp;
    int n = MultiByteToWideChar(CP_UTF8, 0, p.c_str(), (int)p.size(), nullptr, 0);
    if (n > 0) {
        wp.resize((size_t)n);
        MultiByteToWideChar(CP_UTF8, 0, p.c_str(), (int)p.size(), &wp[0], n);
    }
    HMODULE h = wp.empty()
                    ? nullptr
                    : LoadLibraryExW(wp.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!h) {
        char b[256];
        sprintf_s(b, "LoadLibrary fuai.dll 失败 (err=%lu)", GetLastError());
        err = b;
        return false;
    }
    hDll_ = h;
    trace("fuai.dll 已加载 (h=%p)", h);
    g_newProc     = (fn_newProc)GetProcAddress(h, "FUAI_NewFaceProcessorFromBundle");
    g_newResult   = (fn_newResult)GetProcAddress(h, "FUAI_NewFaceProcessorResult");
    g_newView     = (fn_newView)GetProcAddress(h, "FUAI_NewImageView");
    g_initView    = (fn_initView)GetProcAddress(h, "FUAI_ImageViewInit");
    g_setViewData = (fn_setViewData)GetProcAddress(h, "FUAI_ImageViewSetData");
    g_process     = (fn_process)GetProcAddress(h, "FUAI_FaceProcessorProcess2Result");
    g_getNum      = (fn_getNum)GetProcAddress(h, "FUAI_FaceProcessorGetNumFromResult");
    g_getSkinSeg  = (fn_getSkinSeg)GetProcAddress(h, "FUAI_FaceProcessorGetSkinSegResult");
    g_setMaxFaces = (fn_setInt)GetProcAddress(h, "FUAI_FaceProcessorSetMaxFaces");
    g_setDetectMode = (fn_setInt)GetProcAddress(h, "FUAI_FaceProcessorSetDetectMode");
    g_setUseLandmark = (fn_setInt)GetProcAddress(h, "FUAI_FaceProcessorSetUseFaceLandmark");
    g_setUseHead  = (fn_setInt)GetProcAddress(h, "FUAI_FaceProcessorSetUseHeadSegmenter");
    g_setUseHair  = (fn_setInt)GetProcAddress(h, "FUAI_FaceProcessorSetUseHairSegmenter");
    g_setUseSkin  = (fn_setInt)GetProcAddress(h, "FUAI_FaceProcessorSetUseSkinSeg");
    if (!g_newProc || !g_newResult || !g_newView || !g_initView || !g_setViewData ||
        !g_process || !g_getNum || !g_getSkinSeg) {
        err = "fuai.dll 缺少必需导出";
        return false;
    }
    return true;
}

bool LegacyRegion::loadBundle(std::string& err) {
    std::string p = findBundle();
    if (p.empty()) {
        err = "找不到明文 bundle（放到 fuai.dll 同目录并命名为 "
              "ai_face_processor_pc_plain.bundle，或用 BEAUTY_REGION_BUNDLE 指定）";
        return false;
    }
    if (!readAll(p, bundle_)) { err = "读取 bundle 失败: " + p; return false; }
    // 加密件以 CNamaSDK 的头开头，明文一定是 Zip
    if (bundle_.size() < 4 || bundle_[0] != 'P' || bundle_[1] != 'K') {
        err = "bundle 不是明文 Zip（随包分发的是加密件，需先导出明文）: " + p;
        return false;
    }
    return true;
}

bool LegacyRegion::ensureReady(const std::string& engineDir, std::string& err) {
    if (ready_) return true;
    if (failed_) { err = err_; return false; }
    dir_ = engineDir;
    trace("ensureReady dir=%s", dir_.c_str());

    if (!loadDll(err)) { trace("loadDll 失败: %s", err.c_str()); failed_ = true; err_ = err; return false; }
    if (!loadBundle(err)) { trace("loadBundle 失败: %s", err.c_str()); failed_ = true; err_ = err; return false; }
    trace("bundle 已加载 %d 字节", (int)bundle_.size());

    trace("-> FUAI_NewFaceProcessorFromBundle");
    proc_ = g_newProc((const char*)&bundle_[0], (int)bundle_.size());
    trace("<- FUAI_NewFaceProcessorFromBundle proc=%p", proc_);
    if (!proc_) {
        failed_ = true;
        err_ = "FUAI_NewFaceProcessorFromBundle 返回 NULL";
        err = err_;
        return false;
    }
    trace("-> FUAI_NewFaceProcessorResult / NewImageView");
    result_ = g_newResult();
    view_ = g_newView();
    trace("<- result=%p view=%p", result_, view_);
    if (!result_ || !view_) {
        failed_ = true;
        err_ = "FUAI result/view 分配失败";
        err = err_;
        return false;
    }

    // 只开皮肤分割，其余全关。关键点也关 —— 这是 2.1.1 的核心改动。
    //
    // 【成本拆解，1074×604，detect_mode=0，实测】
    //   detect + 关键点 + 皮肤   = 11.46 ms   ← 2.1.0 及以前
    //   detect + 皮肤（关关键点） =  2.55 ms   ← 2.1.1
    //   差值 8.91 ms 全是关键点的，占总耗时 78%。
    //
    // 【为什么能关】皮肤分割模型和人脸框/关键点模型是并联的两条支路：
    // 关掉关键点后 GetSkinSegResult 照样吐出 192×256 概率图，而且**逐比特
    // 相同**（实测 0/49152 像素不同，max abs diff = 0；覆盖度、掩码质心、
    // 权重全都一致）。位移跟随也验证过：图像左右各移 60 px，掩码质心
    // +60.3 / −59.9 px。
    //
    // 【安全】关掉关键点不会让分割器在无人脸时乱判：裁掉人脸的帧覆盖度
    // 0.00073、纯棕色场 0.00000，与开关键点时逐字节一致（v1.4 那套
    // Cr/Cb 颜色判据就是在这里翻车的 —— 白衣服/木桌/米墙全中）。
    //
    // 【代价】GetNumFromResult 恒返回 0，所以 faces_ 之后一直是 0。
    // 该字段只有 regionFaces() 一个只读出口，而 regionFaces() 全仓库无人
    // 调用（日志里的人脸数走 LegacyEngine::lastFaces()，来自 CNamaSDK 的
    // fuRenderItemsEx，不受影响）。
    //
    // 头部/头发掩码用不上，关掉可再省约 5 ms/次（实测 +head 17.2 ms vs
    // 不带 15.6 ms，+hair 再多 5 ms；那是带关键点时的数据，仅供参照）。
    trace("-> SetMaxFaces(%d)", 2);
    if (g_setMaxFaces) g_setMaxFaces(proc_, 2);
    trace("-> SetDetectMode(0)");
    if (g_setDetectMode) g_setDetectMode(proc_, 0);   // 0 = 图片模式，逐帧全检，最稳
    trace("-> SetUseFaceLandmark(0)  <- 2.1.1：关关键点，皮肤分割不依赖它");
    if (g_setUseLandmark) g_setUseLandmark(proc_, 0);
    trace("-> SetUseHeadSegmenter(0)");
    if (g_setUseHead) g_setUseHead(proc_, 0);
    trace("-> SetUseHairSegmenter(0)");
    if (g_setUseHair) g_setUseHair(proc_, 0);
    trace("-> SetUseSkinSeg(1)");
    if (g_setUseSkin) g_setUseSkin(proc_, 1);

    ready_ = true;
    trace("ensureReady 完成");
    return true;
}

// ---------------------------------------------------------------------------
// 3.0.12（P1）：推理失败不再永久判死 —— 连续失败计数。
//
// 【为什么改】
// 3.0.11 的做法是：fuai 任何一次调用抛访问违例就置 failed_，本进程内再不调用。
// 后果是掩码全程缺失（update() 恒返回 nullptr）：① 美白/红润退回 v1.4 的
// 颜色启发式（白衣服/木桌/米墙全中）② 磨皮失去掩码限制，背景一起被抹。
// 用户看到的是「效果瞬间失效、再也回不来」。
//
// 2026-10-25 实测把故障性质定死了（100 个独立进程 / 3000 次推理调用）：
//   * 3 次访问违例，全部发生在 FUAI 调用内部，VEH 能抓到（0xC0000005）；
//   * 冻结帧散布在第 0/1/4/6/7 帧，同一进程内还出现过间隔 2 帧的两次违例
//     → **每次调用独立随机，概率约 0.10%，与调用序号无关**；
//   * 因此「预热烧掉前几次调用」在原理上不可能奏效（3.0.12 试过并已删除）；
//   * 每次违例之后 fuai 都还能继续正常出掩码：恢复场次的覆盖度与健康场次
//     逐位相同（0.1444），说明不是「返回垃圾」，也不会连锁崩溃。
// 按 0.10%/次、30 fps 外推，大约每 1000 帧（约 33 秒）撞一次 —— 也就是说
// 3.0.11 在实际直播里几乎必然在开场几十秒内彻底失效。（外推部分为推测。）
//
// 【做法】
//   * 失败时 failStreak_++，连续未达 kMaxFailStreak 且手上有可用掩码 →
//     沿用上一帧掩码并返回 true（复用「本次没检出人脸」的 hold 语义，
//     避免掉进无掩码分支让美白铺满整幅画面）；
//   * 手上一帧掩码也没有（首帧就失败）→ 返回 false，本帧无区域效果；
//   * 连续 kMaxFailStreak 次 → 置 failed_，退回 3.0.11 的行为；
//   * 任何一次成功推理都把 failStreak_ 清零。
// ---------------------------------------------------------------------------
bool LegacyRegion::noteFail(const char* what) {
    failStreak_++;
    err_ = what;
    NALOG(BEAUTY_LOG_ERROR, "[region] 本帧推理失败（连续第 %d 次）：%s", failStreak_, what);
    if (failStreak_ >= kMaxFailStreak) {
        failed_ = true;
        NALOG(BEAUTY_LOG_ERROR, "[region] 连续失败 %d 次，判定 fuai 不可用，"
                              "本次运行内不再推理", failStreak_);
        return false;
    }
    if (hasMask_ && maskHold_ < kMaskHoldFrames) {
        maskHold_++;
        trace("<- 推理失败，沿用上一帧掩码（%d/%d）", maskHold_, kMaskHoldFrames);
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// 诊断自检：BEAUTY_REGION_SELFTEST=1 时由插件在模块加载末尾调用。
//
// 用来切分故障区间：这时 CNamaSDK 已经 fuSetup + 建好美颜道具，但**还没跑过
// 任何一帧 fuRenderItemsEx**。
//   * 自检就崩  → 冲突发生在「加载/建道具」阶段，与渲染无关
//   * 自检正常、render 后崩 → 冲突发生在 SDK 真正跑过 AI 之后
// 两个尺寸都跑一遍：确认 fuai 往 extra 写多少 int 与分辨率无关。
// ---------------------------------------------------------------------------
void namaRegionSelfTest() {
    const char* st = getenv("BEAUTY_REGION_SELFTEST");
    if (!st || st[0] != '1') return;
    const int sizes[2][2] = {{640, 394}, {1920, 1080}};
    for (int k = 0; k < 2; k++) {
        const int W = sizes[k][0], H = sizes[k][1];
        std::vector<unsigned char> buf((size_t)W * H * 4, 0);
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                unsigned char* p = &buf[((size_t)y * W + (size_t)x) * 4];
                p[0] = (unsigned char)(x * 255 / W);
                p[1] = (unsigned char)(y * 255 / H);
                p[2] = 160;
                p[3] = 255;
            }
        }
        NALOG(BEAUTY_LOG_INFO, "[region] SELFTEST %dx%d 开始", W, H);
        const unsigned char* m = LegacyRegion::inst().update(&buf[0], W, H, 1);
        LegacyRegion& r = LegacyRegion::inst();
        NALOG(BEAUTY_LOG_INFO, "[region] SELFTEST %dx%d 结束 mask=%p %dx%d faces=%d cov=%.3f",
              W, H, m, r.maskW(), r.maskH(), r.lastFaces(), r.coverage());
    }
}

bool LegacyRegion::inferOnce(const unsigned char* rgba, int w, int h) {
    double t0 = nowMsLocal();
    installVehOnce();

    trace("-> ImageViewInit(%dx%d stride=%d buf=%p)", w, h, w * 4, rgba);
    if (!sehInitView(view_, w, h, (void*)rgba, w * 4)) {
        trace("ImageViewInit 抛访问违例");
        return noteFail("FUAI_ImageViewInit 抛访问违例");
    }
    trace("-> FaceProcessorProcess2Result");
    if (!sehProcess(proc_, view_, result_)) {
        trace("Process2Result 抛访问违例");
        return noteFail("FUAI_FaceProcessorProcess2Result 抛访问违例");
    }
    trace("<- FaceProcessorProcess2Result");

    int n = 0;
    trace("-> FaceProcessorGetNumFromResult");
    if (!sehGetNum(result_, &n)) {
        trace("GetNumFromResult 抛访问违例");
        return noteFail("FUAI_FaceProcessorGetNumFromResult 抛访问违例");
    }
    // 注意：2.1.1 起 SetUseFaceLandmark(0)，fuai 不再填人脸列表，所以这里
    // 恒为 0。要看真实人脸数请用 LegacyEngine::lastFaces()（来自 CNamaSDK）。
    faces_ = n < 0 ? 0 : n;
    trace("<- faces=%d（关键点已关，恒 0）", faces_);

    float* p = nullptr;
    int mw = 0, mh = 0;
    trace("-> FaceProcessorGetSkinSegResult");
    int r = sehGetSkin(proc_, view_, &p, &mw, &mh);
    trace("<- GetSkinSegResult r=%d ptr=%p %dx%d", r, p, mw, mh);
    if (r == 0) {
        return noteFail("FUAI_FaceProcessorGetSkinSegResult 抛访问违例");
    }
    if (r == 2 || !p || mw <= 0 || mh <= 0) {
        // 没人脸时这里可能是空指针 —— 不是错误，只是本次没有掩码。
        //
        // 3.0.5：单帧没返回掩码时**不要立刻关效果**。mask() 返回 nullptr 会让
        // applyRegionEffects 直接 return，而那时 out 里是 SDK 的**未受限**输出
        // —— 也就是那一帧美白/红润铺满整幅画面（背景一起变亮），是「整屏闪一下」，
        // 不是轻微闪。所以沿用上一帧掩码（maskSoft_ / maskPrev_ 都不动）最多
        // kMaskHoldFrames 帧；真的连续没人才关。
        if (hasMask_ && maskHold_ < kMaskHoldFrames) {
            maskHold_++;
            trace("<- 无掩码，沿用上一帧（%d/%d）", maskHold_, kMaskHoldFrames);
            inferMs_ = nowMsLocal() - t0;
            inferCount_++;
            failStreak_ = 0;   // 3.0.12：SDK 全程正常返回，连续失败计数清零
            return true;
        }
        hasMask_ = false;
        coverage_ = 0.0;
        // ---- measurement-only hook: log no-mask frames (NOT in production) ----
        {
            FILE* kf = nullptr;
            if (fopen_s(&kf, "C:\\legacy_e2e\\dump_mask.txt", "r") == 0 && kf) {
                fclose(kf);
                FILE* lf = nullptr;
                if (fopen_s(&lf, "C:\\legacy_e2e\\infer_log.txt", "a") == 0 && lf) {
                    fprintf(lf, "frame=%d mask=0 mw=0 mh=0 cov=0.0000\n",
                            (int)inferCount_);
                    fclose(lf);
                }
            }
        }
        inferMs_ = nowMsLocal() - t0;
        inferCount_++;
        failStreak_ = 0;       // 3.0.12：同上（只是没人脸，不是故障）
        return true;
    }

    // float 概率 → uint8，顺带算覆盖度（>=0.5 的像素占比）
    const size_t npx = (size_t)mw * (size_t)mh;
    if (mask_.size() < npx) mask_.resize(npx);
    mw_ = mw;
    mh_ = mh;
    // 注意 hit 现在只用于 trace，覆盖度在 softenMask 之后另算
    size_t hit = 0;
    const float* src = p;
    unsigned char* dst = &mask_[0];
    for (size_t i = 0; i < npx; i++) {
        float v = src[i];
        int q = (int)(v * 255.0f + 0.5f);
        if (q < 0) q = 0;
        if (q > 255) q = 255;
        dst[i] = (unsigned char)q;
        if (q >= 128) hit++;
    }
    (void)hit;
    // 3.0.4：先在**原始**掩码上做 3 帧中值（削孤立尖峰），再软化、再 EMA。
    // 门控用的是上一帧 temporalSmooth() 算出的 vEma_（本身已是 0.6/0.4 平滑
    // 过的速度），滞后一帧对「静止/运动」这种慢变量没有影响。
    medianRawMask();
    // 先软化，再时间平滑，最后按实际输出的掩码算覆盖度 —— 那才是作用范围。
    // （曾经把顺序写反，首帧 maskSoft_ 还是空向量，直接访问违例。）
    softenMask();
    temporalSmooth();
    coverage_ = 0.0;
    // ---- measurement-only hook: per-frame mask dump (NOT in production) ----
    {
        FILE* kf = nullptr;
        if (fopen_s(&kf, "C:\\legacy_e2e\\dump_mask.txt", "r") == 0 && kf) {
            fclose(kf);
            char mp[160];
            sprintf_s(mp, "C:\\legacy_e2e\\mask_dump_%03d.raw", (int)inferCount_);
            FILE* mf = nullptr;
            if (fopen_s(&mf, mp, "wb") == 0 && mf) {
                int hdr[2] = { mw_, mh_ };
                fwrite(hdr, sizeof(int), 2, mf);
                fwrite(&mask_[0], 1, npx, mf);
                fwrite(&maskSoft_[0], 1, npx, mf);
                // 3.0.4 追加：rawTmp_ 是**真正未处理**的 fuai 原始掩码（mask_
                // 自 3.0.4 起已被时域中值就地改写）。老分析脚本按 npx 偏移读
                // 前两块，追加第三块不影响它们。
                if (rawTmp_.size() >= npx)
                    fwrite(&rawTmp_[0], 1, npx, mf);
                fclose(mf);
            }
            FILE* lf = nullptr;
            if (fopen_s(&lf, "C:\\legacy_e2e\\infer_log.txt", "a") == 0 && lf) {
                fprintf(lf, "frame=%d mask=1 mw=%d mh=%d cov=%.4f\n",
                        (int)inferCount_, mw_, mh_, coverage_);
                fclose(lf);
            }
        }
    }
    for (size_t i = 0; i < npx; i++)
        if (maskSoft_[i] >= 128) coverage_ += 1.0;
    coverage_ /= (double)npx;
    hasMask_ = true;
    maskHold_ = 0;
    inferMs_ = nowMsLocal() - t0;
    inferCount_++;
    failStreak_ = 0;   // 3.0.12：本次推理完整成功，连续失败计数清零
    return true;
}

// ---------------------------------------------------------------------------
// 软化掩码边界（2.1.2 新增，2.1.3 修掉归一化 bug）。
//
// 为什么必须做：fuai 吐出来的皮肤概率图**不是**软的，是硬二值。实测直方图
//（640x394 单人照，192x256 掩码）：
//     恰好 0       45539 px  92.65%
//     恰好 255       3382 px   6.88%
//     中间值          231 px   0.47%
// 也就是说 0 -> 255 是在一个掩码像素里跳完的。
//
// 后果：applyRegionEffects 对 m=0 的像素是「逐字节还原成原始帧」，对 m=255
// 是「全额应用 SDK 的美颜结果」，中间没有过渡。于是皮肤边界上出现一条
// 1 掩码像素宽（1074 宽画面下约 5.6 帧像素）的硬台阶，一侧是带磨皮/美白的
// 帧、一侧是原始帧。applySharpen 的 3x3 高频叠回专门放大这种不连续，把它
// 变成一条亮边和一条暗边。
//
// 为什么 2.1.0 没暴露：那时掩码每 3 帧才刷新一次，边界基本停在旧位置，这条
// 边线只是静静地待在那儿，看起来像一圈自然的轮廓。2.1.1 改成每帧跟踪人脸
// 之后，边界随头部移动，这条边就跟着在皮肤上扫 —— 用户报的「脸颊处黑白灰
// 快速跳」。
//
// 做法：可分离 5-tap 二项式 [1,4,6,4,1]/16，横纵各一趟。0->255 的过渡摊到约
// 5 个掩码像素（1074 宽下约 28 帧像素），台阶变成渐变，高频叠回无从放大。
// 边缘按复制边界处理，不会把掩码「缩小」出一圈黑边。
//
// 代价：192x256 上 2 趟 x 5 tap = 约 49 万次乘加，实测 < 0.3 ms。
// 副作用：紧贴皮肤的非皮肤像素会分到少量效果（过渡中心 mv~128 即 50%），
// 这是正确的——半 skin 的像素本就该拿一半效果。实测边界外 2 掩码像素处
// mv 约 60，美白只多加 4 个亮度级，可接受。
//
// 2.1.3 的教训（归一化）：可分离滤波**两趟都要各自归一化**。横向少除一个 16、
// 纵向再少除一个 16，最后 (unsigned char) 截断就变成按 256 取模 —— 内部值
// 4080 mod 256 = 240（皮肤白白损失 6% 效果），边界 251/255 之后取模回绕硬摔
// 到 0，比不软化还糟。当时从输出侧怎么看都像「软化只做了一半」，直到把掩码
// 本身 dump 出来才对上号。**这类数字滤镜，落盘看中间量比看终局输出快得多。**
// ---------------------------------------------------------------------------
void LegacyRegion::softenMask() {
    const int mw = mw_, mh = mh_;
    const size_t n = (size_t)mw * (size_t)mh;
    if (maskSoft_.size() < n) { maskSoft_.resize(n); maskTmp_.resize(n); }    if (mw < 3 || mh < 3) {
        // 掩码太小就不糊，直接拷贝原图，保证 maskSoft_ 始终有 n 个有效字节
        if (n) memcpy(&maskSoft_[0], &mask_[0], n);
        return;
    }

    const unsigned char* src = &mask_[0];
    unsigned char* dst = &maskSoft_[0];
    int* tmp = &maskTmp_[0];

    // ---- 横向 5-tap ----
    for (int y = 0; y < mh; y++) {
        const unsigned char* row = src + (size_t)y * mw;
        int* t = tmp + (size_t)y * mw;
        for (int x = 0; x < mw; x++) {
            const int xm2 = x > 1 ? x - 2 : 0;
            const int xm1 = x > 0 ? x - 1 : 0;
            const int xp1 = x + 1 < mw ? x + 1 : mw - 1;
            const int xp2 = x + 2 < mw ? x + 2 : mw - 1;
            // 必须在这一趟就除 16。2.1.2 初版漏了，纵向只除了 16，总共少除 16 倍，
            // 最后 (unsigned char) 按 256 取模，整个掩码变成 16*v mod 256：
            //   内部全 255 区 -> 4080 mod 256 = 240（皮肤只拿到 94% 效果）
            //   边界处         -> 取模回绕，251/255 之后硬摔到 0
            // 用户看到的「脸颊黑白灰跳」剩下的那一处 27 级陡降就是这么来的。
            // 是 mask_dump.raw（2.1.3 加的转储钩子）直接读出掩码值才定位到的。
            t[x] = (row[xm2] + 4 * row[xm1] + 6 * row[x] + 4 * row[xp1] + row[xp2] + 8) >> 4;
        }
    }
    // ---- 纵向 5-tap + 归一化 ----
    for (int y = 0; y < mh; y++) {
        const int ym2 = y > 1 ? y - 2 : 0;
        const int ym1 = y > 0 ? y - 1 : 0;
        const int yp1 = y + 1 < mh ? y + 1 : mh - 1;
        const int yp2 = y + 2 < mh ? y + 2 : mh - 1;
        const int* a = tmp + (size_t)ym2 * mw;
        const int* b = tmp + (size_t)ym1 * mw;
        const int* c = tmp + (size_t)y * mw;
        const int* e = tmp + (size_t)yp1 * mw;
        const int* f = tmp + (size_t)yp2 * mw;
        unsigned char* o = dst + (size_t)y * mw;
        for (int x = 0; x < mw; x++) {
            o[x] = (unsigned char)((a[x] + 4 * b[x] + 6 * c[x] + 4 * e[x] + f[x] + 8) >> 4);
        }
    }
}

// ---------------------------------------------------------------------------
// 3.0.4 新增：原始掩码的 3 帧时域中值（逐像素三取二）。
//
// 为什么 EMA 之外还要这一层：3.0.3 把 kEmaStill 降到 0.10 之后，用户反馈
// 「还是有轻微屏闪（比之前的频率更低）」—— 频率下来了，幅度没干净。把 12 帧
// 原始 fuai 掩码的过渡带（0<soft<250，260 个像素）时间序列拉出来看：
//     帧间 |Δ| 均值 10.6  中位 3  p90 14  max 196
//     dstd/tstd 中位 0.84（白噪≈1.41，单调游走<<1）
//     差分符号翻转率 0.59（白噪≈0.5，单调游走≈0）
// 翻转率 0.59 说明它**大部分**是白噪型的，所以 EMA 压得很有效（10.6→0.95，
// 11 倍）。但 max 196 说明里面夹着孤立的大跳变，而 EMA 对单个尖峰只能摊薄：
// 0.10*196 ≈ 20 —— 正好等于实测的 max 20。用户看到的「频率低了但还在闪」，
// 就是这些漏过去的 20 级尖峰，不是背景噪声。
//
// 再往下压 kEmaStill 也能压尖峰，但整条边界在缓慢转头时会开始拖尾，等于拿
// 一个更难看的毛病换一个更好看的毛病。中值是正解：
//   * fuai 输出本来就是硬二值（92.65% 恰为 0、6.88% 恰为 255），二值图上做
//     3 帧中值 = 逐像素三取二多数表决，这是二值噪声的标准解法，不是模糊 ——
//     不会让边界变软、也不会让效果变淡。
//   * 中值**原样通过单调斜坡**（转头时边界匀速移动，三帧中值就是中间那帧），
//     所以几乎不增加滞后。实测：原始+EMA0.10 帧间 |Δ| 0.95 / max 20；
//     原始+中值3+EMA0.10 → 0.69 / max 17（残差降 27%，尖峰被削平）。
//
// 顺序：中值必须在 softenMask() **之前**。软化的 5-tap 会把孤立尖峰摊成一个
// 小团，团比点难被中值消掉，效果要打对折。
//
// 3.0.5 的门控。原来用 `vEma_ >= kMotionFull` 跳过中值，判据本身没问题
// （质心速度对平移有效），但和新的平滑开关不是同一个量，容易出现「中值开了、
// α 却已经放开」这种半吊子状态。现在统一用 rawChg：
//     中值只在 rawChg < kChgHi 时做。
// 为什么不需要「连续两帧都在大改」这种防误触条件：中值要消掉的是**逐像素的
// 孤立尖峰**，实测这类尖峰在整幅统计上只有 rawChg ≈ 0.08（和噪声同级），
// 根本触发不了 kChgHi。而 rawChg 一旦超过 kChgHi，就说明是整片区域在变
// （平移/形变），那时候中值不但没用，还会对移动边界多压 1 帧（实测 20px/帧
// 平移下正好 16 px 偏差）。所以直接按当帧变化量开关，运动起始那一帧也不滞后。
//
// 代价：192x256 两趟遍历（先算变化量、再按需做中值），实测 0.02 ms。
// ---------------------------------------------------------------------------
void LegacyRegion::medianRawMask() {
    const size_t n = (size_t)mw_ * (size_t)mh_;
    if (n == 0 || mask_.size() < n) return;

    if (rawPrev1_.size() < n) {
        rawPrev1_.resize(n);
        rawPrev2_.resize(n);
        rawTmp_.resize(n);
        rawHist_ = 0;   // 尺寸变了（分辨率切换），历史作废
    }

    unsigned char* cur = &mask_[0];
    // 本帧原始值先留一份：cur 马上要被中值就地覆盖，而历史必须存原始值
    memcpy(&rawTmp_[0], cur, n);
    const unsigned char* c0 = &rawTmp_[0];     // 本帧原始

    // ---- 第 1 趟：rawChg = mean|本帧 - 上一帧| ----
    double chg = 0.0;
    if (rawHist_ >= 1) {
        const unsigned char* p1 = &rawPrev1_[0];
        long long sum = 0;
        for (size_t i = 0; i < n; i++) {
            const int b = p1[i], c = c0[i];
            sum += (b > c ? b - c : c - b);
        }
        chg = (double)sum / (double)n;
    }
    rawChgPrev_ = rawChg_;
    rawChg_ = chg;

    // ---- 第 2 趟：需要时做 3 帧中值（尖峰/微抖）----
    if (rawHist_ >= 2 && chg < kChgHi) {
        const unsigned char* p2 = &rawPrev2_[0];
        const unsigned char* p1 = &rawPrev1_[0];
        for (size_t i = 0; i < n; i++) {
            const int a = p2[i], b = p1[i], c = c0[i];
            int med;
            if (a < b) {
                if (b < c)      med = b;      // a<b<c
                else if (a < c) med = c;      // a<c<=b
                else            med = a;      // c<=a<b
            } else {
                if (a < c)      med = a;      // b<=a<c
                else if (b < c) med = c;      // b<c<=a
                else            med = b;      // c<=b<=a
            }
            cur[i] = (unsigned char)med;
        }
    }

    // 历史推进：永远存**原始帧**，绝不存中值结果
    memcpy(&rawPrev2_[0], &rawPrev1_[0], n);
    memcpy(&rawPrev1_[0], &rawTmp_[0], n);
    if (rawHist_ < 2) rawHist_++;
}

// 3.0.5：把 rawChg_ 归一化成 0..1 的运动强度。
// 这个量同时给掩码的时间 EMA 和细节层的时序 EMA 当开关，取代原来的质心速度
// （质心对旋转/点头/靠近镜头这类**形变**失明，详见 kChgLo 上面的长注释）。
double LegacyRegion::motion() const {
    if (rawChg_ <= kChgLo) return 0.0;
    if (rawChg_ >= kChgHi) return 1.0;
    return (rawChg_ - kChgLo) / (kChgHi - kChgLo);
}

const unsigned char* LegacyRegion::update(const unsigned char* rgba, int w, int h, int every) {
    if (!ready_ || failed_ || !rgba || w <= 0 || h <= 0) return nullptr;
    if (every < 1) every = 1;

    // 2.1.1 起 every 传 1（见 ensureReady 里关关键点的成本拆解）：单次推理
    // 2.55 ms，比 2.1.0 的「每 3 帧跑一次 11.46 ms」摊到 3.82 ms/帧还便宜，
    // 而且掩码零滞后。降频分支保留，万一以后在更慢的机器上要退档，
    // 把 LegacyEngine 的 kRegionEvery 改回 2 或 3 即可，不用改这里。
    const bool due = (!hasMask_) || (frameSeq_ % (long)every == 0);
    frameSeq_++;
    if (due) {
        if (!inferOnce(rgba, w, h)) return nullptr;
    }
    // 2.1.2 起返回**软化后**的掩码。mask_ 保留 fuai 的原始二值图，只作诊断用。
    return hasMask_ ? &maskSoft_[0] : nullptr;
}

// ---------------------------------------------------------------------------
// 时间平滑（2.2.1 新增）。
//
// 为什么必须做：2.1.2/2.1.3 把掩码边界的**空间**台阶摊成了渐变，但边界仍在
// **帧间**抖动。实测（1074×604 真实帧，逐帧叠加 ±2 传感器噪声模拟摄像头）：
//   原始掩码  每帧 ~300/49152 像素变化（0.6%），集中在边界 0/255 翻转
//   软化掩码  每帧 ~1000 像素变化，最大摆动 28~44 级，98.4% 落在过渡带
// 对照实验：同一帧重复 12 次（零噪声）时掩码逐比特相同 —— 抖动完全由输入
// 噪声驱动，fuai 的边界概率在 0.5 附近，亚灰度级的输入变化就能把边界像素
// 推过阈值。后果：过渡带像素的美白/红润强度每帧反复横跳（边界亮度随机
// 振荡 ±2.5 级），就是用户报的「部分部位遮罩屏闪」。5-tap 空间平滑摊薄了
// 单帧跳变，但帧间摆动照旧。
//
// 做法：对软化后的掩码做 EMA（cur = a*new + (1-a)*prev）。关键是强度
// **随运动速度自适应**，否则就重回 2.1.0 的掩码滞后：
//   * 画面静止（质心速度 ~0）：强平滑（a=0.25），边界抖动压到约 0.39 倍。
//     静止时根本没有「滞后」可言，压得越狠越好。
//   * 画面在动：a 随速度线性升到 1，质心速度超过 kMotionFull（1.5 掩码
//     像素/帧 ≈ 8.4 帧像素/帧 @1074 宽）时完全关闭平滑，边界零滞后。
//   * 过渡段稳态拖尾 = (1-a)/a * v，全速度段 <= ~0.4 掩码像素（约 2 帧
//     像素），远低于 2.1.0 时代 66ms/60px 的滞后量级。
// 速度估计本身也做 EMA，避免 a 抖动把抖动又带回来。
//
// 运动判据的实测分隔带：静态+噪声时质心位移仅 0.01~0.10 掩码像素/帧，
// 与 kMotionFull=1.5 之间有 15 倍以上余量，判据干净。
//
// **3.0.5 推翻了上面这套判据。** 质心速度对「平移」有效，对「形变」失明：
// 用户报「快速移动时遮罩跟不上脸型」，而脸在转、在点头、在靠近镜头时，
// 轮廓大面积改变、质心却几乎不动（实测 0.001~0.003），门控一直判定「静止」，
// alpha 锁在 0.10（时间常数 10 帧 ≈ 167 ms），稳态拖尾 = 9v 掩码像素
// ≈ 50v 帧像素 —— 1 掩码像素/帧的边界移动就有 50 帧像素拖尾。
// 现在改用 medianRawMask() 顺带算出的 rawChg_（掩码自身的帧间变化量）：
//     静止+噪声      rawChg 0.059~0.107  → motion 0 → alpha 0.10（抗闪不变）
//     形变 ×1.15     rawChg ≈ 12         → motion 1 → alpha 1.00（零拖尾）
// 分离度 100 倍以上。质心速度保留下来只作诊断（velEma()）。
//
// 代价：192x256 一次质心遍历 + 一次混合，实测 < 0.1 ms。
// ---------------------------------------------------------------------------
void LegacyRegion::temporalSmooth() {
    const int mw = mw_, mh = mh_;
    const size_t n = (size_t)mw * (size_t)mh;
    if (n == 0) return;
    if (maskPrev_.size() < n) {
        maskPrev_.resize(n);
        hasPrev_ = false;   // 尺寸变了（分辨率切换），历史作废
    }

    // ---- 质心（掩码值加权，49k 像素可忽略）----
    double sx = 0.0, sy = 0.0, sw = 0.0;
    for (int y = 0; y < mh; y++) {
        const unsigned char* row = &maskSoft_[(size_t)y * mw];
        for (int x = 0; x < mw; x++) {
            const int v = row[x];
            if (v) { sx += (double)x * v; sy += (double)y * v; sw += v; }
        }
    }

    if (!hasPrev_) {
        // 首帧：直接采用并建立历史
        memcpy(&maskPrev_[0], &maskSoft_[0], n);
        if (sw > 0.0) { cxPrev_ = sx / sw; cyPrev_ = sy / sw; }
        else          { cxPrev_ = -1.0;     cyPrev_ = -1.0;     }
        vEma_ = 0.0;
        hasPrev_ = true;
        return;
    }

    // 3.0.5：平滑强度由两路取大 ——
    //   ① motion()  输入在变多少（rawChg）：**提前**放开，适合持续运动；
    //   ② err       输出离输入还差多少：**兜底**，输入停了也能把剩余差值追完。
    // 只看 ① 会在「单帧跳变」时提前收手（见 kErrLo 注释）；只看 ② 则永远比
    // 变化晚一帧。两路取大，静止时仍然是 kEmaStill，抗闪能力不变。
    double err = 0.0;
    {
        const unsigned char* cur = &maskSoft_[0];
        const unsigned char* prev = &maskPrev_[0];
        long long sum = 0;
        for (size_t i = 0; i < n; i++) {
            const int a = cur[i], b = prev[i];
            sum += (a > b ? a - b : b - a);
        }
        err = (double)sum / (double)n;
    }
    double m = motion();
    if (err > kErrLo) {
        double e = (err >= kErrHi) ? 1.0 : (err - kErrLo) / (kErrHi - kErrLo);
        if (e > m) m = e;
    }
    const double alpha = kEmaStill + (1.0 - kEmaStill) * m;

    if (sw > 0.0) {
        const double cx = sx / sw, cy = sy / sw;
        if (cxPrev_ >= 0.0) {
            const double dx = cx - cxPrev_, dy = cy - cyPrev_;
            const double v = sqrt(dx * dx + dy * dy);
            vEma_ = 0.6 * v + 0.4 * vEma_;   // 只留作诊断，不再当开关
        }
        cxPrev_ = cx; cyPrev_ = cy;
    } else {
        // 本帧掩码全 0：速度估计清零，质心标记失效（下帧重新建立）
        vEma_ = 0.0;
        cxPrev_ = -1.0; cyPrev_ = -1.0;
    }

    if (alpha < 1.0) {
        const int ai = (int)(alpha * 256.0 + 0.5);   // 0..256
        unsigned char* cur = &maskSoft_[0];
        const unsigned char* prev = &maskPrev_[0];
        for (size_t i = 0; i < n; i++)
            cur[i] = (unsigned char)((cur[i] * ai + prev[i] * (256 - ai) + 128) >> 8);
    }
    memcpy(&maskPrev_[0], &maskSoft_[0], n);
}

void LegacyRegion::release() {
    // 刻意不 FreeLibrary：宿主可能还有别的线程在用，进程退出交给 OS 回收。
    ready_ = false;
    proc_ = nullptr;
    result_ = nullptr;
    view_ = nullptr;
    mask_.clear();
    maskSoft_.clear();
    maskPrev_.clear();
    rawPrev1_.clear();
    rawPrev2_.clear();
    rawTmp_.clear();
    rawHist_ = 0;
    rawChg_ = 0.0;
    rawChgPrev_ = 0.0;
    maskHold_ = 0;
    hasPrev_ = false;
    cxPrev_ = -1.0;
    cyPrev_ = -1.0;
    vEma_ = 0.0;
    bundle_.clear();
}
