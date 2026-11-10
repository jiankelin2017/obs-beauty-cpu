// beauty_core.cpp —— 引擎抽象层 + 三个实现的容器
//
//   1) PassthroughEngine：直通，用来证明「开关真的生效」；
//   2) CoreEngine：自研引擎，3.1.7 起是唯一的实现；
//   3) beautyEngine()：返回选定的实现（默认 core）。
//
// 3.1.21：旧的参考实现驱动适配层（LegacyAdapter）**已从插件里移除**。
// 它只在离线基准 DLL（ref_golden.dll）里保留 —— 那份 DLL 的作用是「量出参考
// 实现的行为」，不随插件发布。插件的编译单元里不再有任何参考实现二进制名。

#include "beauty_env.h"   // beauty_env()：BEAUTY_* 覆盖的唯一入口（1.0.13.10 C-2/C-3）
#include "beauty_core.h"
#include "beauty_face.h"
#include "beauty_freq.h"
#include "beauty_guide.h"
#include "beauty_log.h"     /* 1.0.3.0：输入方向探测的告警要走宿主日志 */
#include "beauty_onnx.h"
#include "beauty_pool.h"
#include "beauty_region.h"
#include "beauty_smooth.h"
#include "beauty_warp.h"   /* 3.1.27：美形三项的几何变形 */

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <vector>

/* 1.0.8.0：A 通道置位改用 SSE2（forceOpaque）。x86/x64 上 SSE2 恒定可用，
 * 不引入 /arch:AVX2 之类的运行期依赖。 */
#include <emmintrin.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#ifdef BEAUTY_WITH_LEGACY_ENGINE
#include "legacy_engine.h"
#endif

namespace {

#ifdef BEAUTY_WITH_LEGACY_ENGINE
// ---------------------------------------------------------------------------
// LegacyAdapter —— 旧链路适配器（仅离线基准 DLL 编译，插件不编译这段）
// ---------------------------------------------------------------------------
class LegacyAdapter : public IBeautyEngine {
public:
    const char* id() const override { return "legacy"; }
    const char* version() const override { return LegacyEngine::inst().version(); }

    bool ensureReady(std::string& err) override { return LegacyEngine::inst().ensureReady(err); }
    bool preheat(std::string& err, bool& didInit) override {
        return LegacyEngine::inst().preheat(err, didInit);
    }
    bool ready() const override { return LegacyEngine::inst().ready(); }

    int acquireSlot(std::string& err) override { return LegacyEngine::inst().acquireSlot(err); }
    void releaseSlot(int slot) override { LegacyEngine::inst().releaseSlot(slot); }
    void setDetectOptions(int rotate, int landmarkQuality, int maxFaces) override {
        LegacyEngine::inst().setDetectOptions(rotate, landmarkQuality, maxFaces);
    }

    bool process(int slot, const unsigned char* src, unsigned char* dst,
                 int w, int h, const BeautySettings& s,
                 bool advanceFrame = true) override {
        return LegacyEngine::inst().process(slot, src, dst, w, h, s, advanceFrame);
    }

    int lastFaces() const override { return LegacyEngine::inst().lastFaces(); }
    bool regionActive() const override { return LegacyEngine::inst().regionActive(); }
    double lastCoreMs() const override { return LegacyEngine::inst().lastCoreMs(); }
    const char* lastErr() const override { return LegacyEngine::inst().lastErr(); }
    int itemId() const override { return LegacyEngine::inst().itemId(); }
    unsigned long ownerThread() const override { return LegacyEngine::inst().ownerThread(); }

    void release() override { LegacyEngine::inst().release(); }
};

#endif  // BEAUTY_WITH_LEGACY_ENGINE

// ---------------------------------------------------------------------------
// PassthroughEngine —— 直通
//
// 用途有两个：
//   * 证明 A/B 开关确实接上了（切过去画面应当变成完全没美颜的原图）；
//   * 作为自研引擎出错时的安全降级目标（比「滤镜整体直通」更安全：OBS 侧的
//     尺寸/纹理/自检逻辑仍然照常跑一遍，不会因为降级而悄悄失效）。
//
// 刻意**不**做任何图像处理：一旦它产出与输入不一致的像素，就说明骨架接错了。
// ---------------------------------------------------------------------------
class PassthroughEngine : public IBeautyEngine {
public:
    const char* id() const override { return "passthrough"; }
    const char* version() const override { return "0"; }

    bool ensureReady(std::string& err) override { err.clear(); return true; }
    bool preheat(std::string& err, bool& didInit) override {
        err.clear();
        didInit = false;
        return true;
    }
    bool ready() const override { return true; }

    int acquireSlot(std::string& err) override { err.clear(); return 0; }
    void releaseSlot(int) override {}
    void setDetectOptions(int, int, int) override {}

    bool process(int, const unsigned char* src, unsigned char* dst,
                 int w, int h, const BeautySettings&,
                 bool = true) override {
        if (!src || !dst || w <= 0 || h <= 0) return false;
        if (dst != src) memcpy(dst, src, (size_t)w * (size_t)h * 4);
        return true;
    }

    int lastFaces() const override { return 0; }
    bool regionActive() const override { return false; }
    double lastCoreMs() const override { return 0.0; }
    const char* lastErr() const override { return ""; }
    int itemId() const override { return 0; }
    unsigned long ownerThread() const override { return (unsigned long)GetCurrentThreadId(); }

    void release() override {}
};

// smoothstep 的 C++ 版（OBS 的 effect 里没有内置，这里自己写）
inline float smoothStep(float a, float b, float x) {
    if (b <= a) return (x < a) ? 0.0f : 1.0f;
    float t = (x - a) / (b - a);
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    return t * t * (3.0f - 2.0f * t);
}

// 约束到 [0,1]。面板档位是 0..100 的 double，面板外（离线脚本）可能给越界值。
inline float clampi01(double v) {
    const float f = (float)v;
    return f < 0.0f ? 0.0f : (f > 1.0f ? 1.0f : f);
}

// 五锚点查表（锚点对应面板 0/25/50/75/100），中间线性插值。
// 用它而不是幂函数：产品曲线在低档几乎是硬拐点（25 档 ≈ 满档的 0.5%），
// 任何单项幂函数都拟合不出「0.005 / 0.211 / 0.588 / 1.0」这条形状。
inline float lvLerp5(const float tbl[5], float t) {
    if (t <= 0.0f) return tbl[0];
    if (t >= 1.0f) return tbl[4];
    const float u = t * 4.0f;
    const int i = (int)u;
    const float f = u - (float)i;
    if (i >= 4) return tbl[4];
    return tbl[i] + (tbl[i + 1] - tbl[i]) * f;
}

// 七锚点非均匀表（1.0.0.1 低档段重标定）。
// 为什么不能继续用等距 5 锚点：把 25 档锚点从 0.020 抬到约 0.081 能修好
// 「低档零响应」，但 25→50 之间只有一条直线，40 档会被抬得过高。产品低档段
// 的 I(t) 斜率依次约为 0.719 / 0.299 / 0.844，不是常数，因此必须在
// t=0.25~0.50 之间加密锚点。50/75/100 三档的锚点值与斜率保持原样，
// 使高档输出逐字节不变。
static const float kLvKnot7[7] = {
    0.00f, 0.25f, 0.30f, 0.40f, 0.50f, 0.75f, 1.00f
};
inline float lvLerp7(const float tbl[7], float t) {
    if (t <= 0.0f) return tbl[0];
    if (t >= 1.0f) return tbl[6];
    for (int i = 0; i < 6; i++) {
        if (t <= kLvKnot7[i + 1]) {
            const float span = kLvKnot7[i + 1] - kLvKnot7[i];
            const float f = (t - kLvKnot7[i]) / span;
            return tbl[i] + (tbl[i + 1] - tbl[i]) * f;
        }
    }
    return tbl[6];
}

// "a,b,c,d,e" → 5 个 float。缺项保持原值，便于只覆盖其中几个锚点。
inline void parseN(const char* s, float* out, int n) {
    if (!s || !*s) return;
    const char* p = s;
    for (int i = 0; i < n && p && *p; i++) {
        out[i] = (float)atof(p);
        const char* q = strchr(p, ',');
        p = q ? (q + 1) : nullptr;
    }
}
inline void parse5(const char* s, float out[5]) { parseN(s, out, 5); }
inline void parse7(const char* s, float out[7]) { parseN(s, out, 7); }

// 自研核参数：CoreEngine 与离线调参入口共用。默认值 = 离线对拍最佳组合。
struct SmoothCfg {
    int radius = beautycore::kSmoothRadius;
    float sigmaSpace = beautycore::kSmoothSigmaSpace;
    float sigmaColor = beautycore::kSmoothSigmaColor;
    int down = 1;
    // 0 = 自动（按硬件并发数，上限 8）；1 = 强制单线程（调参复现用）
    int threads = 0;
    // 只在掩码包围盒内做滤波。关掉它只能用于「测量全帧成本」这类对照实验，
    // 生产路径必须保持开启：关掉后 93% 的算力会花在随后被丢弃的像素上。
    bool roi = true;
    // 3.1.40：确认「本帧真的没人」时直接透传，不再退回「无掩码 = 全帧磨皮」。
    //
    // 为什么需要这个开关：旧行为（< 3.1.40）在「曾经检测到过脸、之后人走开」
    // 时会把整幅画面磨一遍 —— 磨皮核把空掩码当「全皮肤」（m = 255），ROI 也
    // 放开成全帧，于是 1080p 磨皮段从约 5~7 ms 涨到全帧量级，而这些像素随后
    // 一个都不会被用到（其余九项全挂在 haveMask 之下，本来就不动）。
    // 观感上还多一个副作用：背景/衣物被一起磨糊。
    //
    // 默认开。`BEAUTY_NOFACE_SKIP=0` 逐字节回到 3.1.39 的全帧兜底行为 ——
    // 只在「想拿无脸帧当纯滤镜磨整幅画面」或「怀疑检测坏了」时才需要。
    bool noFaceSkip = true;
    // ---- 输入方向（1.0.3.0，从 GPU 版 3.2.0 移植）----
    // 源被场景项转过 90° 时（竖屏摄像头 / 手机竖拍），OBS 的旋转只作用于**显示
    // 合成**，滤镜拿到的仍是横躺的那一帧：YuNet 在躺倒的脸上检不出框 → 掩码为空
    // → 磨皮/美白/润肤整段静默失效。用户看到的是「人明明是正的，美颜毫无反应」。
    //
    // 宿主拿不到场景项的 transform（滤镜只看得见 target source 的纹理），所以
    // 「源有没有被转」只能**试**：连续若干次检不到脸后，在同一张输入图上各跑一次
    // 90°/270° 的重采样检测，任一方向出脸就认定该方向，下一帧起按它检测、再把
    // 几何反变换回源坐标。
    //
    // 开关：BEAUTY_AUTO_ROT=0 整段关掉（逐字节回到 1.0.2.0 的「源躺着脸就检不到」）。
    bool autoRot = true;
    // 连续多少次「检不到脸」的检测之后才开始试。默认 20 ≈ 0.7 秒（30fps、异步
    // 每帧提交）。太小会在人刚走出画面时白试；太大则用户要多等一会儿。
    int autoRotMiss = 20;
    // 一次试探之后的冷却（按检测次数算）。命中后不再试探（方向已定），这条只对
    // 「试了也没人」的情形生效：默认 60 次 ≈ 2 秒一次，代价可忽略。
    int autoRotCool = 60;
    // 1.0.5.0：平面内倾斜（roll）补偿。
    //
    // 与上面那条是两件事：autoRot 解决「源被整体转了 90°」（整幅图躺着），
    // roll 解决「源是正的、但人的头歪着」。实测（05_验证/ab20261109_head_roll.md）：
    // YuNet 对平面内倾斜的容忍边界在 30~40° 之间 —— 30° 还能检出，**45° 时
    // faces=0**，掩码为空 → 磨皮/美白/五官整段静默失效。用户描述为「头歪一下
    // 美颜就没了」。
    //
    // 做法：检不到脸时在 ±45° 上各跑一次检测，命中就记下这个 roll，下一帧起
    // 按 (方向 + roll) 的合成角去检测，框再反变换回源坐标。
    // 开关：BEAUTY_AUTO_ROLL=0 关掉（逐字节回到 1.0.4.0）。
    bool autoRoll = true;
    // 探测前要连续多少次无脸。默认 4 ≈ 0.13 秒 —— 比 autoRotMiss 小得多，因为
    // 「刚还在、突然检不到」通常就是头歪了，反应要快；人真走开时多两次推理无所谓。
    //
    // 1.0.13.6：8 → 4。头歪到 45° 附近时 YuNet 会**直接检不出**，要等这条探测
    // 接手；原来等 8 帧，这 8 帧里形变和磨皮都只能靠旧框撑着（掩码靠 kMaskHold
    // 保住，但框一直是旧的外接盒），接上那一刻框要整体塌一次 —— 用户感知到的
    // 「闪一下、卡一下」就出在这里。实测 45° 素材逐帧记录：f00..f07 连续 8 帧
    // 无脸，f08 才被 roll 探测接上。降到 4 把窗口砍一半，代价只是人真离开画面
    // 时多跑两次推理（每次 ≈ 一次 YuNet 前向）。
    int rollMiss = 4;

    // 1.0.13.9：倾斜锁死释放的对照周期（帧）。0 = 关闭（退回 1.0.13.8 行为）。
    //
    // 为什么需要这条：roll 一旦锁定，原来的唯一出口是「按锁定角检不到脸」那条兜底。
    // 但头回正之后，YuNet 在 -45° 输入下**照样给框** —— 是个撑大的敷衍框，
    // score 能到 0.8 上下、双眼间距比也可能落进 plausible 区间。于是 detOk 为真、
    // plausOk 也为真，兜底与倾斜探测两条路都不会触发，roll 就永久停在 -45。
    // 实测回正后 mask 23097 px vs 正常 17805 px（+30%）、phi +42.6°（应≈0）——
    // 位置看着正常只是因为 phi 与 roll 两个误差碰巧互相抵消。
    //
    // 45 帧 ≈ 1.5 s @30fps：够慢到正常歪头时不误判，够快到回正后一秒半内归位。
    // 每次只多一次 640×640 推理，摊到 45 帧上可忽略。
    int rollCheckFrames = 45;

    // 对照判据的余量：0° 对照的 score 必须比当前锁定角**高出这么多**才释放。
    // 沿用下面倾斜探测的 0.05 —— 同一个道理，门槛太松会在两个角度之间来回跳，
    // 每跳一次都要清人脸框 EMA，画面会抖。
    float rollReleaseMargin = 0.05f;

    // Sobel 边缘门控的灵敏度。0 = 关闭（退回纯掩码混合）。
    // 灵敏度取自 wuxiwuhen/obs-beauty-filter（MIT）的 PSComposite：
    //   edge = saturate(|∇luma| * k),  k 默认 10（该仓库用 ×10.0）
    // 实测：k=10 时高梯度区磨皮量降到 81.8%，低梯度区 100.0% 不变。
    // 调参见 04_文档/C2_边缘门控与保边核.md
    int edgeK = 10;
    // 五官保护强度 0..100。磨皮权重会乘 (1 - protect × protectK/100)，
    // 0 = 不保护，100 = 五官区域完全不磨。做法同 lumina 的 uSmoothProtect。
    //
    // 80 → 40 是 C 方案的一部分：原来唇细纹理 96.7%（参考实现89.3%），保护压太死。
    // 40 的取舍依据是**眼区**：protectK 0/20/40/60/80 对应眼区
    // 90.3/90.9/91.7/92.6/93.5，而参考实现是 91.3 —— 40 恰好落在参考实现线上，
    // 再往下眼睛就被磨得比参考实现还狠了（见 C15 §3）。
    int protectK = 40;
    // 阈值软膝：|src - smoothed| 超过它就开始减少磨皮，到 2.5 倍时完全不磨。
    //
    // **默认关闭（0）**：实测在我们的实现里几乎没有效果。原因是我们用的是
    // r=2 的双边滤波，本身就很保边 —— 全帧平均 |src-sm| 只有 0.064/255，
    // 连 15 的阈值都够不到，所以 thr=15/30/50 时高差值区的磨皮量都在 99.8%
    // 以上，等于没动。这条在 lumina 那边有意义，是因为它用的是大半径高斯，
    // |src-sm| 本来就大。
    //
    // 保留这个能力是为「以后换成更大半径的核」留口子，生产不开。
    int limitThr = 0;

    // ---- 高低频磨皮（频率分离）----
    // 1 = 用高低频（默认），0 = 退回旧的「双边滤波 + 线性混合」。
    // 旧方式的问题：dst = src·(1-t) + blur·t 会把**所有频段**一起削弱 t 倍，
    // 包括脸部的低频结构（明暗层次、骨骼起伏）→ 强度一大就"糊"。
    // 高低频只压「幅度小的高频」（毛孔/痘印），低频从不动。
    int freqMode = 1;
    // 低频尺度 = radius × iters。迭代比放大半径便宜：r=2 迭代 3 次 ≈ 半径 6 的
    // 保边模糊，成本却只有 r=6 的约 1/9（面积比）。
    // lowPath=3（盒式）时这一项不生效，尺度由 boxRadius/boxIters 决定。
    int freqIters = 2;
    // 幅度门控。magHi 从 30 抬到 60 是 C 方案的一部分：换成不保边的盒式低通后，
    // 高频层的幅度整体变大，30 会把痘印/鼻翼阴影一起当成「结构」放过去 ——
    // 实测 magHi 30→60 让额头 90.4%→81.0%、鼻翼 93.4%→85.4%（见 C15）。
    // 眉毛/唇线这些真边缘的幅度远大于 60，仍然被拦住（眼区实测 92.3%，参考实现 91.3%）。
    float freqMagLo = 6.0f;  // 幅度小于它：全按强度磨
    float freqMagHi = 60.0f; // 幅度大于它：完全不动（眉毛、鼻梁边、嘴唇轮廓）
    // 颗粒回填：把 4 邻域尺度的极细颗粒扣回一部分。
    // 0.5 → 0.10 也是 C 方案的一部分：它原本是给**双边迭代的阶梯感**打的补丁，
    // 盒式低通没有阶梯；而实测它是「细纹理保留率」的最大单一来源
    // （脸颊 60.2% → 80.2%，见 C15），留着就把刚追上的差距又吐回去了。
    float freqGrain = 0.10f;
    // 低频提取：0 = 双边迭代（快，有阶梯），1 = 引导滤波（无阶梯，O(1)）
    int freqLowMode = 0;
    int guideRadius = 12;
    float guideEps = 400.0f;

    // 低频层的第二条路线（与 freqLowMode 互斥，>0 时优先）：
    //   0 = 旧的 uint8 双边迭代（绝对颜色差、中间结果压回 uint8）—— 默认
    //   1 = 浮点双边（只换精度）
    //   2 = 浮点双边 + 低频参照（权重只看局部起伏）
    //
    // **默认 0 是实测结论，不是保守**：2026-10-28 用 golden 对三条路线做了
    // 逐项对照（04_文档/C8_低频层对照_浮点与参照.md），把 lumina 那套
    // 「(tap-center)-(refTap-refCenter)」搬到我们 r=2 的核上：
    //   小幅度高频保留 106.0% → 105.4%（几乎不变）
    //   大幅度保留        99.1% → 98.8%（更差）
    //   脸颊台阶像素      59.4% → 66.8%（更差，磨出更多平台边）
    //   成本              6.6 ms → 10.5 ms @640×394（+60%）
    // 四条都更差或持平，所以不投产。代码保留是因为：① 换更大半径的核时它可能
    // 才起作用（lumina 等效半径 ≈12px，我们只有 2）；② 它同时也是「ROI 局部
    // 浮点平面」这套基础设施的唯一使用者，删了要重写。
    // 3 = 盒式迭代低通（C 方案，见 C14/C15）：不保边，保边交给幅度门控。
    // **默认 3**（2026-10-28 起）：实测脸颊细纹理保留 86.0% → 64.9%（参考实现63.1%），
    // 四区域平均绝对差从 18.6pp 降到 2.0pp。旧的 0/1/2 三条双边路线全部保留，
    // 用 BEAUTY_LOW_PATH 切回去做对照。
    int lowPath = 3;
    // 参照半径（盒式）。8 → 17 像素窗口，约等于「大尺度」而不是「皮肤纹理」。
    int refRadius = 8;
    // lowPath=3 的尺度：等效 σ² = boxIters × ((2·boxRadius+1)² − 1) / 12。
    //
    // 默认 r=2 / iters=2 → σ≈2（两步 5×5 盒式 ≈ 9×9 高斯）。这个值是**按三频带**
    // 选的，不是按细频带：只看细频带的话 r=4/it=2 更贴近 参考实现（脸颊 65.0 vs 63.1），
    // 但它的中频/阴影会掉到 77.4/94.0，而参考实现是 83.8/96.8 —— 中频削太多就是
    // 「脸塌」。r=2/it=2 的三频带平均绝对差 1.92pp，r=4/it=2 是 4.49pp（C15 §3）。
    //
    // 扫参时最反直觉的一条：**r 越大磨得越少**。低通越糊，|src−low| 幅度越大，
    // 越容易被 magHi 门控拦住。别再靠加大半径去追强度。
    int boxRadius = 2;
    int boxIters = 2;
    // 磨皮档位的饱和系数（见 process() 里的 t_eff 公式）。0 = 退回线性。
    float blurSat = 0.16f;

    // ---- 磨皮核模型（3.1.14 / C22）----
    // 0 = legacy：盒式高低频 + 幅度门控 + blendWithMask（3.1.12/3.1.13 默认）
    // 1 = surface3：三层表面模糊，按参考实现 GLSL 结构重写（见 C22）
    // **3.1.17 起默认 1**（配合 s3Band=1 组成生产路径）。
    // 依据：真机帧 1920×1080 / 脸宽 529px / 磨皮 100 离线对拍「参考实现真值」
    // （加密 bundle、不下发 blur_type = bt2）：
    //     legacy     RMSE 3.251  改动量 1.480  空间相关 0.312  ← 装机旧默认，严重欠磨
    //     band T=14  RMSE 2.280  改动量 2.740  空间相关 0.769
    //     band T=8.3 RMSE ~1.63  改动量 ~1.98  空间相关 ~0.823  ← 新默认
    //     产品真值    —          改动量 2.034
    // 回退：BEAUTY_SMOOTH_MODEL=legacy
    int smoothModel = 1;
    // surface3 的两层半径 / 迭代 / 颜色阈值。默认值只是起点，由离线拟合定。
    // 半径**随档位增长**（C22 §4：真机 50 档等效 r≈6、100 档 r≈10）：
    //     r(t) = s3R0 + (s3R1|s3R2 − s3R0)·t
    int s3R1 = 14, s3It1 = 1;
    int s3R2 = 14, s3It2 = 1;
    int s3R0 = 2;                 // t=0 时的半径（两层共用）
    float s3Thr1 = 0.0f, s3Thr2 = 0.0f;
    // 档位曲线（3.1.14 起改用 GLSL 原式，不再拟合）：
    //     intensity  = mix(t·K, 1.0, step(0.7, t))   ← step 的自变量是**乘之前**的 t
    //     evenfactor = mix(E0, intensity − E0, step(0.6, intensity))
    // 三段形态：[0, 0.42] 恒 0.3；(0.42, 0.70] 线性升到 0.7；[0.70, 1] 恒 0.7。
    // （0.42 = 0.6/1.4286，即 intensity 刚够到 EThr 的档位）
    // 关键含义：t ≥ 0.7 之后 intensity 恒为 1，**75→100 档的差别不可能来自这里**，
    // 只能来自第一级预模糊 —— 这是第 2 批必须补上 pre_blur 的直接原因。
    // 旧的线性拟合式 e = eLo + (eHi−eLo)·t（0.45→0.60）已删除：它是阶段 3 扫参的
    // 产物，与源码结构不符（见 C23 §2.3；原载于已移除的 `00_先读我.md` §4.3）。
    float s3K = 1.4286f;          // 强度饱和系数（= 1/0.7，与 step 阈值配套）
    float s3ESat = 0.7f;          // step(0.7, t) 的阈值，用乘之前的 t
    float s3EThr = 0.6f;          // step(0.6, intensity) 的阈值
    float s3E0 = 0.3f;            // evenfactor 的下限，同时也是减数
    // >=0 时强制 evenfactor 取该值（离线扫参／诊断用；生产保持 -1 走原式）。
    // 为什么需要：e 只由 I 决定，于是 I<0.6 的档位 e 一律 0.3，低档纹理
    // 磨削量被压在平坦区的 1/2，而产品的低档反而是纹理先动。
    float s3EFix = -1.0f;
    // 眼睛保护的排除强度（%，100 = 完全按 protect 掩码排除）。
    // 3.1.14 起 protect 只有眼睛：参考实现没有 lip 通道，嘴唇当皮肤磨。
    float s3EyeK = 100.0f;

    // ---- 25 tap 表面模糊（第 2 批 #5/#6/#7，C23 §3）----
    // 0 = 旧的盒式两层（boxRgbRoi，半径随档位 + 按脸宽 fw/532 归一化）
    // 1 = 25 tap 表面模糊，固定 UV 半轴，串行两趟 yFactor 40→20
    // 用 BEAUTY_S3_TAP25=1 打开。**定稿前不翻默认**（默认仍是 0，legacy 与
    // 现有 surface3 的输出都不动）。
    int s3Tap25 = 0;
    // UV 半轴【实测】0a″ 光栅实验：四画幅 σx = 1.95/3.85/7.72/11.20 px，
    // 拟合 σx ∝ W^0.98 → 核定义在 UV 空间。这两个常量**不是拟合值**，别按
    // 画幅或脸宽去改它们 —— 改了就退回拟合路线（C23 §8.4 明令禁止）。
    float s3Sx = 0.002640845f;
    float s3Sy = 0.0046875f;
    // 两趟的值域权重系数【实测·标定，非源码】。容限 Δg = 1/sqrt(yFactor)：
    //   pass1 110 → 0.0953；pass2 55 → 0.1348
    //
    // 怎么定的（重要，别当成拟合）：C23 原来记的是 40/20【重建·待证】。用光栅法
    // 量自研引擎的等效核宽，40/20 得到 σx=4.67px，而参考实现实测 σx=3.85px —— 核宽
    // 了 21%，过磨的直接原因。扫 yFactor 得到 σx：40→4.67、80→4.10、160→3.54，
    // 对 log2(yFactor) 线性插值到 σ=3.85 得 yFactor≈109。取 110。
    // 验证（不是调参）：像素级改动量 2.73 灰阶 vs参考实现 2.71，几乎完全对上；
    // 皮肤内部 RMSE 2.795（盒式）→ 2.417。
    // 注意 yFactor 再往上（160/80）RMSE 只再降 0.056，但在噪声内，且幅度掉到
    // 2.46 明显欠磨 —— 按 RMSE 去挑就是拿金标拟合，不做。
    float s3YF1 = 110.0f;
    float s3YF2 = 55.0f;
    // 半分辨率处理【实测】。UV 与分辨率无关，所以它不改变核的物理尺寸。
    int s3Half = 1;

    // ---- 双尺度带通 + 振幅门控（第 2 批-B，C23 §11/§12）----
    // 0 = 关（25 tap / 盒式两条老路径）
    // 1 = surface3RgbBand：B1 窄、B2 宽两个不同尺度的模糊 + 振幅门控
    // **3.1.17 起默认 1**（与 smoothModel=1 配套 = 生产路径）。
    // 为什么要换掉 25 tap：§10.4 频响实测是双凹陷（稀疏环核的旁瓣），§11.4
    // 振幅依赖只有 1.05 倍（参考实现2.0 倍）。根因见 §11.5：B1/B2 必须尺度不同。
    // 回退：BEAUTY_S3_BAND=0
    int s3Band = 1;
    // 振幅门控阈值 T（灰阶）。w = 1/(1+(a/T)²)，a = blur(|C.g − B2.g|)。
    // 【3.1.17 重定】原值 14 是按「改动量 2.704」标的，而那个 2.704 来自我们自己
    // 的 ref_golden.dll 显式下发 bt=1 的金标 —— 不是参考实现产品。参考实现实测
    // **从不下发 blur_type**，生效档是 bundle 默认 bt2，同帧改动量只有 2.034。
    // 按产品真值重扫（同帧、磨皮 100）：T=14→2.740 / 12→2.529 / 10→2.279 /
    // 9→2.138 / 8→1.979 / 7→1.803。
    // 【3.1.17】先取 8.3：插值后改动量 ≈2.03、RMSE ≈1.63、相关 ≈0.823，与产品
    // 真值 2.034 相差 <0.3%。
    // 【3.1.19】改取 **6.5**：8.3 只对上了总量，对不上分布 —— 产品「越平越磨、
    // 越有结构越保守」，平坦/纹理比 1.39，而 8.3 只有 1.09。T 是唯一能改这个
    // 比值的旋钮（I/e 只等比缩放），降到 6.5 后比值 1.31，掉的总量由 e 补回。
    // 注意方向：T 越小 → gw=1/(1+(a/T)²) 整体越小 → 磨得越轻、纹理保留越多。
    float s3BandT = 6.5f;

    // ---- 门控陡度指数（3.1.19）------------------------------------------
    // gw = 1/(1+(a/T)^gwp)。p=2 是原式；p>2 让「越平越磨、越有结构越保守」
    // 的非对称变强 —— 平坦/纹理比是产品最明显的分布特征（产品 1.39，我方
    // p=2 时只有 1.10）。T 单独调不动这个矛盾：它同时缩放两个分区。
    float s3Gwp = 2.0f;

    // ---- 档位 → (I, T) 查表（3.1.18）------------------------------------
    // 为什么必须查表：band 路径原先只有 I 一条随档位变化的腿，而 I 在 t≥0.7
    // 就饱和到 1（s3ESat），于是 70~100 档输出逐字节相同（死区），且低档
    // 起步过强。产品五档实测（同帧离线、加密 bundle、不下发 blur_type）：
    //     档位  25      50      75      100
    //     改动  0.010   0.402   1.122   1.908     ← 凸曲线，低档几乎不动
    // 我方旧映射（T=8.3）：0.459 / 1.120 / 1.956 / 1.956 —— 低档强 46 倍、
    // 高段压死。归一化后产品的强度占比是 0.005/0.211/0.588/1.0，所以把
    // 强度项改成**按档位查表分段线性**，锚点直接取产品反解值。
    // T 不随档位变：100 档我方 flat/tex = 1.08 而产品 1.06，选择性本来
    // 就对得很齐（8 帧那次的 1.05 vs 1.39 是分类器口径不同造成的误判）。
    // 表可在运行时被 BEAUTY_S3_LV_I / BEAUTY_S3_LV_T 覆盖（离线扫参用）。
    int   lvTable = 1;
    float lvI[5] = {0.000f, 0.020f, 0.240f, 0.577f, 0.976f};
    // 1.0.0.1：低档段非均匀锚点表。数值来自 8 帧产品真值的 I→chg 曲线反解
    // （05_验证/goldens/masks/shape_inverse_20261106.md §3），25/30/40 档分别
    // 为 0.080566 / 0.116538 / 0.146446；50/75/100 档沿用旧表的 0.240/0.577/0.976，
    // 且 0.50→0.75、0.75→1.00 两段斜率与旧表一致，因此三档输出逐字节不变。
    // lvShape=0 回退到旧五锚点表，供 A/B 与历史报告复现。
    int   lvShape = 1;
    float lvI7[7] = {0.000f, 0.080566f, 0.116538f, 0.146446f,
                     0.240f, 0.577f, 0.976f};
    // 3.1.19：T 由 8.3 → 6.5。T 是唯一能改「平坦/纹理相对强度」的旋钮
    // （I 与 e 只等比缩放）：8.3 时平坦/纹理比 1.09，产品是 1.39。T 降到
    // 6.5 把拐点前移，代价是总量掉 15%，由 e 补回 —— 见下。
    float lvT[5] = {6.5f, 6.5f, 6.5f, 6.5f, 6.5f};
    // evenfactor 也按档位查表。
    // 为什么把 e 从 I 上摘下来：旧式 e 由 I 决定，I<0.6 的档位 e 恒为 0.3，
    // 于是低档只磨平坦区、纹理几乎不动（同帧实测 50 档 flat/tex = 2.17）；
    // 而产品 50 档是 0.96（纹理与平坦一起磨）。e 固定后我方变为
    // 1.18/1.08/1.08，与产品的 0.96/1.11/1.06 同量级。
    // 3.1.19：0.70 → 0.95，与 T=6.5 配对。e 控制「向 B2 混合」的量，也就是
    // 低频压平（平坦区的主要改动来源）；T 压掉纹理后用它把总量补回 1.91。
    float lvE[5] = {0.95f, 0.95f, 0.95f, 0.95f, 0.95f};

    // ---- 清晰（clarity）：大半径局部对比 ----
    // 面板「清晰」100 档线性映射到 0..clarityMax。
    // 上限取 0.5 而不是 1.0：gain=1 时明暗差被原样翻倍，脸会显得像 HDR 过曝。
    // 0.30 是离线扫参的结果：面板 25/50/75/100 对应中频 100.2/101.1/103.0/104.7，
    // 大幅度带 99.7~100.0（不涨 = 边缘没被加亮）。
    float clarityMax = 0.30f;
    // 盒式半径 → (2r+1) 像素窗口。12 = 25px，大于磨皮核（≤8px）才叫「层次」。
    int clarityRadius = 12;
    // ---- 异步检测 ----
    // 1 = 检测跑在 worker 线程（默认），0 = 老的同线程同步检测。
    // 关掉它只为离线对拍：异步会让「第几帧用哪份掩码」依赖线程调度，
    // 逐字节哈希的测试会不稳定。
    bool asyncDetect = true;
    // 1.0.13.8：掩码对齐的「画面没动」阈值（平均绝对差，灰阶）。
    // 0 = 永远对齐（3.1.10 的旧行为）；越大越容易对齐。
    // 默认 4：相机噪声静止时约 1~2，1°/帧 的旋转约 5.4，取中间。
    // BEAUTY_ALIGN_DIFF 可覆盖（0~64）。
    float alignDiff = 4.0f;
    // 异步路径的提交周期（帧）。0 = 每帧都提交。
    //
    // 为什么异步路径要每帧、而同步路径仍然是每 4 帧（见 kMaskEverySync）：
    //   · 异步时检测在 worker 上，渲染线程一分钱不花，只多烧一个核的一部分 ——
    //     20 核机器上 14.1ms/33.3ms ≈ 42% 单核，整机 +1.7 个百分点；
    //   · 同步时检测压在渲染线程上，每帧跑就是每帧 +14ms，那是掉帧，不是省不省的问题。
    // 3.1.8 之前两条路共用 4 帧，真机表现为「掩码拖在脸后面」：
    // 提交周期 5 帧 = 167ms，滞后从 1 帧锯齿漂到 5 帧，而掩码边界是脸框硬切边，
    // 拖影非常显眼。实测 YuNet 只要 14.1ms，慢的从来不是推理，是节流。
    int maskEveryAsync = 0;
    // 软膝：|mid| ≤ lo 全增益，≥ hi 完全不加。
    // 8/22 是扫出来的：软膝放到 20/45 时大幅度带会涨到 105.9（= 边缘被加亮，
    // 也就是光晕）。收到 8/22 后稳定在 100.0 以内，边缘平均改动只有 0.26 灰阶。
    float clarityKneeLo = 8.0f;
    float clarityKneeHi = 22.0f;

    // ---- 细节回填（锐化 / 全局锐化）----
    // 中频带增益基准，与参考实现路径的 kMidGain 取同一个值（legacy_engine.cpp）。
    // 这样「锐化 50」在我们的引擎里和在参考实现里指的是同一条曲线：细频带 100% 回填、
    // 中频带推到原图的 1.65 倍。数值对照见 04_文档/C11_锐化与全局锐化.md。
    float detailMidGain = 3.30f;
    // 细频带软阈值：幅值低于它的高频直接不回填。相机噪点与毛孔在幅值上重叠
    // （±2~6 vs 2~8），只能从最细的一端削掉一点；3.0 是「削噪但不动毛孔」的
    // 折中值，靠 BEAUTY_DETAIL_THR 可现场改。
    float detailThrFine = 3.0f;
    // 3.1.35：磨皮=0 时的「纯锐化」参数（脸内锐化专用，与磨皮>0 的回填路径隔离）。
    // 磨皮>0 时脸内锐化是「回填被磨掉的高频」：dst 已失高频，加回 src 高频 =
    // 把高频补回原值量级，增益走 detailMidGain 那条曲线（沿用历史值，不动）。
    // 磨皮=0 时 dst≈src，语义变成「纯锐化增强」，机制上有两个坑：
    //   (1) 中频带(mid)在磨皮=0 时会对全脸皮肤产生一份固定基底偏移
    //       （实测 100 档 chg 2.74、且 25 档就已有 0.62 的与档位无关的基底），
    //       所以纯锐化模式**关掉中频带**（mid=0），只留细频带。
    //   (2) 细频带默认 thrFine=3.0 的软阈值会把磨皮=0 时幅度本就很小的高频
    //       几乎全削掉（实测纯细频+默认阈值时 100 档 chg 仅 0.078、dret 1.05，
    //       等于没锐化），所以纯锐化模式把阈值放开到 faceSharpThrFine（默认 0）。
    // 放开后细频带才能产生 SDK 原生锐化那种「细节翻倍」的观感（dret→1.6+）。
    // 离线用 BEAUTY_FACE_SHARP_GAIN / BEAUTY_FACE_SHARP_THR 扫参，生产初值 1.0 / 0.0。
    float faceSharpGain = 1.0f;
    float faceSharpThrFine = 0.0f;

    // ---- 全局锐化自己的旋钮（3.1.22 新增，从 detailMidGain / detailThrFine 拆出）----
    // 为什么拆：原来全局锐化与脸内锐化共用同一条中频曲线与同一个细频阈值，
    // 改一个就会动到另一个 —— 两边的档位语义根本不同，没法各自标定。
    // 参照路径（legacy_engine.cpp 的 applySharpen）里它们本来就是两条独立曲线：
    //     脸内：  am = 锐化/100,          gm = min(锐化/100 × kMidGain, 3.0)
    //     掩码外：aG = 全局锐化/100,     gG = min(全局锐化/100 × kMidGain, 3.0)
    // 拆开后全局这一路就能单独扫参（见 06_离线验证/全项对齐_20261030/
    // sweep_gsharpen.json）。
    float globalMidGain = 3.30f;    // 全局锐化的中频带基准增益（参照 kMidGain）
    float globalFineGain = 1.00f;   // 全局锐化的细频带基准增益（面板 100 = 全额回填）
    // 全局锐化的细频软阈值。生产值 2.00（3.1.22 扫参定档）：
    //   阈值 3.0 → 25 档改动量 −8.1%、100 档 dret 2.478
    //   阈值 2.0 → 25 档改动量 −7.5%、100 档 dret 2.494（参照 2.837）
    //   阈值 1.0 → 25 档改动量 −6.2%、但 100 档改动量 +3.1%（开始过量）
    // 阈值 0 看着 dret 最接近（2.826 vs 2.837），但改动量过 10%（4.623 vs 4.194），
    // 净效果更差 —— 说明我方的细频带本来就比参照强一点，不能再往上加。
    float globalThrFine = 2.00f;    // 全局锐化的细频软阈值（与脸内分开标定）
    float globalThrMid = 0.00f;     // 全局锐化的中频软阈值（默认不削）

    // ---- 磨皮后的「基准细频回填」（3.1.22 新增）----------------------------
    // 为什么要它：单开磨皮 100 档时我方细节保留 dret=0.734，参照=0.834 ——
    // 我方比参照多削了 12% 的高频；同时我方总改动量 2.009 还比参照 1.908 高。
    // 也就是说：我方把能量挪到了**中频**，而不是像参照那样留在低频。
    // I / e / T / gwp 四个旋钮都改不动这个形状（它们让「总量」与「细节保留」
    // 永远反向，见 06_离线验证/全项对齐_20261030/sweep_blur.json）。
    // 真正的解法是把**细频带**按比例还回来：磨皮少了多少高频，就还回去多少。
    // 这不会额外增加改动量 —— 还回去的高频本来就是原图的一部分，
    // 补得越多反而越接近原图（chg 下降）。
    // 只在「用户没开锐化、也没开清晰」时生效（开了就用用户自己的档位）。
    // 生产默认值 0.06（3.1.22 实测定档）。
    // 扫参结论（100 档 / 3 帧均值，参照 chg=1.905 / dret=0.835）：
    //   refill 0.05 → chg 1.914  rmse 1.57  dret 0.838
    //   refill 0.10 → chg 1.913  rmse 1.58  dret 0.839
    //   refill 0.15 → chg 1.913  rmse 1.58  dret 0.841
    //   refill 0.30 → chg 1.913  rmse 1.60  dret 0.850
    //   refill 0.40 → chg 1.916  rmse 1.62  dret 0.858（已超参照，RMSE 变差）
    // 0.05~0.10 是量化吸收后的平台区（dret 基本不动），0.10 起单调上升。
    // 取 0.06：落在平台区中部，dret≈0.838 贴参照 0.835，RMSE 1.57 优于基线 1.58。
    float blurRefill = 0.06f;
    // 回填只在磨皮强度 ≥ 这个值时启用（I 是查表强度，0/25/50/75/100 档
    // 对应 0.00/0.08/0.24/0.58/0.98）。0.3 大致落在 50 与 75 档之间。
    float blurRefillMinI = 0.3f;
    // 1 = 用 delta 模式（加回「原图细频 − dst 细频」）。默认 0，
    // 见 wantBlurRefill 处的实测对比。
    int blurRefillDelta = 0;
    // 基准回填专用的细频软阈值（灰阶）。比锐化那套（3.0）低得多：
    // 磨皮要还的就是「小幅值细频」，锐化要防的却是「噪点被放大」，
    // 两者的取舍正好相反，所以不能共用一个阈值。
    float blurRefillThr = 0.8f;

    // ---- 细节层时序 EMA（0.7.2）----
    // 锐化会把相机白噪一起放大，而噪点帧间独立 → 静止的脸呈「沸腾」式闪动。
    // 把算高通用的亮度平面做一次运动自适应 EMA：静止强平滑、头一动立刻放开。
    // 常量照抄参考实现侧已标定过的一组（legacy_engine.cpp 的 kDetailBetaStill 等）：
    // 静止 beta 0.20（噪声 ×0.38），运动判据 0.15/0.40 对应 rawChg 0.79/1.44。
    //
    // 我们的运动判据换成「全帧亮度帧间差均值（4×4 抽样，单位=灰阶）」，比 参考实现的
    // rawChg 更直接：相机静止 + 传感器噪声实测在 1~3 之间，真人头动在 8 以上。
    // 阈值 2.5 / 8.0 是这两段之间取的空隙，两侧都有余量。
    bool  emaOn = true;
    float emaStill = 2.5f;       // 帧间差 <= 它 → 按静止（强平滑）
    float emaFull = 8.0f;        // 帧间差 >= 它 → 完全不平滑（零拖影）
    float emaBetaStill = 0.20f;  // 静止时新帧的权重

    // ---- 人脸局部五项（五官立体 / 亮眼 / 去黑眼圈 / 去法令纹 / 祛斑痘）----
    // 增益单位是「灰阶」：面板拉满时椭圆中心处的亮度增量（可用负值=压暗）。
    // 每个值都是先量参考实现再定的 —— 用 ref_golden.dll 把该项单独拉满、与该项为 0
    // 的输出相减，取连通域的峰值。所以这些数字是「对齐观感」而不是猜的：
    //     五官立体 峰值 +7.3 / -4.7    亮眼 峰值 +44（眼白本就接近饱和）
    //     去黑眼圈 峰值 +7.7           去法令纹 峰值 +3.3
    // 数据与差分图见 06_离线验证/goldens/_probe/ 与 04_文档/C12_人脸局部五项.md
    // 上面那组是**峰值**，直接当增益用会过头 —— 峰值是连通域里最亮的几个点，
    // 而椭圆中心一大片都会拿到满增益。下面这版是按「脸内 dY 均值 + p95」对拍
    // 回调过的（core vs 参考实现：立体 +2.97/+6.0 → 目标 +0.64/+5.1，依此类推）。
    // ---- 五官局部三项：3.1.22 按参照差分图重建后的旋钮 --------------------
    //
    // 【亮眼】参照在这批素材上几乎不动（峰值 < 1 灰阶），保持原样不动它。
    float regEyeGain = 12.0f;
    //
    // 【五官立体】= 8 个锚在关键点上的宽椭圆（见 applyFaceRegions 的 threed 表）。
    // 三条关键结论（都是实测出来的，不是猜的）：
    //   1. 参照的立体是**解剖/网格驱动**的：额头恒亮、脖子恒暗，与画面自身
    //      明暗无关。之前用「低频明暗场」路线实测 corr≈0.05（头发/背景污染），
    //      已废弃。
    //   2. 参照的**面部中线 = 双眼中点**，不是 YuNet 的鼻尖 —— 侧脸时鼻尖
    //      会偏 0.12 脸宽，参照的中线不偏。所有中线特征（鼻梁/鼻底/额头）
    //      都锚在 midX/midY 上。
    //   3. 增益分「亮部 / 暗部」两组 feather（亮部 0.705 平台大、暗部 0.498），
    //      因为参照的提亮区是大片平顶、压暗区是窄带。
    //   regThreedGain : 整体比例因子（离线对拍用）。
    float regThreedGain = 1.0f;
    // 【去黑眼圈】参照：两个小块在眼下方，峰值 17.3~18.5，**与暗度无关**
    //   （corr(原亮度, Δ) ≈ +0.1），是纯几何区域 → 双层椭圆（亮核 + 淡晕）。
    //   转头时近侧眼袋在画面上被拉宽 → 用 yaw（鼻尖相对眼中点的偏移）做
    //   透视缩短修正，rx *= 1 − regPouchYawK·yaw·side。
    float regPouchYawK = 1.5611f;     // 3.1.23 重新拟合值（原 2.0）
    float regPouchScale = 1.0f;      // 黑眼圈双层椭圆的整体增益比例
    // 【去法令纹】参照：峰值恒为 **+52**（封顶），且 corr(原亮度, Δ) = −0.4
    //   → 它不是「固定形状 + 固定亮度」，而是**把暗线填平到周围皮肤亮度**：
    //   Δ = min(maxLift, slope·max(0, LR − Y))，LR = 邻域最大亮度。
    //   3.1.23：加**暗线闸门**（gateLo/gateHi）把响应收窄到褶皱线上；
    //   限制因子在 applyFoldRemoval 内部改成 max(皮肤掩码, 区域权重)。
    //   3.1.23 第二轮（双瓣模型 naso6，8 帧统一拟合 fit_naso6.json）：
    //   上瓣参数整体收紧（k 0.60→0.45、闸门 8.5/15.0→19.2/29.9、
    //   LR 半径 6→4、封顶 60→57.5）—— 旧值让上瓣过冲到封顶，
    //   而参照的峰只有 48。
    float regNasoSlope = 0.4500f;    // 每 1 灰阶的「暗差」提亮多少（3.1.23 双瓣重拟合）
    float regNasoMaxLift = 57.5000f; // 封顶（双瓣拟合值；参照实测峰值 51~52）
    int regNasoLrRadius = 4;         // LR = 半径 4 的邻域最大亮度（双瓣拟合值）
    float regNasoGateLo = 19.1526f;   // 暗差 < gateLo → 不起作用
    float regNasoGateHi = 29.8535f;   // 暗差 > gateHi → 完全起作用
    // 祛斑痘：拉回量 = k × 偏离局部均值的幅度。0.25 是拿「参考实现的 dY p5/p95
    // = -3.6/+3.5」反推的；0.55 时 core 是 -11/+7，暗斑被打得太狠，痘印会
    // 变成一块块发亮的补丁。再大就会把毛孔一起抹平（那成了第二次磨皮）。
    float regSpotK = 0.25f;
    int regSpotRadius = 2;          // 5×5 窗口。2~4 是斑点尺度，再大就吃到结构
    float regSpotThrLo = 1.4f;      // 小于它算皮肤细纹理，不动
    float regSpotThrHi = 30.0f;     // 大于它算真边缘（睫毛/鼻孔/唇线），不动

    // ---- 人脸框时序平滑（1.0.0.2；按用户裁定撤销 §7「不做人脸框 EMA」）----
    // 遮住半边脸时 YuNet 仍会给出框，但中心与大小会跳，掩码跟着跳。
    // faceEma = 0 且 faceHold = 0 时整段不执行，逐字节回到 1.0.0.1。
    // ⚠️ 默认开启会引入帧间状态，破坏逐字节确定性；所有历史 golden 基线
    // 必须显式加 BEAUTY_FACE_EMA=0 才能复现，见 docs/CHANGELOG.md §2。
    float faceEma = 0.35f;
    // 遮挡迟滞：新框面积骤变或与历史框 IoU 过低时，最多沿用历史框多少帧。
    // 0 = 只做 EMA，不做迟滞。
    int   faceHold = 6;
    float faceHoldAreaRatio = 0.65f;   // 面积比低于它（或高于倒数）判为跳变
    float faceHoldIoU = 0.30f;         // IoU 低于它判为跳变
};

// 关键点是否可信。
//
// 遮挡（手挡脸、口罩、低头）或大侧脸时，YuNet 仍会输出 5 个点，但位置可能
// 离谱到人脸框外面。直接用它们画五官保护区，椭圆会跑到画面别处，把不该保护
// 的地方保护掉（或者该保护的没保护）。
// 判据：五个点都必须落在人脸框外扩 50% 的范围里 —— 正常侧脸也就贴边，
// 超出这个范围说明这组关键点不可信，宁可这次不做五官保护。
static bool kpsSane(const beautycore::FaceBox& f) {
    if (!f.hasKps) return false;
    const float mx0 = f.x - f.w * 0.5f, mx1 = f.x + f.w * 1.5f;
    const float my0 = f.y - f.h * 0.5f, my1 = f.y + f.h * 1.5f;
    for (int p = 0; p < 5; p++) {
        const float x = f.kps[p * 2], y = f.kps[p * 2 + 1];
        if (x < mx0 || x > mx1 || y < my0 || y > my1) return false;
    }
    return true;
}

// 在缓冲上画一个软边椭圆，权重 0..255，取较大值。
//
// 公式抄 dinjufen/lumina-beauty 的 kComposeShader（核心代码为 MIT）：
//     weight = (1 - smoothstep(0.35, 1.0, du² + dv²)) × strength
// 注意它把**平方距离**直接喂给 smoothstep（不是 sqrt），这里保持一致。
void paintProtectEllipse(unsigned char* buf, int w, int h,
                         float cx, float cy, float rx, float ry) {
    if (!buf || rx < 0.5f || ry < 0.5f) return;
    int x0 = (int)(cx - rx), x1 = (int)(cx + rx) + 1;
    int y0 = (int)(cy - ry), y1 = (int)(cy + ry) + 1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > w) x1 = w;
    if (y1 > h) y1 = h;
    const float irx = 1.0f / rx, iry = 1.0f / ry;
    for (int y = y0; y < y1; y++) {
        const float dv = (y + 0.5f - cy) * iry;
        unsigned char* row = buf + (size_t)y * w;
        for (int x = x0; x < x1; x++) {
            const float du = (x + 0.5f - cx) * irx;
            const float q = du * du + dv * dv;
            if (q >= 1.0f) continue;
            const float t = smoothStep(0.35f, 1.0f, q);
            const int v = (int)((1.0f - t) * 255.0f + 0.5f);
            if (v > (int)row[x]) row[x] = (unsigned char)v;
        }
    }
}
SmoothCfg g_cfg;

// ---------------------------------------------------------------------------
// 1.0.0.2：人脸框时序平滑与遮挡迟滞（按用户裁定撤销 §7「不做人脸框 EMA」）
//
// 用户反馈的现象是「挡住半边脸时脸部遮罩闪烁」，并说明 GPU 版同样存在。
// 归档 c21 §3.1 把闪烁归因于「检测 faces 坐标抖」，但同文档 §6 自己把这句
// 标为个人推测、未做消融验证。本轮按 B 授权直接落地，**未做真机复现**，
// 因此这里不声称「已修好」，只提供一个可回退、可逐字节验证的实现。
//
// 人脸框的时序状态已经并进紧随其后的 DetState，不再有文件级静态。
// 1.0.0.3 给它加过一把 s_faceEmaMtx，那是为了修「两个实例并发写」导致的
// 0xc0000005；锁确实挡住了崩溃，但挡不住语义错误：状态本身属于「这一路源」，
// 不属于进程。锁还有第二个副作用 —— resetFaceEmaState() 内部持锁，任何
// 「外面再套一层」的写法都会自死锁，所以它只能一路散着调用。
// 现在整份状态按 slot 存，锁自然不需要了（同一 slot 同一时刻只有一条线程）。

// ---------------------------------------------------------------------------
// 每实例（slot）独立的检测上下文
//
// 为什么要有它：`beautyEngine()` 是**进程级单例**（见文件末尾），OBS 里每个
// 「美颜」滤镜实例只是向它领一个 slot（obs-beauty.cpp 的 f->slot）。
// 1.0.13.1 把方向状态从文件级静态改成 CoreEngine 成员，只换了存储位置 ——
// 单例下仍然是一份状态，两个实例照样互相清零（05_验证/dual_instance_check.py
// 实测：异分辨率源插进来后命中率 30/30 → 1/30）。所以这里按 slot 再切一刀：
// 方向结论、掩码缓冲、检测计数各归各的实例，与 acquireSlot 的
// 「每实例一份上下文」契约对齐。
// -----------------------------------------------------------------
struct DetState {
    // ---- 输入方向 / 平面内倾斜 ----
    // effRot 本帧**实际使用**的方向（0/90/180/270）；rotManual 是用户用
    // BEAUTY_INPUT_ROT 手工声明的方向（非 0 时不做自动探测）。
    // effRoll ∈ {-45, 0, +45}，本帧检测角 = effRot + effRoll。
    // 方向与倾斜的探测计数器**分开**两套：倾斜要反应快（默认 8 次），方向
    // 可以慢（默认 20 次），混用会让彼此的节奏互相带偏。
    int   effRot = 0;
    int   rotManual = 0;
    int   autoMiss = 0;
    int   autoCool = 0;
    bool  autoProbeLogged = false;
    bool  rotFallbackLogged = false;
    int   rotLastW = 0, rotLastH = 0;   // 帧尺寸变了就把方向结论重来
    float effRoll = 0.0f;
    int   rollMiss = 0;
    int   rollCool = 0;
    bool  rollProbeLogged = false;
    // 1.0.13.9：距上一次「0° 对照」过了多少帧。只在 roll≠0 且本帧检测正常时累加，
    // 到 g_cfg.rollCheckFrames 就跑一次对照，判断该不该把 roll 放回 0。
    int   rollCheck = 0;
    int   rollReleaseLog = 0;      // 释放次数，用于日志去重（只记前几次）

    // ---- 掩码与检测结果 ----
    std::vector<unsigned char> mask;
    std::vector<unsigned char> protect;   // 五官保护区（眼睛/嘴巴），0..255
    // 本帧检出的人脸（含 5 个关键点）。五官局部五项全靠它定位；
    // 与掩码同一生命周期（异步时由 worker 一起交回），所以不会出现
    // 「掩码是这一帧的、关键点是上一帧的」这种错配。
    std::vector<beautycore::FaceBox> faces;
    beautycore::RoiRect bounds;    // 掩码包围盒（外扩 radius），随掩码一起更新
    bool  maskValid = false;
    // 3.1.21：本次「启用以来」是否成功产出过掩码。只看第一次 —— 用它区分
    // 「刚开开关、检测还没回来」（这几帧透传）和「人不在画面里」（全帧兜底）。
    bool  everHadMask = false;
    int   maskAge = 999;
    int   maskHold = 0;            // 连续丢检次数（用于沿用旧掩码）
    std::vector<unsigned char> heldFrame;   // 与 mask 同源的原始帧（RGBA）
    bool  maskFresh = false;       // 本帧刚收到一份新的有效结果

    // ---- 细节层时序 EMA（0.7.2）----
    // 这一组是**有记忆**的状态，必须按实例分开：两个源交替时如果共用，
    // 帧序号会被对方推进（frameNo 一跳，detailEmaGen + 1 != frameNo 立刻
    // 成立），于是每次交替都判成「断帧 → 重置历史」，画面表现为细节层
    // 反复从零起步 —— 观感是锐度/细节层在两个源之间来回跳。
    std::vector<unsigned char> motionPrev;  // 1/4 分辨率的亮度快照
    bool     motionHave = false;
    std::vector<unsigned char> detailLumT;  // 全帧亮度历史，喂 detailRefill 做 EMA
    bool     detailEmaReset = true;
    uint64_t frameNo = 0;
    uint64_t detailEmaGen = 0;              // 0 = 从未写过

    // ---- 人脸框时序 EMA / 迟滞（1.0.0.2）----
    // 这一组同样是「有记忆」的：上一帧的框决定这一帧的平滑量与迟滞判定。
    // 之前是文件级静态 + s_faceEmaMtx，1.0.0.3 加锁只解决了「并发写」，
    // 解决不了「语义上不属于同一路源」—— B 实例一帧没检出脸就把 valid 置 false，
    // A 实例下一帧只能「直接采纳」，平滑量与迟滞全丢，掩码随之整体偏一点。
    // 实测（05_验证/_tmp_ab_ema2 的判据）：A 的同一帧在「只跑 A」与「A/B 交替」
    // 下最大差 22 灰阶、350 万像素不一致 —— 就是这一组造成的。
    std::vector<beautycore::FaceBox> faceEmaPrev;
    bool faceEmaValid = false;
    int  faceHoldLeft = 0;
    // 1.0.13.6：连续丢检帧数。与 faceHoldLeft 分开记 —— 后者是「检到了但
    // 跳变太大，暂时不采信」的计数，两者语义不同，混用会让 hold 在恢复时
    // 立刻用光。只在 smoothFaceBoxes 里读写。
    int  faceMiss = 0;

    // ---- 几何过渡（1.0.13.7）----
    // roll 从 0 切到 ±45（或反向）时，交给下游的几何会在**一帧之内**整个换掉：
    // 关键点从「塌成水平」恢复成真正倾斜的，于是 beauty_warp 的 phi 从 0° 跳到
    // 45°，fw/fh 也从外接盒尺寸变成紧框尺寸（实测 108×116 → 107×142）。形变
    // 方向转 45°、幅度再变 22%，一帧之内发生 —— 观感就是「闪一下」。
    //
    // 这一组让那次切换跨 kGeoFadeFrames 帧插值过去：起点是切换前那一帧真正交给
    // 下游的框（geoFrom），终点是新算出来的框，中间帧按 t 线性混合。roll 非 0 时
    // 盒的 w/h 必须由 rw/rh 与 roll 重新算外接矩形，否则掩码（按 rw/rh + roll 画
    // 倾斜矩形）和 ROI 会互相错位。
    std::vector<beautycore::FaceBox> geoFrom;
    int geoFadeLeft = 0;           // 0 = 不在过渡中
    // 上一次真正交给下游的那组框。**不能用 DetState::faces 代替**：那个字段是
    // 异步链路里由渲染线程 swap 进来的（collectAsync），worker 在检测阶段读到
    // 的时序不确定 —— 实测首次滚转锁定的那一刻它是空的，过渡根本没起来。
    // 这份由 buildMaskInto 自己在交出去之前写，时序确定。
    std::vector<beautycore::FaceBox> geoLast;

    // ---- 诊断（lastFaces / lastRoi / lastErr / lastCoreMs 读它）----
    int   lastFaces = 0;
    // 1.0.13.4：本 slot 主检测那一次的最高置信度（不受 conf 阈值影响）。
    // 原先直接读 FaceDetector::lastBestScore()，但检测器是共用的 —— 读到的可能
    // 是另一路刚刚跑完的值，于是日志里「best=0.412」根本不属于这一路，调阈值
    // 时被它带偏。改由 detect() 的 out 参数交回，落在这里，只写本 slot。
    float detBest = 0.0f;
    int   maskPixels = 0;
    std::string faceErr;
    double lastMs = 0.0;
    // 1.0.9.0：分段耗时（ms）。0=掩码/检测 1=磨皮 2=色调 3=细节 4=美形+A通道 5=保留
    double st[6] = {0, 0, 0, 0, 0, 0};
};

// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 1.0.3.0：输入方向（从 GPU 版 2.13.1 / 3.2.0 移植）
//
// 1.0.13.1 之前这些状态是文件级静态，理由是「只做方向这一件无副作用的事，不涉及
// 跨实例坐标，故不需要加锁」。该理由不成立，现已改为 CoreEngine 的实例成员
// （声明见类内 effRot_ 一组）：
//   · 方向结论属于「这一路源」，不属于进程。720p 摄像头与 1080p 图像源各挂一个
//     滤镜时，两个实例共用 rotLastW_/rotLastH_，彼此的尺寸差异会把对方的方向与
//     倾斜结论反复作废 —— 自动探测永远收敛不了，两个实例还会互相套用对方的角度；
//   · ensureReady() 是按实例跑的，B 实例初始化会把 A 实例已收敛的方向清掉；
//   · 非原子 int/float 跨线程读写本身就是 C++ 未定义行为；而这里又**不能**套
//     s_faceEmaMtx —— resetFaceEmaState() 内部已持该锁，套上即自死锁。
// 改为成员后与 face_ / faces_ 走同一套并发约定：同一实例同一时刻只有一条线程在
// 跑 buildMaskInto（由 asyncOn_ 路由），多实例之间互不可见。
// 本文件其余部分仍按旧名引用，对应关系：effRot_→effRot_、effRoll_→effRoll_ …
// ---------------------------------------------------------------------------

// 旋转后坐标 → 源坐标。与 beauty_face.cpp 的 letterboxRgbRot 严格互逆：
// 那边用同一组向量式把源图采样成「旋转后整图」，这里把检测出的点搬回源坐标。
static void invRotatePoint(float px, float py, float rot, float Wr, float Hr,
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
        // 1.0.5.0：一般式。与 beauty_face.cpp 的 letterboxRgbRot 同一组式子，
        // 在 0/90/180/270 上与上面的 switch 逐位相同（cos90=0/ sin90=1 等）。
        const float th = rot * 3.14159265358979323846f / 180.0f;
        const float ct = cosf(th), st = sinf(th);
        rx = dx * ct + dy * st;
        ry = -dx * st + dy * ct;
    }
    ox = rx + csx;
    oy = ry + csy;
}

// 对整个 FaceBox（中心 + 关键点）做反变换。
//   90 的整数倍：宽高互换（1.0.3.0 的老口径，逐位不变）
//   任意角度（1.0.5.0，头歪补偿）：把检测框的 4 个角搬回源坐标后取外接矩形。
//   倾斜的框本来就是斜的，轴对齐外接矩形才是它该占的范围。
// (Wr,Hr) 是**旋转后整图**的宽高（由 beautycore::rotCanvasSize 给出），
// (Ws,Hs) 是源帧宽高。
static void invRotateFace(beautycore::FaceBox& f, float rot, float Wr, float Hr,
                          float Ws, float Hs) {
    if (rot == 0.0f) return;
    const int qi = (int)lroundf(rot);
    const bool axis = (fabsf(rot - (float)qi) < 0.01f) && ((qi % 90) == 0);
    if (!axis) {
        // 1.0.5.0：外接矩形会把斜框的面积放大 (cos+sin)² 倍（45° 时 2.8 倍）。
        // 把脸自身的宽高与倾角一并记下来，下游掩码按倾斜矩形画，别按外接盒画。
        f.roll = rot;
        f.rw = f.w;
        f.rh = f.h;
        // 任意角度的紧框 rw × rh 本来就是脸的宽高，下游不再按 srcRot 互换。
        f.srcRot = 0;
        const float cx[4] = {f.x, f.x + f.w, f.x + f.w, f.x};
        const float cy[4] = {f.y, f.y, f.y + f.h, f.y + f.h};
        float x0 = 1e30f, y0 = 1e30f, x1 = -1e30f, y1 = -1e30f;
        for (int i = 0; i < 4; i++) {
            float nx = 0.0f, ny = 0.0f;
            invRotatePoint(cx[i], cy[i], rot, Wr, Hr, Ws, Hs, nx, ny);
            if (nx < x0) x0 = nx;
            if (nx > x1) x1 = nx;
            if (ny < y0) y0 = ny;
            if (ny > y1) y1 = ny;
        }
        f.x = x0;
        f.y = y0;
        f.w = x1 - x0;
        f.h = y1 - y0;
        for (int k = 0; k < 10; k += 2) {
            float nx = 0.0f, ny = 0.0f;
            invRotatePoint(f.kps[k], f.kps[k + 1], rot, Wr, Hr, Ws, Hs, nx, ny);
            f.kps[k] = nx;
            f.kps[k + 1] = ny;
        }
        return;
    }
    f.roll = 0.0f;      // 90 的整数倍：框本身轴对齐，无需倾斜几何
    // 1.0.13.6：把「盒宽高是否已被对调」这个离散事实带下去（下一行真要换，
    // 记号与换的动作必须在同一处）。180° 只转半圈，宽高不变，记 0。
    f.srcRot = (qi % 180 == 0) ? 0 : 90;
    const float cx0 = f.x + f.w * 0.5f, cy0 = f.y + f.h * 0.5f;
    float ncx = 0.0f, ncy = 0.0f;
    invRotatePoint(cx0, cy0, rot, Wr, Hr, Ws, Hs, ncx, ncy);
    if (qi == 90 || qi == 270) { const float t = f.w; f.w = f.h; f.h = t; }
    f.x = ncx - f.w * 0.5f;
    f.y = ncy - f.h * 0.5f;
    for (int k = 0; k < 10; k += 2) {
        float nx = 0.0f, ny = 0.0f;
        invRotatePoint(f.kps[k], f.kps[k + 1], rot, Wr, Hr, Ws, Hs, nx, ny);
        f.kps[k] = nx;
        f.kps[k + 1] = ny;
    }
}

/* 1.0.5.0（头歪补偿）：倾斜探测候选框的「像不像人脸」判据。
 *
 * 为什么必须有这道门槛：探测的两个候选 ±45° 里，与真实倾斜**同向**的那个能把脸
 * 摆正，**反向**那个会把倾斜累加到接近 90°（侧躺）—— YuNet 在那里吐出来的不是
 * 脸，而是画面里某块像脸的纹理。2026-11-09 实测（05_验证/ab20261109_head_roll.md）：
 *
 *     真框    score 0.886~0.920   双眼间距/长边 0.332~0.370
 *     敷衍框  score 0.759        双眼间距/长边 0.216   ← 45° 歪头、方向没修正时
 *     假框    score 0.661~0.690  双眼间距/长边 0.078~0.103
 *
 * 「敷衍框」这一档是新发现的：框在那儿、分数也不算低，但双眼被挤到框宽 28%，
 * 说明框是撑大的，掩码照样糊错地方。下限取 0.25（真框最低 0.332，假框最高
 * 0.216），两边各留 25% 余量。
 *
 * 判据全部在**旋转后坐标系**里算：检测框在那里恒为正立，与 0° 检测同口径。
 *   · score ≥ 0.75          —— 假框最高只到 0.69
 *   · 双眼间距/框较长边 ∈ [0.25, 0.62] —— 假框 ≤ 0.103，敷衍框 0.216，真框 ≥ 0.332
 *   · 眼睛在嘴上面           —— 正立脸的必然关系，假框偶尔会反过来
 */
static bool rollBoxPlausible(const beautycore::FaceBox& f) {
    if (f.score < 0.75f) return false;
    if (!f.hasKps) return false;
    const float dx = f.kps[2] - f.kps[0];
    const float dy = f.kps[3] - f.kps[1];
    const float ew = sqrtf(dx * dx + dy * dy);
    const float mx = (f.w > f.h) ? f.w : f.h;
    if (mx <= 0.0f) return false;
    const float r = ew / mx;
    if (r < 0.25f || r > 0.62f) return false;
    const float eyeY = 0.5f * (f.kps[1] + f.kps[3]);
    const float mouthY = 0.5f * (f.kps[7] + f.kps[9]);
    if (eyeY >= mouthY) return false;
    return true;
}

static float faceBoxIoU(const beautycore::FaceBox& a,
                        const beautycore::FaceBox& b) {
    const float ix0 = (a.x > b.x) ? a.x : b.x;
    const float iy0 = (a.y > b.y) ? a.y : b.y;
    const float ax1 = a.x + a.w, ay1 = a.y + a.h;
    const float bx1 = b.x + b.w, by1 = b.y + b.h;
    const float ix1 = (ax1 < bx1) ? ax1 : bx1;
    const float iy1 = (ay1 < by1) ? ay1 : by1;
    const float iw = ix1 - ix0, ih = iy1 - iy0;
    if (iw <= 0.0f || ih <= 0.0f) return 0.0f;
    const float inter = iw * ih;
    const float uni = a.w * a.h + b.w * b.h - inter;
    return (uni > 0.0f) ? inter / uni : 0.0f;
}

// 就地平滑 faces。detect 之后、画掩码与交出 fboxOut 之前调用，
// 使肤色掩码、五官保护区、五官局部五项拿到的是同一组框。
// w/h 是当前帧分辨率：用于跨分辨率防线（1.0.0.3，见上方状态定义处说明）。
// 1.0.13.6：丢检多少帧以内仍保留人脸框历史（超过就认为人真的离开 / 换镜头）。
//
// 取 15 帧 ≈ 0.25 s @60fps：要盖住「头歪到 45° 时 YuNet 连续丢检、等 roll 探测
// 接手」的整个窗口（g_cfg.rollMiss 默认 4，最坏 8 帧也在此范围内），又短到
// 人物真离开时不会把磨皮糊在背景上太久。掩码侧的保持由 kMaskHold 单独管。
static const int kEmaResyncMiss = 15;

// 1.0.13.7：几何切换的过渡帧数。6 帧 = 0.2 s @30fps / 0.1 s @60fps ——
// 够长到人眼跟不上（每帧只走 1/5 步），又短到「歪头到位」后不会一直发虚。
static const int kGeoFadeFrames = 6;

static void smoothFaceBoxes(DetState& S, std::vector<beautycore::FaceBox>& faces,
                            int w, int h) {
    const float alpha = g_cfg.faceEma;
    const int   hold  = g_cfg.faceHold;
    // 回退口径：两个开关都关时既不读也不写状态，也不动 faces，
    // 输出与 1.0.0.1 逐字节一致。
    if (alpha <= 0.0f && hold <= 0) return;
    // 1.0.13.7：几何过渡期间不叠 EMA。
    //
    // 理由：这 N 帧的框本来就在按刻意设计的轨迹从旧几何挪到新几何，再叠一层
    // 「跟上一帧比跳不跳」的迟滞只会把它拽住（旧历史还是切换前的坐标系）；
    // EMA 也会把插值结果写进 faceEmaPrev，过渡一结束就又开始往回拉。
    // 这段时间的平滑由 applyGeoFade 自己负责，它结束时会把 faceEmaPrev 对齐。
    if (S.geoFadeLeft > 0) return;
    // 本帧是不是「丢检之后恢复」的第一帧 —— 它要的是平滑，不是 hold。
    const bool resync = (S.faceMiss > 0);
    if (faces.empty()) {
        // 1.0.13.6：丢脸不再当场把 EMA 历史作废。
        //
        // 原做法是立刻 faceEmaValid = false，于是「检回脸」那一帧必然走「直接
        // 采纳」—— 中间一点平滑都没有。头歪到 40° 出头时 YuNet 会连续丢若干帧
        // （等 roll 探测接手），检回时框从 176×176 的外接盒塌成 107×142 的紧框：
        // 面积差 2.04 倍、倾角从 0 变 −45°，全部一帧吃下 —— 那就是用户看到的
        // 「闪一下」。现在短时间内的丢检保留历史，恢复那帧继续按 EMA 过渡；
        // 丢太久才作废，免得从一个早就不成立的位置慢慢爬回来。
        S.faceHoldLeft = 0;
        if (++S.faceMiss > kEmaResyncMiss) {
            S.faceEmaValid = false;
            S.faceEmaPrev.clear();
        }
        return;
    }
    S.faceMiss = 0;
    // 跨分辨率防线（1.0.0.3）：历史框必须大致落在当前帧内。允许 ±50% 的
    // 松弛量是给边界上的脸留余量；框宽高超过 1.5 倍帧宽/高则肯定不是本帧
    // 分辨率里检出的。不满足就整体复位 —— EMA 与迟滞都不跨越「换源/换
    // 分辨率」这个断点，1.0.0.2 在这里会把 720p 坐标原样搬进 1080p 帧
    // （或反向），下游 toneColor 越界即真机崩溃。
    for (const beautycore::FaceBox& p : S.faceEmaPrev) {
        const bool stale =
            p.x < -0.5f * w || p.y < -0.5f * h ||
            p.x + p.w > 1.5f * w || p.y + p.h > 1.5f * h ||
            p.w > 1.5f * w || p.h > 1.5f * h;
        if (stale) {
            S.faceEmaPrev = faces;      // 直接采纳，别从旧值慢慢爬
            S.faceEmaValid = true;
            S.faceHoldLeft = 0;
            return;
        }
    }
    if (!S.faceEmaValid || S.faceEmaPrev.size() != faces.size()) {
        S.faceEmaPrev = faces;      // 首帧或人数变化：直接采纳，别从旧值慢慢爬
        S.faceEmaValid = true;
        S.faceHoldLeft = 0;
        return;
    }

    const float arGate = (g_cfg.faceHoldAreaRatio > 0.05f)
        ? g_cfg.faceHoldAreaRatio : 0.05f;
    std::vector<beautycore::FaceBox> out;
    out.reserve(faces.size());
    std::vector<char> used(S.faceEmaPrev.size(), 0);
    bool anyHold = false;

    for (size_t i = 0; i < faces.size(); i++) {
        const beautycore::FaceBox& n = faces[i];
        // 按中心距离最近匹配历史框；多人脸时按数组下标匹配会错配。
        int best = -1;
        float bestD2 = 1e30f;
        const float ncx = n.x + n.w * 0.5f, ncy = n.y + n.h * 0.5f;
        for (size_t j = 0; j < S.faceEmaPrev.size(); j++) {
            if (used[j]) continue;
            const beautycore::FaceBox& p = S.faceEmaPrev[j];
            const float dx = (p.x + p.w * 0.5f) - ncx;
            const float dy = (p.y + p.h * 0.5f) - ncy;
            const float d2 = dx * dx + dy * dy;
            if (d2 < bestD2) { bestD2 = d2; best = (int)j; }
        }
        if (best < 0) { out.push_back(n); continue; }
        used[best] = 1;
        const beautycore::FaceBox& p = S.faceEmaPrev[best];
        const float areaRatio = (p.w * p.h > 0.0f)
            ? (n.w * n.h) / (p.w * p.h) : 1.0f;
        const bool jump = (areaRatio < arGate ||
                           areaRatio > 1.0f / arGate ||
                           faceBoxIoU(n, p) < g_cfg.faceHoldIoU);

        beautycore::FaceBox r = n;
        // 恢复首帧不吃 hold：hold 的用意是「疑似遮挡，先别信新框」，拿它去挡
        // 一次真实的「框被 roll 探测重新锁定」只会让旧框多撑 6 帧，形变位置
        // 错得更久。这里让它直接按 EMA 收敛。
        if (hold > 0 && jump && !resync && S.faceHoldLeft < hold) {
            r = p;                  // 疑似遮挡造成的跳变：暂不采信新框
            anyHold = true;
        } else if (alpha > 0.0f) {
            r.x = p.x + (n.x - p.x) * alpha;
            r.y = p.y + (n.y - p.y) * alpha;
            r.w = p.w + (n.w - p.w) * alpha;
            r.h = p.h + (n.h - p.h) * alpha;
            // 1.0.5.0：倾斜脸的「自身宽高」也要跟着平滑，否则外接盒是平滑的、
            // 里面的斜框在抖，掩码边缘会看见一两像素的呼吸。
            // 倾斜角**不做** EMA：它一换就 resetFaceEmaState()，历史里不会有两种角度；
            // 真要对两个角度做插值，中间量既不是前者也不是后者，掩码会瞬间转到
            // 谁都不对的方向。
            if (n.rw > 0.0f && p.rw > 0.0f) {
                r.rw = p.rw + (n.rw - p.rw) * alpha;
                r.rh = p.rh + (n.rh - p.rh) * alpha;
            }
            if (n.hasKps && p.hasKps) {
                for (int k = 0; k < 10; k++)
                    r.kps[k] = p.kps[k] + (n.kps[k] - p.kps[k]) * alpha;
                r.hasKps = true;
            } else {
                r.hasKps = n.hasKps;   // 关键点缺失时不造出混合出来的假值
            }
        }
        out.push_back(r);
    }
    S.faceHoldLeft = anyHold ? (S.faceHoldLeft + 1) : 0;
    S.faceEmaPrev = out;            // 历史存平滑后的值，标准 EMA 语义
    faces = out;
}

// 1.0.3.0：方向一变就作废人脸框的时序状态（只清本 slot 的那一份）。
//
// 为什么必须清：切方向时新框与旧框的 IoU 必然很低，迟滞分支会把新框当成
// 「遮挡造成的跳变」压掉最多 6 帧（≈0.2s），而那 6 帧用的正是**另一个方向**的
// 旧坐标 —— 掩码会先糊在错的地方再跳回来。直接采纳新框是最省事且无错的处置。
static void resetFaceEmaState(DetState& S) {
    S.faceEmaPrev.clear();
    S.faceEmaValid = false;
    S.faceHoldLeft = 0;
    S.faceMiss = 0;         // 1.0.13.6：别把「刚恢复」的标记带过方向切换
}

// ---------------------------------------------------------------------------
// 1.0.13.7：几何切换的跨帧过渡
//
// 问题：roll 在 0 与 ±45 之间切换时，交给下游的几何是**一帧之内整个换掉**的。
// 实测（face_src 每 3° 一帧从 0° 转到 57°，异步检测）：
//
//   f17 51°  roll= 0   phi=-6.3   框 116×119   meanD 1.16   单帧 50.5 ms
//   f18 54°  roll=-45  phi=+45.7  框 179×179   meanD 1.61   ← 一帧内 meanD +39%
//
// 两件事同时变：
//   · phi 从「关键点塌成水平」得到的 ~0°，跳到真正倾斜的 45.7° —— 形变方向转 45°；
//   · fw/fh 从检测框（roll=0 时是轴对齐外接盒）变成 rw/rh（紧框），108×116 → 107×142。
// 单独看每一样都不该在一帧里发生，何况两样一起。观感就是「闪一下」。
//
// 做法：把切换后的 N 帧当成一次插值 —— 起点是切换前那一帧真正交给下游的框，
// 终点是新算出来的框，中间按 t 线性混合全部几何量（中心、rw/rh、roll、关键点）。
// roll 非 0 的中间帧，盒的 w/h 必须由 rw/rh 与 roll 重算外接矩形：掩码是按
// rw/rh + roll 画倾斜矩形的，ROI 与 fw/fh 却读 w/h，两边不一致就会错位。
// ---------------------------------------------------------------------------

// 记一次「即将切换几何」。必须在 faces 已经是本帧最终结果之前调用 ——
// 起点取的是**上一帧交给下游的那一批**（DetState::faces），不是本帧的。
static void startGeoFade(DetState& S) {
    if (S.geoLast.empty()) {        // 没有可用的旧框：无处可插，直接硬切
        S.geoFrom.clear();
        S.geoFadeLeft = 0;
        return;
    }
    S.geoFrom = S.geoLast;
    S.geoFadeLeft = kGeoFadeFrames;
}

// 把 faces 从 geoFrom 线性过渡过来。就地改 faces。
static void applyGeoFade(DetState& S, std::vector<beautycore::FaceBox>& faces) {
    if (S.geoFadeLeft <= 0 || faces.empty()) return;

    const int left = S.geoFadeLeft;
    // 只在「一对一」时插值：脸数变了（人走进来 / 第二张脸出现）时两批框无法
    // 配对，硬切反而更安全 —— 硬把 A 的几何拉到 B 上会得到一张不属于任何人的脸。
    if (faces.size() != 1 || S.geoFrom.size() != 1) {
        if (--S.geoFadeLeft <= 0) S.geoFrom.clear();
        return;
    }

    // t 从 0 走到 1，steps = N，每步 1/(N-1)。left==1 时直接给终点，避免
    // 最后一帧再留一个 1/N 的硬跳。
    const float t = (left <= 1)
                        ? 1.0f
                        : 1.0f - (float)(left - 1) / (float)(kGeoFadeFrames - 1);
    S.geoFadeLeft--;

    const beautycore::FaceBox& a = S.geoFrom[0];
    beautycore::FaceBox& b = faces[0];

    if (t >= 1.0f) {                // 终点：保持检测结果原样（与无过渡逐字节一致）
        S.faceEmaPrev = faces;
        S.faceEmaValid = true;
        S.geoFrom.clear();
        return;
    }

    // 起点 a 可能是 roll==0（rw/rh 为 0，宽高在 w/h 里），也可能已经是倾斜框。
    const float arw = (a.rw > 1.0f) ? a.rw : a.w;
    const float arh = (a.rh > 1.0f) ? a.rh : a.h;
    const float brw = (b.rw > 1.0f) ? b.rw : b.w;
    const float brh = (b.rh > 1.0f) ? b.rh : b.h;
    const float acx = a.x + a.w * 0.5f, acy = a.y + a.h * 0.5f;
    const float bcx = b.x + b.w * 0.5f, bcy = b.y + b.h * 0.5f;

    const float rw   = arw + (brw - arw) * t;
    const float rh   = arh + (brh - arh) * t;
    const float roll = a.roll + (b.roll - a.roll) * t;
    const float cx   = acx + (bcx - acx) * t;
    const float cy   = acy + (bcy - acy) * t;

    // 关键点是 phi 的唯一来源（makeGeom 用眼线算角度），必须一起插 ——
    // 只插 roll 不动关键点，形变方向照样会在过渡结束时跳。
    if (a.hasKps && b.hasKps) {
        for (int k = 0; k < 10; k++)
            b.kps[k] = a.kps[k] + (b.kps[k] - a.kps[k]) * t;
    }

    const float rad = roll * (3.14159265358979323846f / 180.0f);
    const float c = fabsf(cosf(rad)), s = fabsf(sinf(rad));
    if (fabsf(roll) > 0.5f) {
        // 倾斜矩形：rw/rh 是脸自身宽高，w/h 是它的轴对齐外接矩形。
        b.roll = roll;
        b.rw = rw;
        b.rh = rh;
        b.w = rw * c + rh * s;
        b.h = rw * s + rh * c;
    } else {
        // 退回轴对齐：下游按「roll==0 ⇒ rw/rh 恒为 0」的约定读 w/h。
        b.roll = 0.0f;
        b.rw = 0.0f;
        b.rh = 0.0f;
        b.w = rw;
        b.h = rh;
    }
    b.x = cx - b.w * 0.5f;
    b.y = cy - b.h * 0.5f;

    // 过渡期间 EMA 被跳过，历史由这里负责维护，结束后才能接着平滑。
    S.faceEmaPrev = faces;
    S.faceEmaValid = true;
}

// 异步掩码的提交计数（诊断用，只增不减）。
// 为什么需要它：提交周期从 4 帧改成每帧，从「每帧毫秒」上完全看不出来 ——
// 检测跑在 worker 上，渲染线程一分钱不多花。唯一直接可测的就是「多少帧提交了几次」。
uint64_t g_maskSubmits = 0;

// 掩码↔帧对齐的计数（3.1.10，诊断用）。
// 为什么需要它：对齐有没有生效、真机上是不是常态，日志一个字都看不出来。
// ratio = alignUsed / alignTotal，30fps 下应 ≈1；worker 追不上时会掉。
uint64_t g_alignUsed = 0;
uint64_t g_alignTotal = 0;
// 1.0.13.8：因「画面在动」而主动放弃对齐的帧数。
// 与 g_alignUsed 成对看才有意义：used 是「静止、对齐有用」，rejected 是
// 「在动、故意不对齐」。两个都 0 才说明对齐根本没走过。
uint64_t g_alignRejected = 0;

// 1.0.13.8：两帧是不是「几乎同一幅画」。
//
// 用途只有一个 —— 决定这一帧要不要用「上一帧画面 + 新掩码」输出（掩码对齐）。
// 为什么不能只看 maskFresh_：对齐的收益在静止时（掩码与画面同源），代价在运动时
// （画面重复一帧）。worker 一忙一闲，maskFresh_ 就一真一假，输出便在「晚一帧」
// 与「当前帧」之间来回跳 —— 实测 1°/帧 的旋转下两者 meanD 差 5.4 灰阶。
//
// 采样：每 4 行每 4 列取 1 像素（1080p 约 13 万次比较，实测 < 0.3 ms）。
// 只比 R/G/B：OBS 的 BGRA 里 A 恒 255，不携带画面信息。
// 阈值 thr 由 BEAUTY_ALIGN_DIFF 覆盖（默认 4 灰阶）。相机噪声在静止时约 1~2，
// 1°/帧 的旋转约 5.4，4 正好卡在中间。
static bool frameNearlySame(const unsigned char* a, const unsigned char* b,
                            int w, int h, double thr) {
    if (!a || !b || w <= 0 || h <= 0) return true;
    const size_t stride = (size_t)w * 4;
    long long sum = 0;
    long long n = 0;
    for (int y = 0; y < h; y += 4) {
        const unsigned char* ra = a + (size_t)y * stride;
        const unsigned char* rb = b + (size_t)y * stride;
        for (int x = 0; x < w; x += 4) {
            const size_t i = (size_t)x * 4;
            for (int c = 0; c < 3; c++) {
                const int d = (int)ra[i + c] - (int)rb[i + c];
                sum += (d < 0) ? -d : d;
            }
            n += 3;
        }
    }
    if (n <= 0) return true;
    return (double)sum / (double)n < thr;
}

// 无脸透传帧数（3.1.40，诊断用）。
// 为什么需要它：跳过之后引擎耗时直接变 0，「变快了」既可能是跳过生效，
// 也可能是磨皮根本没跑（参数为 0 / 掩码异常）。有了这个计数，性能行里的
// noface=N 才能证明「本窗口真的有 N 帧是因为没人而跳过的」。
uint64_t g_noFaceFrames = 0;

// 掩码参数：人脸框外扩倍数。S1 对拍扫出来 IoU 峰值在 1.15
// （IoU 0.727 / 精确率 0.934 / 召回率 0.767），见 04_文档/S1_掩码对拍结论.md。
const float kFaceBoxGrow = 1.15f;

// 人脸检测的推理输入边长默认值。
//
// 必须保持 640：我们的 YuNet 2023mar ONNX 把输入声明成固定 640x640，ORT 会
// 直接拒绝其它尺寸（`Got: 320 Expected: 640`）。「降到 320 省 4 倍算力」这条
// 路在当前模型上走不通 —— 详见 beauty_face.h 里 setInputSize 的说明。
// 检测提速改走「推理多线程」而不是「降分辨率」。
const int kFaceInputDefault = 640;

// 脖子肤色通道（2026-10-28 新增）
//
// 背景：S1 当时放弃补脖子，理由是「磨皮场景下漏磨脖子比误磨背景更可接受」。
// 用户 2026-10-28 要求「对齐 OBS美颜摄像头」，而参考实现的掩码覆盖到脖子
// （face_src 上到 y≈332，只磨脸的话停在 232），所以补回来。
//
// 三条硬约束（都是 S1 已经验证过的，别放宽）：
//   * **不能放大矩形框** —— grow 到 2.2 时精确率从 0.934 掉到 0.393，
//     矩形会把背景整块框进来；
//   * 横向只能收窄：半宽取脸宽的 0.30（总宽 0.60 脸宽），比脸框窄一截，
//     这样左右两侧的背景不会被拉进来；
//   * 纵向只到脸高的 0.55，再往下就是衣服；
//   * 依然要求 isSkin —— 白衣服（R≈G≈B，不满足 R>G）和灰背景靠这条挡。
// 参数怎么定的：`06_离线验证/neck_sweep.py` 在 S1 的 8 个有效场景上扫网格，
// 以参考实现的掩码当真值（192×256 口径，与 S1 可直接比）：
//     只磨脸           IoU 0.6981
//     半宽0.30/长0.55  IoU 0.7934（初版估值）
//     半宽0.45/长0.65  IoU 0.8442  ← 峰值，取这组
//     半宽0.60/长0.75  IoU 0.7701（横向放到 1.2 倍脸宽开始框进背景）
// 曲面在峰值附近很平（0.40~0.45 × 0.55~0.75 都在 0.83 以上），不是过拟合尖点。
const float kNeckHalfW = 0.45f;   // 半宽 = 脸宽 × 0.45（总宽 0.90 脸宽，仍窄于脸框）
const float kNeckLen = 0.65f;     // 长度 = 脸高 × 0.65

// 脖子「跟随肤色」时的探索范围（3.1.20，g_maskShape 的 bit 4）
//
// 两个数都是**允许范围**而不是**裁剪位置**：边界最终落在肤色真正结束的地方
// （脖子侧面、头发、衣领），这两个数只决定「最多允许探多远」和「探不到时兜底多宽」。
//   * maxHalf 0.70 脸宽：比旧矩形（0.45）宽，用于覆盖真实脖子的完整宽度；
//     仍设上限是因为肤色背景（v_skinbg 场景）会把掩码拉爆，S1 已验证放大矩形
//     精确率会掉到 0.393。
//   * minHalf 0.30 脸宽：肤色被阴影/胡须/镜框打断时的兜底，避免掩码被切碎。
const float kNeckSkinMaxHalf = 0.70f;
const float kNeckSkinMinHalf = 0.30f;

// 掩码边界羽化（3.1.9，修「硬边拖影」；3.1.10 收窄 + 依赖帧对齐）
//
// 问题：异步检测最快也有 1 帧滞后（33ms，worker 忙时会到 2 帧）。肤色那层本来
// 就是软边，但**人脸框是硬裁**（下面 buildMaskInto 直接截 x0..x1 / y0..y1），
// 头部一动，脸后就会留下一条硬边——观感上就是「拖影」。
//
// 做法：在框边缘 F 像素内把权重平滑降到 0。F 是 smoothstep 而不是线性 ——
// 线性斜坡在两端有折角（一阶不连续），大脸近距离看能看到一条「淡等值线」；
// smoothstep 两端导数为 0，看不到折点。
//
// **羽化治不了滞后本身**：滞后 33ms 时边界每帧都在脸后扫动，羽化只是把"硬边扫过"
// 变成"软边扫过"，拖影带还在。3.1.10 的掩码↔帧对齐（见 updateMask / collectAsync）
// 才是把滞后从「掩码落后画面」改成「整帧落后 33ms」—— 对齐之后边界不再扫动，
// 羽化只负责软化矩形裁剪的硬角，所以才能收窄到 8%。
//
// 为什么不做运动预测：预测在急停/反向时会把掩码甩到脸前面（过冲），那是另一种
// 更难看的东西。帧对齐 + 软边比它便宜且稳。
//
// 为什么是 0.08 而不是 0.12：3.1.9 第一版跟了 wtnl-zhi 的默认 12%，真机反馈
// 「整体效果弱了较多」—— 我们的掩码不只是脸的椭圆，还有脖子通道（横向 0.90 脸宽、
// 一直伸到领口），12% 脸宽的带子打进脖子的横向范围就是 13% 半宽，脸框四条边各削
// 一条带子加起来实测把掩码总能量削掉 10%，而 face_src 离线图上脸不贴框，这个数字
// 被低估了。8% 回到自定的第一版，配合 3.1.10 的「掩码与帧对齐」够用 —— 对齐之后
// 边界不再每帧移动，羽化只需要把矩形裁剪的硬角软化，不再需要补偿滞后。
// （wtnl-zhi 的 12% 是骑在椭圆边界上内外各一半的，我们只能向内，等价于更厚的边。）
const float kMaskFeatherRatio = 0.08f;

// -1 = 按脸宽自适应；0 = 关闭（与 3.1.8 逐字节相同，A/B 用）；>0 = 固定像素
int g_maskFeatherPx = -1;

// 掩码几何形状（3.1.20）。
//
// 问题：旧版把掩码画成**两个矩形**——脸框一个、脖子通道一个。羽化只能把硬边变成
// 软边，边本身还是**直的**：脖子左右两条竖线永远「切」在脖子皮肤上，线外一刀不磨。
// 头部快速摆动时这两条直边在脖子上来回扫，观感就是「遮罩残影」（用户 2026-10-30 反馈）。
//
// 做法：把裁剪边界从矩形换成**椭圆距离场**，边界沿 (x/a)²+(y/b)²=1 连续收敛，
// 没有一段是直的；羽化仍然沿用 kMaskFeatherRatio 的斜坡，所以只是「形状」变了，
// 「软硬」不变。
//
// 位掩码（可用 BEAUTY_MASK_SHAPE 覆盖，离线 A/B 用）：
//   0 = 矩形（3.1.19 及以前的旧行为）
//   1 = 脸用椭圆
//   2 = 脖子用椭圆
//   3 = 两者都用椭圆
int g_maskShape = 0;

// 羽化斜坡查表：ramp[dist * 65 + fe] = smoothstep(dist/fe) × 256。
//
// 为什么查表：羽化在 worker 上逐像素跑，1080p 脸框约 40 万像素，每像素至少一次
// 整数除法就是 40 万次（约 10ms），能把这层优化整个吃掉。表只有 65×65 个 int
// （17KB，常驻 L1/L2），首次使用时算一次，之后每像素只剩一次乘法寻址。
const int kFeatherMax = 64;          // 与 buildMaskInto 里的 clamp 上限一致
int g_featherRamp[(kFeatherMax + 1) * (kFeatherMax + 1)];
bool g_featherReady = false;

void initFeatherRamp() {
    for (int fe = 0; fe <= kFeatherMax; fe++) {
        for (int d = 0; d <= kFeatherMax; d++) {
            int v;
            if (fe <= 0 || d >= fe) {
                v = 256;
            } else if (d <= 0) {
                v = 0;
            } else {
                const float t = (float)d / (float)fe;
                v = (int)(t * t * (3.0f - 2.0f * t) * 256.0f + 0.5f);
            }
            g_featherRamp[d * (kFeatherMax + 1) + fe] = v;
        }
    }
    g_featherReady = true;
}

// 距边界 dist 像素处的羽化系数：0（边界）→ 256（dist >= fe）。
// 必须在 initFeatherRamp() 之后调用（ensureReady 里初始化，早于任何掩码构建）。
inline int featherRamp(int dist, int fe) {
    if (fe <= 0) return 256;
    if (!g_featherReady) return 256;   // 表没建好就当没羽化，退回 3.1.8 行为
    if (fe > kFeatherMax) fe = kFeatherMax;
    if (dist <= 0) return 0;
    if (dist >= fe) return 256;
    if (dist > kFeatherMax) dist = kFeatherMax;
    return g_featherRamp[dist * (kFeatherMax + 1) + fe];
}

// 脖子通道参数（离线扫参用）。生产路径不设这两个环境变量，走上面的默认值。
// 与 BEAUTY_FACE_MODEL 同一套写法：只在 ensureReady 里读一次。
struct NeckCfg {
    float halfW = kNeckHalfW;
    float len = kNeckLen;
};
NeckCfg g_neck;

// 脖子通道总开关（1.0.6.0）。`BEAUTY_NECK=0` 无条件关掉，用于离线 A/B
// 和「我就要脸、不要脖子」的用户 —— 关掉后 ROI 与掩码都会小一圈，是可量化的收益。
bool g_neckOn = true;

// 自身 DLL 所在目录（找模型用）
std::string selfDir() {
    char path[MAX_PATH] = {0};
    HMODULE hm = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&beautyCoreSetSmoothParams, &hm);
    if (hm) GetModuleFileNameA(hm, path, MAX_PATH);
    std::string s(path);
    const size_t p = s.find_last_of("\\/");
    return (p == std::string::npos) ? std::string(".") : s.substr(0, p);
}

// YCbCr 肤色判据（与 legacy_engine.cpp 的 applyWhiten 同一套阈值）
// A/B 开关：true = 旧的 YCbCr 矩形窗 + 硬 0/255（改造前行为），
// false = 椭圆 + 软边 + 亮度门控（默认）。只用于离线对比，生产不设环境变量。
bool g_skinHard = false;

// 肤色椭圆的**中心与半径**（C20）。
//
// 原来这两个中心是写死的常量（抄自 MIT 版 lumina-beauty）。它是相机在标准
// 白平衡下统计出来的，可摄像头不保证白平衡 —— C20 实测：真机帧平均 RGB
// 151/118/134（B > G，白平衡偏冷），整张脸被推出椭圆，皮肤掩码只剩 41%，
// 磨皮强度掉到 参考实现的 1/8。而离线素材 face_src 在同一判据下是 99%。
// 同一个核参数只因素材白平衡不同就差 2.8 倍，此前所有离线调参都建立在
// 「掩码 ≈ 95%」这个失真前提上。
//
// 修法：中心改为**逐帧从画面本身估计**（脸框中心区色度中位数），半径保留常量。
// 关键性质：在 face_src 这种标准白平衡素材上，估计出的中心 (−0.063, 0.096)
// 与默认 (−0.065, 0.095) 几乎重合 —— 所以开启自适应不会推翻此前结论。
float g_skinCb = -0.065f;         // 椭圆中心（逐帧估计，这里是初值/兜底值）
float g_skinCr = 0.095f;
float g_skinRu = 0.075f;          // 椭圆半径（C20 方案 B2 的兜底旋钮）
float g_skinRv = 0.070f;
bool  g_skinAdapt = true;         // 自适应中心开关（BEAUTY_SKIN_ADAPT=0 关闭）
float g_skinAdaptEma = 1.0f;      // 帧间平滑系数，**默认 1.0 = 纯函数无状态**
bool  g_skinAdaptValid = false;   // 上一帧是否取得有效中心（EMA 初始化用）

// 「估计首次收效」的一次性上报标志（C20 真机自查）。3.1.13 首版只在 init 时
// 打了一行 skin=，那一行永远是"(center=default, not yet estimated)" —— 用户
// 拿着日志没法回答「第 2 帧以后估计真的成功了？」。worker 第一次把估计结果
// 写进 g_skinCb/g_skinCr 时置位，渲染线程在 video_render 里取走并打一行。
// panel 只在 init 调 beautyCoreSkinInfo()、没有周期性 re-log，这是补的出口。
std::atomic<bool> g_skinAnnounce{false};

// 为什么 EMA 默认必须是 1.0：任何 <1 的系数都会让中心携带历史，同一张图
// 重复处理（ROI 对拍、多次 BeautyCoreRun）得到不同掩码 —— verify_roi 实测
// maxdiff=1（EMA=0.15），EMA=0 或 1 时 ALL PASS。确定性优先于平滑。
// 真机若观察到磨皮强度逐帧闪，可设 BEAUTY_SKIN_EMA=0.2 压住抖动
// （代价是失去确定性，只在真机场景用）。

// 从画面估计本帧肤色色度中心。
//
// 采样区 = 最大脸框的中心 40%×40%（避开背景、头发、额头镜面高光）；
// 迭代两次「取中位数 → 用新中心剔除离群 → 再取中位数」—— 实测迭代 1 次即收敛，
// 第 2 次只是防极端光照下的抖动。
//
// 返回 false = 采样不足（戴口罩、手挡脸、极暗），调用方保持默认/上一帧中心。
bool estimateSkinCenter(const unsigned char* src, int w, int h,
                        const std::vector<beautycore::FaceBox>& faces,
                        float& outCb, float& outCr) {
    if (faces.empty()) return false;
    // 多脸时取最大的那张 —— 主脸的肤色才是要磨的对象，小脸样本少噪声大
    const beautycore::FaceBox* best = &faces[0];
    for (const auto& f : faces)
        if (f.w * f.h > best->w * best->h) best = &f;

    const float fx0 = best->x + best->w * 0.30f;
    const float fx1 = best->x + best->w * 0.70f;
    const float fy0 = best->y + best->h * 0.40f;
    const float fy1 = best->y + best->h * 0.80f;
    int x0 = (int)fx0, x1 = (int)fx1, y0 = (int)fy0, y1 = (int)fy1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > w) x1 = w;
    if (y1 > h) y1 = h;
    const int bw = x1 - x0, bh = y1 - y0;
    if (bw < 8 || bh < 8) return false;

    // 采样步长：控制采样点在 8000 以内，保证每 4 帧一次的这个 pass 足够便宜
    int step = 1;
    while ((bw / step) * (bh / step) > 8000) step++;
    if (step > 8) step = 8;

    std::vector<float> cbs, crs;
    cbs.reserve(8192);
    crs.reserve(8192);
    // 先按亮度粗筛一次并缓存色度，后面两轮迭代只做剔除、不再重算 RGB→YCbCr
    std::vector<float> cbAll, crAll;
    cbAll.reserve(8192);
    crAll.reserve(8192);
    std::vector<unsigned char> keep;
    keep.reserve(8192);
    for (int y = y0; y < y1; y += step) {
        const unsigned char* row = src + ((size_t)y * w) * 4;
        for (int x = x0; x < x1; x += step) {
            const int i = x * 4;
            const float r = row[i] * (1.0f / 255.0f);
            const float g = row[i + 1] * (1.0f / 255.0f);
            const float b = row[i + 2] * (1.0f / 255.0f);
            const float yv = 0.299f * r + 0.587f * g + 0.114f * b;
            // 暗部与过曝区不参与统计（鼻孔、发缝、镜面高光）
            if (yv < 0.12f || yv > 0.94f) continue;
            cbAll.push_back(-0.168736f * r - 0.331264f * g + 0.5f * b);
            crAll.push_back(0.5f * r - 0.418688f * g - 0.081312f * b);
        }
    }
    const size_t n = cbAll.size();
    const size_t need = (size_t)(((float)bw / step) * ((float)bh / step) * 0.30f);
    if (n < 64 || n < need) return false;   // 命中太少 → 不信任这个中心

    keep.assign(n, 1);
    float ccB = g_skinCb, ccR = g_skinCr;
    for (int iter = 0; iter < 2; iter++) {
        cbs.clear();
        crs.clear();
        for (size_t i = 0; i < n; i++) {
            if (!keep[i]) continue;
            cbs.push_back(cbAll[i]);
            crs.push_back(crAll[i]);
        }
        if (cbs.size() < 32) return false;
        // 中位数（nth_element 是 O(n)，比完整排序便宜）
        const size_t mid = cbs.size() / 2;
        std::nth_element(cbs.begin(), cbs.begin() + mid, cbs.end());
        std::nth_element(crs.begin(), crs.begin() + mid, crs.end());
        ccB = cbs[mid];
        ccR = crs[mid];
        if (iter == 1) break;
        // 用新中心剔除离群点，下一轮再取一次中位数
        for (size_t i = 0; i < n; i++) {
            const float du = (cbAll[i] - ccB) / g_skinRu;
            const float dv = (crAll[i] - ccR) / g_skinRv;
            keep[i] = (du * du + dv * dv < 2.25f) ? 1 : 0;   // d < 1.5
        }
    }
    outCb = ccB;
    outCr = ccR;
    return true;
}

// 肤色权重，返回 0..255 的**连续值**（不是布尔）。
//
// 判据与参数抄自 dinjufen/lumina-beauty 的 skinMask（核心代码为 MIT）：
//   - 在 CbCr **色度平面上画椭圆**（中心 -0.065/+0.095，半径 0.075/0.070），
//     距离 0.6~1.3 之间用 smoothstep 软过渡；
//   - 再乘亮度门控 smoothstep(0.12, 0.30, Y)：暗部不算皮肤，避免把阴影、
//     鼻孔、发缝当成肤色。
//
// 为什么换掉原来的矩形窗：
//   1) 矩形窗在 (Cb,Cr) 平面的**四个角**会误判 —— 那些组合真实肤色里不存在；
//   2) 硬 0/255 让磨皮强度在掩码边界**瞬间跳变**，观感上就是鼻梁侧面、
//      下颌线出现台阶状硬边。软边把跳变摊开成过渡带。
inline int skinWeight(int R, int G, int B) {
    if (g_skinHard) {
        // 改造前的判据，原样保留以便 A/B 对拍
        const int Y = (66 * R + 129 * G + 25 * B + 128) >> 8;
        const int Cb = ((-38 * R - 74 * G + 112 * B + 128) >> 8) + 128;
        const int Cr = ((112 * R - 94 * G - 18 * B + 128) >> 8) + 128;
        const bool ok = (Cr >= 133 && Cr <= 173 && Cb >= 77 && Cb <= 127 &&
                         R > G && G > B && R > 80 && Y > 60 && Y < 235);
        return ok ? 255 : 0;
    }
    const float r = R * (1.0f / 255.0f);
    const float g = G * (1.0f / 255.0f);
    const float b = B * (1.0f / 255.0f);
    const float y = 0.299f * r + 0.587f * g + 0.114f * b;
    const float cb = -0.168736f * r - 0.331264f * g + 0.5f * b;
    const float cr = 0.5f * r - 0.418688f * g - 0.081312f * b;

    // 椭圆中心来自 g_skinCb/g_skinCr：默认常量，或由 estimateSkinCenter()
    // 逐帧从画面估计（C20）。半径 g_skinRu/g_skinRv 是方案 B2 的兜底旋钮。
    const float du = (cb - g_skinCb) / g_skinRu;
    const float dv = (cr - g_skinCr) / g_skinRv;
    const float d = sqrtf(du * du + dv * dv);

    float m = 1.0f - smoothStep(0.6f, 1.3f, d);
    // 暗部不算皮肤（避免把阴影、鼻孔、发缝当肤色）；
    // 同理过曝区也不算 —— 鼻梁、额头的镜面高光如果被磨平，会变成一块死白。
    m *= smoothStep(0.12f, 0.30f, y) * (1.0f - smoothStep(0.94f, 0.99f, y));
    if (m <= 0.0f) return 0;
    const int v = (int)(m * 255.0f + 0.5f);
    return (v > 255) ? 255 : v;
}

inline bool isSkin(int R, int G, int B) {
    return skinWeight(R, G, B) > 0;
}

// 毫秒级单调时钟（GetTickCount64 只有 15.6ms 精度，量几毫秒的核不够用）
double nowMsCore() {
    static LARGE_INTEGER freq = {0};
    if (freq.QuadPart == 0) QueryPerformanceFrequency(&freq);
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)freq.QuadPart;
}

// 把整帧 RGBA 的 A 通道强制置成 255。
//
// 为什么需要：引擎的 dst 是调用方给的独立缓冲，未被任何一项写到的像素保留
// 上一帧的残留（包括 A）。OBS 侧必须拿到不透明 alpha，否则合成出来是黑的。
//
// 1.0.8.0：从 obs-beauty.cpp 的插件层搬进来。原来的写法是「每帧在插件里跑一遍
// 207 万次 32 位读改写」（1080p 实测约 0.4 ms），但那遍发生在**引擎返回之后**，
// 数据已经凉了；挪到引擎末尾，同一批 cache line 刚被本帧写过，代价降到 0.1 ms
// 量级。语义与原来完全一致（无条件全帧、在引擎输出之后）。
void forceOpaque(unsigned char* buf, size_t px) {
    if (!buf || px == 0) return;
    size_t k = 0;
#if defined(_M_X64) || defined(_M_IX86)
    const __m128i a = _mm_set1_epi32((int)0xFF000000u);
    for (; k + 4 <= px; k += 4) {
        __m128i* p = (__m128i*)(void*)(buf + k * 4);
        _mm_storeu_si128(p, _mm_or_si128(_mm_loadu_si128(p), a));
    }
#endif
    uint32_t* p32 = (uint32_t*)(void*)buf;
    for (; k < px; k++) p32[k] |= 0xFF000000u;
}

// 1.0.10.0：A 通道是否由引擎负责。BEAUTY_ALPHA_IN_ENGINE=0 回到 1.0.7.0 的分工
// （引擎不碰 A，插件在上传段跑一遍标量循环）。做成开关是为了在真机上把
// 「搬进引擎」与「留在插件层」各测一遍 —— 两者只在真机才可能有差别。
bool alphaInEngine()
{
    static const bool v = []() {
        const char* e = beauty_env("BEAUTY_ALPHA_IN_ENGINE");
        return !(e && *e == '0');
    }();
    return v;
}

// ---------------------------------------------------------------------------
// CoreEngine —— 自研引擎（S2 起逐步成型）
//
// 第一版只做磨皮一件事，这样对拍最干净：输入原图 → 自研双边滤波 → 按档位线性
// 混合。掩码、美白、红润、细节回填随后逐个接进来 —— 每接一个都在 golden 上
// 对拍一次，而不是一次性写完再看差多少。
//
// 参数映射：面板磨皮 0..100 → 混合系数 t = 档位/100。与参考实现侧
// bgraToRgbaBlend 的定义完全一致，所以两边同档位可以直接比。
// ---------------------------------------------------------------------------
class CoreEngine : public IBeautyEngine {
public:
    static const int kMaxSlots = 8;

    // 把上下文里的同名字段绑成局部引用。函数体保持原样即可，不必逐个改写成
    // S.xxx —— 这些绑定会被优化掉，运行时零成本；而一旦漏绑，编译期就会因为
    // 「找不到成员」直接报错，不会留下静默的跨实例共享。
#define BEAUTY_BIND_DET_DIR(S) \
    auto& effRot_ = (S).effRot; \
    auto& rotManual_ = (S).rotManual; \
    auto& autoMiss_ = (S).autoMiss; \
    auto& autoCool_ = (S).autoCool; \
    auto& autoProbeLogged_ = (S).autoProbeLogged; \
    auto& rotFallbackLogged_ = (S).rotFallbackLogged; \
    auto& rotLastW_ = (S).rotLastW; \
    auto& rotLastH_ = (S).rotLastH; \
    auto& effRoll_ = (S).effRoll; \
    auto& rollMiss_ = (S).rollMiss; \
    auto& rollCool_ = (S).rollCool; \
    auto& rollProbeLogged_ = (S).rollProbeLogged; \
    auto& rollCheck_ = (S).rollCheck; \
    auto& rollReleaseLog_ = (S).rollReleaseLog
#define BEAUTY_BIND_DET_ALL(S) \
    BEAUTY_BIND_DET_DIR(S); \
    auto& mask_ = (S).mask; \
    auto& protect_ = (S).protect; \
    auto& faces_ = (S).faces; \
    auto& bounds_ = (S).bounds; \
    auto& maskValid_ = (S).maskValid; \
    auto& everHadMask_ = (S).everHadMask; \
    auto& maskAge_ = (S).maskAge; \
    auto& maskHold_ = (S).maskHold; \
    auto& heldFrame_ = (S).heldFrame; \
    auto& maskFresh_ = (S).maskFresh; \
    auto& lastFaces_ = (S).lastFaces; \
    auto& maskPixels_ = (S).maskPixels; \
    auto& faceErr_ = (S).faceErr; \
    auto& frameNo_ = (S).frameNo; \
    auto& detailEmaGen_ = (S).detailEmaGen; \
    auto& detailLumT_ = (S).detailLumT; \
    auto& detailEmaReset_ = (S).detailEmaReset; \
    auto& lastMs_ = (S).lastMs; \
    auto& st_ = (S).st; \
    auto& geoFrom_ = (S).geoFrom; \
    auto& geoFadeLeft_ = (S).geoFadeLeft; \
    auto& geoLast_ = (S).geoLast

    const char* id() const override { return "core"; }
    // 1.4.0 → 1.4.1（3.1.40）：无脸帧改走逐字节透传，不再全帧兜底磨皮。
    // 门控语义变了 ⇒ 无脸帧的画面输出与 1.4.0 不同，旧的对拍数字不覆盖这条路径。
    // 引擎版本并入 CPU 单轴，不再维护独立的 core 1.4.x 号。
    // 2026-11-07：改为引用 beauty_params.h 的唯一出处（经 beauty_core.h 引入），
    // 根治「滤镜已是新版本、init 日志却打印 engine=core/<旧版本>」的失同步。
    const char* version() const override { return BEAUTY_BUILD_STR; }

    bool ensureReady(std::string& err) override {
        // 1.0.13.4：初始化串行。preheat()（模块加载）与 acquireSlot()（宿主建滤镜）
        // 是两条不同的调用路径，OBS 里两个场景项同时建滤镜时它们可能分别在两条
        // 线程上进来，而 faceTried_ 这个「只试一次」的闸门本身不是原子的 ——
        // 两边同时看到 false，就会**各自** face_.load() 一次：多付一次模型加载
        // （100~300 ms），后一个还会把前一个刚建好的会话拆掉重建。
        std::lock_guard<std::mutex> initLk(initMtx_);
        // 人脸检测模型只试一次。失败不阻止引擎就绪 —— 降级为「无掩码，全帧磨皮」，
        // 与参考实现在 region=off 时的行为一致，不会让滤镜整体失效。
        if (!faceTried_) {
            faceTried_ = true;
            const std::string d = selfDir();
            // 必须告诉 ORT 去哪找自己的 DLL：系统里可能另有别的版本
            beautycore::onnxSetRuntimeDir(d.c_str());
            std::string mp;
            const char* envp = beauty_env("BEAUTY_FACE_MODEL");
            if (envp && *envp) {
                mp = envp;
            } else {
                mp = d + "\\models\\yunet.onnx";
                FILE* probe = nullptr;
                if (fopen_s(&probe, mp.c_str(), "rb") != 0 || !probe) {
                    mp = d + "\\yunet.onnx";
                } else {
                    fclose(probe);
                }
            }
            std::string ferr;
            faceOk_ = face_.load(mp.c_str(), ferr);
            // 加载失败发生在 acquireSlot 之前，此时没有任何 slot 上下文可用，
            // 所以单独存在成员里；lastErr() 会优先把它报出来。
            faceLoadErr_ = faceOk_ ? std::string() : (mp + " : " + ferr);
            if (faceOk_) {
                // 推理输入边长：320 比 640 快约 4 倍（像素数差 4 倍）。
                // 代价是小脸检出率下降 —— 默认值由离线对拍定，环境变量留给复验。
                int isz = kFaceInputDefault;
                const char* fenv = beauty_env("BEAUTY_FACE_INPUT");
                if (fenv && *fenv) isz = atoi(fenv);
                face_.setInputSize(isz);
            }
            // 脖子通道参数（离线扫参用；生产不设环境变量）
            const char* nhw = beauty_env("BEAUTY_NECK_HALFW");
            if (nhw && *nhw) g_neck.halfW = (float)atof(nhw);
            const char* nln = beauty_env("BEAUTY_NECK_LEN");
            if (nln && *nln) g_neck.len = (float)atof(nln);
            // 脖子通道总开关（1.0.6.0）：BEAUTY_NECK=0 整段不画。
            const char* nk = beauty_env("BEAUTY_NECK");
            g_neckOn = !(nk && nk[0] == '0');
            // 边缘门控灵敏度（0 = 关闭）。生产默认 10，这里只为离线复验留口子。
            const char* ek = beauty_env("BEAUTY_EDGE_K");
            if (ek && *ek) g_cfg.edgeK = atoi(ek);
            // 肤色判据 A/B：BEAUTY_SKIN_HARD=1 回到旧矩形窗（离线对比用）
            const char* sh = beauty_env("BEAUTY_SKIN_HARD");
            g_skinHard = (sh && sh[0] == '1');
            // 肤色椭圆中心自适应（C20 方案 A）：BEAUTY_SKIN_ADAPT=0 回到固定中心。
            // 默认开 —— 固定中心在白平衡偏冷的摄像头上会把掩码压到 34%。
            const char* sa = beauty_env("BEAUTY_SKIN_ADAPT");
            if (sa && *sa) g_skinAdapt = (sa[0] != '0');
            // 半径缩放（C20 方案 B2 兜底）：BEAUTY_SKIN_RADIUS=1.5 放宽 1.5 倍。
            // 自适应失效时的保底手段，代价是暖色背景误判增加。
            const char* sr = beauty_env("BEAUTY_SKIN_RADIUS");
            if (sr && *sr) {
                const float k = (float)atof(sr);
                if (k > 0.1f) { g_skinRu = 0.075f * k; g_skinRv = 0.070f * k; }
            }
            // 中心帧间平滑系数（0 = 不平滑，1 = 完全跟随本帧）
            const char* se = beauty_env("BEAUTY_SKIN_EMA");
            if (se && *se) g_skinAdaptEma = (float)atof(se);
            // 五官保护强度 A/B：BEAUTY_PROTECT_K=0 关闭（离线对比用）
            const char* pk = beauty_env("BEAUTY_PROTECT_K");
            if (pk && *pk) g_cfg.protectK = atoi(pk);
            // 阈值软膝 A/B：BEAUTY_LIMIT_THR=0 关闭
            const char* lt = beauty_env("BEAUTY_LIMIT_THR");
            if (lt && *lt) g_cfg.limitThr = atoi(lt);
            // 高低频磨皮：BEAUTY_FREQ=0 退回旧的「双边+线性混合」做 A/B
            const char* fq = beauty_env("BEAUTY_FREQ");
            if (fq && *fq) g_cfg.freqMode = (fq[0] != '0');
            const char* fi = beauty_env("BEAUTY_FREQ_ITERS");
            if (fi && *fi) g_cfg.freqIters = atoi(fi);
            const char* fg = beauty_env("BEAUTY_FREQ_GRAIN");
            if (fg && *fg) g_cfg.freqGrain = (float)atof(fg);
            // 低频提取方式：BEAUTY_LOW_MODE=1 用引导滤波
            const char* lm = beauty_env("BEAUTY_LOW_MODE");
            if (lm && *lm) g_cfg.freqLowMode = atoi(lm);
            const char* gr = beauty_env("BEAUTY_GUIDE_R");
            if (gr && *gr) g_cfg.guideRadius = atoi(gr);
            const char* ge = beauty_env("BEAUTY_GUIDE_EPS");
            if (ge && *ge) g_cfg.guideEps = (float)atof(ge);
            // 低频层路线：BEAUTY_LOW_PATH=0 退回旧的 uint8 双边迭代，1 = 只换浮点，
            // 2 = 浮点 + 低频参照（默认）。三个值对应三组对照数据。
            const char* lp = beauty_env("BEAUTY_LOW_PATH");
            if (lp && *lp) g_cfg.lowPath = atoi(lp);
            const char* lr = beauty_env("BEAUTY_REF_R");
            if (lr && *lr) g_cfg.refRadius = atoi(lr);
            // C 方案（lowPath=3）的低频尺度：等效 σ² = iters × ((2r+1)²−1)/12
            const char* br = beauty_env("BEAUTY_BOX_R");
            if (br && *br) g_cfg.boxRadius = atoi(br);
            const char* bi = beauty_env("BEAUTY_BOX_ITERS");
            if (bi && *bi) g_cfg.boxIters = atoi(bi);
            // 档位饱和：BEAUTY_BLUR_SAT=0 退回线性（对比用）
            const char* bs = beauty_env("BEAUTY_BLUR_SAT");
            if (bs && *bs) g_cfg.blurSat = (float)atof(bs);
            // ---- surface3 三层磨皮（C22；默认关，只走环境变量）----
            // BEAUTY_SMOOTH_MODEL=surface3|1 打开；不设或 =legacy|0 走旧核。
            const char* smodel = beauty_env("BEAUTY_SMOOTH_MODEL");
            if (smodel && *smodel)
                g_cfg.smoothModel = (smodel[0] == 's' || smodel[0] == 'S' ||
                                     smodel[0] == '1') ? 1 : 0;
            const char* s3r1 = beauty_env("BEAUTY_S3_R1");
            if (s3r1 && *s3r1) g_cfg.s3R1 = atoi(s3r1);
            const char* s3i1 = beauty_env("BEAUTY_S3_IT1");
            if (s3i1 && *s3i1) g_cfg.s3It1 = atoi(s3i1);
            const char* s3r2 = beauty_env("BEAUTY_S3_R2");
            if (s3r2 && *s3r2) g_cfg.s3R2 = atoi(s3r2);
            const char* s3r0 = beauty_env("BEAUTY_S3_R0");
            if (s3r0 && *s3r0) g_cfg.s3R0 = atoi(s3r0);
            const char* s3i2 = beauty_env("BEAUTY_S3_IT2");
            if (s3i2 && *s3i2) g_cfg.s3It2 = atoi(s3i2);
            const char* s3t1 = beauty_env("BEAUTY_S3_THR1");
            if (s3t1 && *s3t1) g_cfg.s3Thr1 = (float)atof(s3t1);
            const char* s3t2 = beauty_env("BEAUTY_S3_THR2");
            if (s3t2 && *s3t2) g_cfg.s3Thr2 = (float)atof(s3t2);
            const char* s3k = beauty_env("BEAUTY_S3_K");
            if (s3k && *s3k) g_cfg.s3K = (float)atof(s3k);
            // 3.1.14：e 模型换成 GLSL 原式，旧旋钮 EHI/EOFF 已废弃（不再解析）。
            // ELO 语义等价于新的 E0（evenfactor 下限），保留为别名，免得老脚本
            // 静默失效 —— 但注意 ELO 现在**只影响下限**，不再影响高段斜率。
            const char* s3e0 = beauty_env("BEAUTY_S3_E0");
            if (s3e0 && *s3e0) g_cfg.s3E0 = (float)atof(s3e0);
            const char* s3el = beauty_env("BEAUTY_S3_ELO");
            if (s3el && *s3el) g_cfg.s3E0 = (float)atof(s3el);
            const char* s3es = beauty_env("BEAUTY_S3_ESAT");
            if (s3es && *s3es) g_cfg.s3ESat = (float)atof(s3es);
            const char* s3et = beauty_env("BEAUTY_S3_ETHR");
            if (s3et && *s3et) g_cfg.s3EThr = (float)atof(s3et);
            const char* s3ek = beauty_env("BEAUTY_S3_EYEK");
            if (s3ek && *s3ek) g_cfg.s3EyeK = (float)atof(s3ek);
            // 25 tap（第 2 批 #5/#6/#7）。TAP25 是总开关，其余只在它打开时有用。
            const char* s3t25 = beauty_env("BEAUTY_S3_TAP25");
            if (s3t25 && *s3t25) g_cfg.s3Tap25 = atoi(s3t25);
            const char* s3sx = beauty_env("BEAUTY_S3_SX");
            if (s3sx && *s3sx) g_cfg.s3Sx = (float)atof(s3sx);
            const char* s3sy = beauty_env("BEAUTY_S3_SY");
            if (s3sy && *s3sy) g_cfg.s3Sy = (float)atof(s3sy);
            const char* s3y1 = beauty_env("BEAUTY_S3_YF1");
            if (s3y1 && *s3y1) g_cfg.s3YF1 = (float)atof(s3y1);
            const char* s3y2 = beauty_env("BEAUTY_S3_YF2");
            if (s3y2 && *s3y2) g_cfg.s3YF2 = (float)atof(s3y2);
            const char* s3hf = beauty_env("BEAUTY_S3_HALF");
            if (s3hf && *s3hf) g_cfg.s3Half = atoi(s3hf);
            // 双尺度带通（第 2 批-B）。BAND 是总开关，T 只在它打开时有用。
            const char* s3bd = beauty_env("BEAUTY_S3_BAND");
            if (s3bd && *s3bd) g_cfg.s3Band = atoi(s3bd);
            const char* s3bt = beauty_env("BEAUTY_S3_BT");
            if (s3bt && *s3bt) g_cfg.s3BandT = (float)atof(s3bt);
            // 档位 → (I, T) 查表（3.1.18）。LV_TABLE=0 退回旧的饱和式 I（对比用）。
            // LV_I / LV_T 形如 "0,0.005,0.205,0.574,0.975"，对应面板 0/25/50/75/100。
            const char* lvt = beauty_env("BEAUTY_S3_LV_TABLE");
            if (lvt && *lvt) g_cfg.lvTable = atoi(lvt);
            parse5(beauty_env("BEAUTY_S3_LV_I"), g_cfg.lvI);
            parse5(beauty_env("BEAUTY_S3_LV_T"), g_cfg.lvT);
            parse5(beauty_env("BEAUTY_S3_LV_E"), g_cfg.lvE);
            // 1.0.0.1 低档段形状开关。BEAUTY_S3_LV_SHAPE=0 回退旧五锚点表
            // （历史报告用 "0,<v>" 覆盖 BEAUTY_S3_LV_I 的语义因此完全不变）；
            // BEAUTY_S3_LV_I7 单独覆盖新的七锚点表，供离线扫参与复现。
            const char* lvs = beauty_env("BEAUTY_S3_LV_SHAPE");
            if (lvs && *lvs) g_cfg.lvShape = (lvs[0] != '0') ? 1 : 0;
            parse7(beauty_env("BEAUTY_S3_LV_I7"), g_cfg.lvI7);
            const char* sef = beauty_env("BEAUTY_S3_E_FIX");
            if (sef && *sef) g_cfg.s3EFix = (float)atof(sef);
            const char* gwp = beauty_env("BEAUTY_S3_GWP");
            if (gwp && *gwp) g_cfg.s3Gwp = (float)atof(gwp);
            // clarity：BEAUTY_CLARITY_MAX 改上限（离线标定用），BEAUTY_CLARITY_R 改窗口
            const char* cm = beauty_env("BEAUTY_CLARITY_MAX");
            if (cm && *cm) g_cfg.clarityMax = (float)atof(cm);
            const char* cr = beauty_env("BEAUTY_CLARITY_R");
            if (cr && *cr) g_cfg.clarityRadius = atoi(cr);
            // 异步检测：BEAUTY_ASYNC_DETECT=0 关掉（离线对拍要确定性）
            const char* ad = beauty_env("BEAUTY_ASYNC_DETECT");
            if (ad && *ad) g_cfg.asyncDetect = (ad[0] != '0');
            // 3.1.40：无脸帧是否跳过整段处理。BEAUTY_NOFACE_SKIP=0 回到旧行为
            // （无掩码 → 全帧兜底磨皮，逐字节等于 3.1.39）。
            const char* nfs = beauty_env("BEAUTY_NOFACE_SKIP");
            if (nfs && *nfs) g_cfg.noFaceSkip = (nfs[0] != '0');
            // 1.0.0.2 人脸框时序平滑。两个开关都关才逐字节回到 1.0.0.1；
            // 复现历史 golden 基线时请显式设 BEAUTY_FACE_EMA=0 BEAUTY_FACE_HOLD=0。
            const char* fbEma = beauty_env("BEAUTY_FACE_EMA");
            if (fbEma && *fbEma) g_cfg.faceEma = (float)atof(fbEma);
            const char* fbHold = beauty_env("BEAUTY_FACE_HOLD");
            if (fbHold && *fbHold) g_cfg.faceHold = atoi(fbHold);
            const char* fbArea = beauty_env("BEAUTY_FACE_AREA");
            if (fbArea && *fbArea) g_cfg.faceHoldAreaRatio = (float)atof(fbArea);
            const char* fbIou = beauty_env("BEAUTY_FACE_IOU");
            if (fbIou && *fbIou) g_cfg.faceHoldIoU = (float)atof(fbIou);
            // 1.0.3.0：输入方向。源被场景项转过 90° 时滤镜拿到的帧是躺着的
            // （竖屏摄像头 / 手机竖拍），YuNet 检不出脸 → 美颜整段静默失效。
            //   BEAUTY_INPUT_ROT=90   手工声明源被转了多少度（0/90/180/270）
            //   BEAUTY_AUTO_ROT=0     关掉自动探测（逐字节回到 1.0.2.0）
            //   BEAUTY_AUTO_ROT_MISS  试探前要连续多少次无脸（3..600，默认 20）
            //   BEAUTY_AUTO_ROT_COOL  一次试探后的冷却（0..6000，默认 60）
            // BEAUTY_INPUT_ROT 的解析挪到 initDetState()：方向状态现在按 slot 存，
            // 而 ensureReady() 早于 acquireSlot()，在这里赋值会落到一份还没有归属
            // 的上下文上。
            const char* ar = beauty_env("BEAUTY_AUTO_ROT");
            if (ar && *ar) g_cfg.autoRot = (ar[0] != '0');
            const char* arm = beauty_env("BEAUTY_AUTO_ROT_MISS");
            if (arm && *arm) {
                int v = atoi(arm);
                if (v >= 3 && v <= 600) g_cfg.autoRotMiss = v;
            }
            const char* arc = beauty_env("BEAUTY_AUTO_ROT_COOL");
            if (arc && *arc) {
                int v = atoi(arc);
                if (v >= 0 && v <= 6000) g_cfg.autoRotCool = v;
            }
            // 1.0.5.0：平面内倾斜（头歪）补偿。默认开；=0 逐字节回到 1.0.4.0。
            const char* arl = beauty_env("BEAUTY_AUTO_ROLL");
            if (arl && *arl) g_cfg.autoRoll = (arl[0] != '0');
            const char* rlm = beauty_env("BEAUTY_AUTO_ROLL_MISS");
            if (rlm && *rlm) {
                int v = atoi(rlm);
                if (v >= 2 && v <= 600) g_cfg.rollMiss = v;
            }
            // 1.0.13.9：倾斜锁死释放的对照周期。0 = 关闭这道门，退回 1.0.13.8
            // 的「锁定后只能靠检不到脸才退回」；A/B 与回退都用这个。
            const char* rck = beauty_env("BEAUTY_ROLL_CHECK");
            if (rck && *rck) {
                int v = atoi(rck);
                if (v >= 0 && v <= 6000) g_cfg.rollCheckFrames = v;
            }
            // 方向/倾斜的初值见 initDetState()（按 slot 初始化）。
            // 异步提交周期：BEAUTY_MASK_EVERY=4 退回 3.1.7 的节奏（拖影回来，但省 CPU）。
            // 留这个口子是为了让真机能当场对比 0 / 1 / 2 / 4 四档，不用改代码重编译。
            const char* me = beauty_env("BEAUTY_MASK_EVERY");
            if (me && *me) {
                int v = atoi(me);
                if (v < 0) v = 0;
                g_cfg.maskEveryAsync = v;
            }
            // 掩码边界羽化：BEAUTY_MASK_FEATHER=0 关闭（与 3.1.8 逐字节相同，A/B 用），
            // >0 固定像素；不设则按脸宽自适应（0.12 × 脸宽，对齐 wtnl-zhi 的默认值）。
            const char* mf = beauty_env("BEAUTY_MASK_FEATHER");
            if (mf && *mf) {
                int v = atoi(mf);
                g_maskFeatherPx = (v < 0) ? -1 : v;
            }
            // 掩码几何：BEAUTY_MASK_SHAPE=0 退回矩形（3.1.19 行为），3 = 脸+脖子都用椭圆。
            const char* msh = beauty_env("BEAUTY_MASK_SHAPE");
            if (msh && *msh) g_maskShape = atoi(msh);
            initFeatherRamp();   // 羽化查表：必须早于任何一次 buildMaskInto
            // 3.1.10 掩码↔帧对齐：BEAUTY_MASK_ALIGN=0 关闭（回到 3.1.9 的
            // 「当前帧 + 旧掩码」，会拖影但零延迟，A/B 用）。
            const char* ma = beauty_env("BEAUTY_MASK_ALIGN");
            if (ma && *ma) alignOn_ = (ma[0] != '0');
            // 1.0.13.8：对齐的「画面没动」阈值。0 = 退回 3.1.10 的「有结果就对」。
            const char* adj = beauty_env("BEAUTY_ALIGN_DIFF");
            if (adj && *adj) {
                const double v = atof(adj);
                if (v >= 0.0 && v <= 64.0) g_cfg.alignDiff = (float)v;
            }
            asyncOn_ = g_cfg.asyncDetect;
            // 异步检测会和磨皮抢核：留一个核给 worker，否则磨皮那一帧会被拖慢
            // （实测 1080p 非检测帧从 6.4ms 涨到 13.7ms，等于尖峰换了个形状）。
            if (asyncOn_ && g_cfg.threads <= 0) {
                const unsigned hc = std::thread::hardware_concurrency();
                if (hc > 2) g_cfg.threads = (hc > 9) ? 8 : (int)hc - 1;
            }
            const char* fm = beauty_env("BEAUTY_FREQ_MAG");
            if (fm && *fm) {
                float lo = 0, hi = 0;
                if (sscanf(fm, "%f,%f", &lo, &hi) == 2) {
                    g_cfg.freqMagLo = lo;
                    g_cfg.freqMagHi = hi;
                }
            }
            // 细节回填（锐化）：BEAUTY_DETAIL_THR 改细频带软阈值（削噪量），
            // BEAUTY_DETAIL_MID 改中频带基准增益。两者只在离线标定时用。
            const char* dt = beauty_env("BEAUTY_DETAIL_THR");
            if (dt && *dt) g_cfg.detailThrFine = (float)atof(dt);
            const char* dm = beauty_env("BEAUTY_DETAIL_MID");
            if (dm && *dm) g_cfg.detailMidGain = (float)atof(dm);
            // 3.1.35：磨皮=0 纯锐化模式的细频增益 / 细频阈值（见配置段 faceSharpGain / faceSharpThrFine）。
            const char* fsg = beauty_env("BEAUTY_FACE_SHARP_GAIN");
            if (fsg && *fsg) g_cfg.faceSharpGain = (float)atof(fsg);
            const char* fst = beauty_env("BEAUTY_FACE_SHARP_THR");
            if (fst && *fst) g_cfg.faceSharpThrFine = (float)atof(fst);
            // 全局锐化自己的旋钮（3.1.22，从 detailMidGain / detailThrFine 拆出）
            const char* gm = beauty_env("BEAUTY_DETAIL_MID_GLOBAL");
            if (gm && *gm) g_cfg.globalMidGain = (float)atof(gm);
            const char* gf = beauty_env("BEAUTY_DETAIL_FINE_GLOBAL");
            if (gf && *gf) g_cfg.globalFineGain = (float)atof(gf);
            const char* gt = beauty_env("BEAUTY_DETAIL_THR_GLOBAL");
            if (gt && *gt) g_cfg.globalThrFine = (float)atof(gt);
            const char* gt2 = beauty_env("BEAUTY_DETAIL_THR_MID_GLOBAL");
            if (gt2 && *gt2) g_cfg.globalThrMid = (float)atof(gt2);
            // 磨皮后的基准细频回填比例（0 = 关）。见配置段 blurRefill 的说明。
            const char* brf = beauty_env("BEAUTY_BLUR_REFILL");
            if (brf && *brf) g_cfg.blurRefill = (float)atof(brf);
            const char* brt = beauty_env("BEAUTY_BLUR_REFILL_THR");
            if (brt && *brt) g_cfg.blurRefillThr = (float)atof(brt);
            const char* brm = beauty_env("BEAUTY_BLUR_REFILL_MINI");
            if (brm && *brm) g_cfg.blurRefillMinI = (float)atof(brm);
            const char* brd = beauty_env("BEAUTY_BLUR_REFILL_DELTA");
            if (brd && *brd) g_cfg.blurRefillDelta = atoi(brd);
            // 细节层时序 EMA：BEAUTY_EMA=0 关掉（做 A/B 用），其余三个是阈值与 beta
            const char* em = beauty_env("BEAUTY_EMA");
            if (em && *em) g_cfg.emaOn = (em[0] != '0');
            const char* es = beauty_env("BEAUTY_EMA_STILL");
            if (es && *es) g_cfg.emaStill = (float)atof(es);
            const char* ef = beauty_env("BEAUTY_EMA_FULL");
            if (ef && *ef) g_cfg.emaFull = (float)atof(ef);
            const char* eb = beauty_env("BEAUTY_EMA_BETA");
            if (eb && *eb) g_cfg.emaBetaStill = (float)atof(eb);
            // 五官局部五项增益标定：BEAUTY_REG_GAIN="立体,亮眼,去黑眼圈,法令纹"
            // 只在离线对拍时用（要和 参考实现的差分峰值对齐时改这里，别改源码重编译）。
            // 3.1.22：后两项不再是「增益」了 ——
            //   黑眼圈 = 双层椭圆的**整体比例因子**（形状在代码里定档）
            //   法令纹 = 暗度模型的「斜率,封顶」
            const char* rg = beauty_env("BEAUTY_REG_GAIN");
            if (rg && *rg) {
                float a = 0, b = 0, c = 0, d = 0;
                if (sscanf(rg, "%f,%f,%f,%f", &a, &b, &c, &d) == 4) {
                    g_cfg.regThreedGain = a;
                    g_cfg.regEyeGain = b;
                    g_cfg.regPouchScale = c;
                    g_cfg.regNasoSlope = d;
                }
            }
            const char* rs = beauty_env("BEAUTY_REG_SPOT");
            if (rs && *rs) g_cfg.regSpotK = (float)atof(rs);
            // 五官局部三项（3.1.22 重建）：
            //   BEAUTY_REG_THREED = 立体增益比例因子（单值）
            //   BEAUTY_REG_POUCH  = 黑眼圈增益比例因子（单值）
            //   BEAUTY_REG_NASO   = "斜率,封顶"
            const char* rt = beauty_env("BEAUTY_REG_THREED");
            if (rt && *rt) g_cfg.regThreedGain = (float)atof(rt);
            const char* rp = beauty_env("BEAUTY_REG_POUCH");
            if (rp && *rp) g_cfg.regPouchScale = (float)atof(rp);
            const char* rn = beauty_env("BEAUTY_REG_NASO");
            if (rn && *rn) {
                float a, b;
                if (sscanf(rn, "%f,%f", &a, &b) == 2) {
                    g_cfg.regNasoSlope = a;
                    g_cfg.regNasoMaxLift = b;
                }
            }
            // 暗线闸门阈值（离线对拍用）："下限,上限"
            const char* rgate = beauty_env("BEAUTY_REG_NASO_GATE");
            if (rgate && *rgate) {
                float a, b;
                if (sscanf(rgate, "%f,%f", &a, &b) == 2) {
                    g_cfg.regNasoGateLo = a;
                    g_cfg.regNasoGateHi = b;
                }
            }
        }
        // 3.1.21：把「首帧」的一次性成本提前到这里（模块加载 / 引擎首次就绪）。
        warmUp();
        err.clear();
        return true;
    }
    // 预热：加载 YuNet 人脸模型（一次性，约 100~300 ms）。
    //
    // 3.1.4 修：这里以前是空壳（只 clear err 就返回），而 ensureReady() 是**唯一**
    // 做 face_.load() 的地方，obs-beauty.cpp 又从不直接调 ensureReady() —— 结果
    // OBS 里 faceOk_ 永远是 false，updateMask() 第 764 行第一句就 return false：
    //   · 磨皮退回全帧（背景一起磨，CPU 顶到最高）；
    //   · 清晰 / 美白 / 红润 / 五官五项 / 脸内锐化全部落在 if (haveMask) 里，
    //     整片不执行 —— 面板 11 项只剩磨皮和全局锐化能用。
    // 离线脚本（core_probe / golden_capture）是显式调 ensureReady() 的，所以离线
    // 对拍一直是带掩码的：OBS 里跑的画面和验收过的画面根本不是一回事。
    bool preheat(std::string& err, bool& didInit) override {
        didInit = false;
        err.clear();
        const bool wasTried = faceTried_;
        if (!ensureReady(err)) return false;
        // 只有这一次真的做了加载才回 true —— 插件层靠它决定要不要打 init OK
        didInit = !wasTried;
        return true;
    }
    bool ready() const override { return true; }

    // 每实例发一个独立 slot。1.0.13.2 起不再恒返回 0 —— 恒返回 0 意味着
    // 「每实例一份上下文」只是句注释：两个滤镜实例会落在同一份检测态上。
    int acquireSlot(std::string& err) override {
        // 兜底：preheat 之外还有别的入口（宿主可能很久以后才建滤镜，或 preheat
        // 因故没跑到）。ensureReady 自身幂等，第二次调用只判一次 faceTried_。
        if (!ensureReady(err)) return -1;
        std::lock_guard<std::mutex> lk(slotsMtx_);
        for (int i = 0; i < kMaxSlots; i++) {
            if (slotUsed_[i]) continue;
            slotUsed_[i] = true;
            slots_[i] = DetState();      // 干净上下文
            initDetState(slots_[i]);
            return i;
        }
        err = "no free slot (kMaxSlots reached)";
        return -1;
    }
    void releaseSlot(int slot) override {
        if (slot < 0 || slot >= kMaxSlots) return;
        // 2026-11-10 代码审查 #1：worker 在 async_.m 之外直接引用 slots_[slot]
        // 跑 buildMaskInto()。重置上下文前必须先排空该 slot 的任务，否则两个
        // 线程会并发读写同一 DetState 里的 std::vector。
        {
            std::unique_lock<std::mutex> lk(async_.m);
            // (1) 撤销还没开工的任务
            if (async_.hasJob && async_.slot == slot) {
                async_.hasJob = false;
                async_.slot = -1;
            }
            // (2) 等该 slot 正在跑的任务收工（worker 收尾会 notify cvDone）。
            //     别的 slot 的任务不阻塞这里；quit 兜底防止引擎停止时死等。
            async_.cvDone.wait(lk, [this, slot] {
                return !async_.working || async_.runningSlot != slot || async_.quit;
            });
            // (3) 丢弃该 slot 已产出但还没被取走的结果。不清会让 submitAsync
            //     新增的 ready 门永久拒绝新任务，异步检测整体停摆。
            if (async_.ready && async_.slot == slot) {
                async_.ready = false;
                async_.slot = -1;
            }
        }
        std::lock_guard<std::mutex> lkSlots(slotsMtx_);
        slotUsed_[slot] = false;
        slots_[slot] = DetState();
    }
    void setDetectOptions(int, int, int) override {}

    bool process(int slot, const unsigned char* srcIn, unsigned char* dst,
                 int w, int h, const BeautySettings& s,
                 bool = true) override {
        // slot 越界（离线台架直调、或宿主没走 acquireSlot）一律兜到 0：
        // 宁可共用一份上下文，也不能读到 slots_ 之外。
        if (slot < 0 || slot >= kMaxSlots) slot = 0;
        DetState& S = slots_[slot];
        diagSlot_ = slot;
        BEAUTY_BIND_DET_ALL(S);
        const unsigned char* src = srcIn;
        if (!src || !dst || w <= 0 || h <= 0) return false;
        const size_t need = (size_t)w * (size_t)h * 4;
        frameNo_++;   // 时序 EMA 用它判断历史有没有断帧（见 detailEmaGen_ 的注释）
        // 1.0.9.0：分段耗时清零。**必须放在所有早退分支之前**，否则早退帧会
        // 把上一帧的分段值留在成员里，统计窗口就混进了不存在的耗时。
        for (int i = 0; i < 6; i++) st_[i] = 0.0;

        double blur = s.panel[P_BLUR];
        if (blur < 0) blur = 0;
        if (blur > 100) blur = 100;
        // 档位 → 强度的**饱和映射**：t_eff = t · (1 − sat·t²)
        //
        // 为什么需要它：参考实现的档位曲线在高段是饱和的（脸颊 50→75→100 对应
        // 63.1→48.0→35.5，每档增量递减），而我们换盒式低通后几乎是线性的
        // （64.9→43.7→23.4）—— 磨皮拉满时我们比参考实现狠 12 个百分点，脸会糊。
        // sat=0.16 是按参考实现五个档位反解出来的：
        //     面板   25     50     75     100
        //     等效  0.248  0.480  0.683  0.840   （目标 0.187/0.482/0.679/0.842）
        // 中高段几乎重合，25 档偏强约 3.7pp（磨得稍狠，观感上可接受）。
        //
        // ⚠️ 这条曲线是**单张素材拟合**的（goldens 里只有 face_src 一张脸）。
        // 素材补齐后必须复核，BEAUTY_BLUR_SAT=0 可一键关掉回到线性。
        const float tLin = (float)(blur / 100.0);
        const float t = tLin * (1.0f - g_cfg.blurSat * tLin * tLin);

        // 面板其余各项（0..1）。谁生效取决于它自己，不再被「磨皮是否为 0」绑死 ——
        // 旧实现在 t<=0 时直接逐字节返回，导致磨皮归零时美白/红润/全局锐化一起失效，
        // 与参考实现路线的行为不一致（那边 applyRegionEffects 在磨皮门控之外）。
        const float shFace = clampi01(s.panel[P_SHARPEN] / 100.0);
        const float shGlobal = clampi01(s.panel[P_GLOBAL_SHARP] / 100.0);
        // 脸内锐化原先以「磨皮开启」为前提（legacy_engine.cpp 的
        // wantFaceSharpen = panel[P_BLUR] > 0 && ...）。3.1.35 起取消这个前提：
        // 磨皮为 0 时脸内虽然没有「被磨掉的高频」可回填，但 dst≈src，
        // 回填一份原图细频就等于叠加锐化 —— 这正是用户拉「锐化」时的预期。
        // 旧行为实测：面板 100 档、其余全 0 → 改动量 0.000，滑块完全无效；
        // 同条件下 SDK 的 sharpen 是独立锐化器，改动量 1.012、细节 ×2.00。
        // 磨皮 > 0 时这条路径的行为逐字节不变（仍按 shFace 回填）。
        const bool wantFaceDetail = (shFace > 0.0f);
        const bool wantGlobalDetail = (shGlobal > 0.0f);
        // 3.1.22：磨皮后的基准细频回填。只在「开了磨皮、没开锐化、没开清晰」时
        // 生效 —— 用户自己开了锐化/清晰时，那两项的回填已经起作用了，
        // 再叠一层基准会把毛孔放大成噪声。
        // 基准回填用的实际磨皮强度（band 路径算出来的 I）。
        // I 是在磨皮分支内部定义的，这里先声明，等分支里算出来再回填。
        float blurRefillI = 0.0f;
        // 磨皮强度低于阈值就不回填：轻磨时几乎没削掉高频，
        // 回填带来的只是量化噪声（±1 灰阶），而参照实现那一档本来就几乎不动。
        //
        // 注意这里是**可变**的：真正的判定要等磨皮分支算出实际强度 I 之后
        // （band 分支里才赋值 blurRefillI）。先在这里求值的话，
        // blurRefillI 恒为 0，条件永远不成立 —— 这个坑踩过一次。
        bool wantBlurRefill = false;
        const bool wantTone = (s.panel[P_WHITEN] > 0.0 || s.panel[P_RED] > 0.0);
        // 清晰：原生 参考实现的 clarity 是**纯颜色变换**（S 形对比 + 轻微暖调），
        // 与磨皮毫无关系 —— panel 全 0、只下发 clarity=1.0 时改动量 6.16、
        // 细节 ×1.17（2026-10-30 实测，见 全项对齐_20261030/sdk_native.py）。
        // 3.1.19 之前这里要求 `t > 0`，于是「只开清晰、磨皮为 0」的画面零变化，
        // 离线矩阵直接判「欠 100%」。这条前提已删除。
        const bool wantClarity = (s.panel[P_CLARITY] > 0.0);
        // 五官局部五项：全部要求「有掩码 + 有脸」，所以也算掩码需求方。
        // 与参考实现一致地**不**以磨皮为前提（这是妆容层，磨皮关掉也该生效）。
        const bool wantRegion = (s.panel[P_THREED] > 0.0 ||
                                 s.panel[P_EYEBRIGHT] > 0.0 ||
                                 s.panel[P_POUCH] > 0.0 ||
                                 s.panel[P_NASOLABIAL] > 0.0 ||
                                 s.panel[P_DELSPOT] > 0.0);

        // 3.1.27：美形三项（瘦脸 / 大眼 / 下巴）—— 本项目第一次做**几何变形**。
        // 它与上面十项完全独立：不需要磨皮、不需要皮肤掩码，只要「人脸框 +
        // 关键点」。但它需要 faces_ 是新鲜的，而检测链是唯一更新途径，所以
        // 下面把它并进 needMask 的触发条件（而不是另起一条检测路径）。
        // BEAUTY_WARP=0 整体关闭 → 逐字节回到 3.1.26 的行为。
        static const bool warpEnabled = []() {
            const char *e = beauty_env("BEAUTY_WARP");
            return !(e && *e == '0');
        }();
        const bool wantWarp = warpEnabled &&
                              (s.panel[P_THIN_FACE] > 0.0 ||
                               s.panel[P_BIG_EYE] > 0.0 ||
                               s.panel[P_CHIN] > 0.0);

        // 3.1.35：早退条件补 wantFaceDetail。3.1.19 修「只开清晰、磨皮为 0
        // 零变化」时补过 wantClarity，但同一条链上漏了锐化 —— 于是把门控
        // 放开之后仍然被这里拦掉，实测仍是 0.000。两个条件必须成对维护。
        if (t <= 0.0f && !wantGlobalDetail && !wantFaceDetail && !wantTone &&
            !wantClarity && !wantRegion && !wantWarp) {
            // 面板全是 0：逐字节透传，零成本（与旧实现同一条路径）
            if (dst != src) memcpy(dst, src, need);
            if (alphaInEngine())
                forceOpaque(dst, (size_t)w * (size_t)h);   // 1.0.8.0：见 forceOpaque
            lastMs_ = 0.0;
            return true;
        }

        if (smooth_.size() < need) smooth_.resize(need);
        unsigned char* sm = &smooth_[0];

        const double t0 = nowMsCore();
        // 掩码用途变了：以前只有磨皮要它，现在美白/红润/脸内锐化都要。
        const bool needMask = (t > 0.0f) || wantFaceDetail || wantTone ||
                              wantClarity || wantRegion || wantWarp;
        // 先更新掩码再磨皮：ROI 裁剪要用掩码的包围盒。顺序反了的话，
        // 磨皮那一遍全帧算完才知道 ROI，等于白算。
        const bool haveMask = needMask ? updateMask(slot, src, w, h) : false;
        if (haveMask) everHadMask_ = true;
        st_[0] = nowMsCore() - t0;      // 分段 0：检测 + 掩码
        double tSt = nowMsCore();       // 以下各段的公共起点

        // 1.0.12.0（A6）：色调整帧分支会把 A 一并置 255，届时末尾的 forceOpaque
        // 可以省掉。标志由 toneColor 的返回值给出（只有「整帧 + 整数表」分支为
        // true —— 那时它本来就要逐像素写 R/G/B，顺手写 A 是零边际成本）。
        bool alphaDone = false;

        // 3.1.21：**首次启用**这几帧直接透传，不退回全帧磨皮。
        //
        // 打开开关的那一刻异步检测还没跑完（模型 15 ms + worker 排队），掩码是空的。
        // 旧逻辑此时退回「全帧磨皮」，代价是双份的：
        //   · 算力：1080p 全帧双边 ~30 ms，而稳态只磨脸（掩码 16%）~18 ms，
        //     首帧必超 30fps 预算（实测首帧 42 ms vs 稳态 19 ms）；
        //   · 观感：整幅画面先糊一下，等掩码到了再跳回「只磨脸」——每次开开关
        //     都闪一次背景。
        // 一旦得到过掩码就不再走这条分支 ⇒ 交给下面的「无脸透传」（3.1.40）
        // 与「全帧兜底」按 lastFaces_ 分流。
        if (needMask && !haveMask && faceOk_ && !everHadMask_) {
            if (dst != src) memcpy(dst, src, need);
            if (alphaInEngine())
                forceOpaque(dst, (size_t)w * (size_t)h);   // 1.0.8.0：见 forceOpaque
            lastMs_ = 0.0;
            return true;
        }

        // 3.1.40：**确认本帧没人 → 直接透传**，不再退回全帧磨皮。
        //
        // 旧行为（≤ 3.1.39）在「曾经检测到过脸、之后人走开」时会一直走全帧兜底：
        // 磨皮核把空掩码当「全皮肤」（m = 255）、ROI 也放开成全帧，于是 1080p
        // 磨皮段从「只磨 ROI（12.6%）约 5~7 ms」涨到全帧量级（720p 全帧带通
        // 实测 10.3 ms，按像素比推算 1080p ≈ 23 ms），**而这些像素随后一个都
        // 用不到**——色调/清晰/五官/细节全部挂在 haveMask 之下，美形要 faces_
        // 非空（见 wantWarp 的调用点）。观感上还多一个副作用：背景、衣物、
        // 商品被一起磨糊。
        //
        // 判据四条必须同时成立，缺一条都会把「暂时算不出来」误判成「没人」：
        //   ① faceOk_     模型可用（模型没加载时 updateMask 第一句就 return false，
        //                 此时跳过等于「检测坏了 = 完全没美颜」，比慢更难排查）；
        //   ② everHadMask_ 历史上真的得到过掩码（否则上面那条分支已经处理了）；
        //   ③ lastFaces_ == 0  最近一次检测**跑完**且一张脸都没有；
        //   ④ faceErr_ 里没有 "err=" —— 那是推理/模型错误的标记，不是「没脸」。
        //      onDetectFailed 对这两种情况写的是同一条 lastFaces_ = 0，只能靠
        //      错误串区分；宁可多算（退回全帧），也不要静默不磨。
        //
        // 迟滞不用自己加：kMaskHold = 8（1.0.13.6 由 6 提到 8）已让「人走出去」
        // 先沿用旧掩码若干次检测，之后才进这里；人走回画面时检出当帧即恢复，不会闪。
        // BEAUTY_NOFACE_SKIP=0 逐字节回到 3.1.39 的行为。
        if (g_cfg.noFaceSkip && needMask && !haveMask && faceOk_ && everHadMask_ &&
            lastFaces_ == 0 && faceErr_.find("err=") == std::string::npos) {
            if (dst != src) memcpy(dst, src, need);
            if (alphaInEngine())
                forceOpaque(dst, (size_t)w * (size_t)h);   // 1.0.8.0：见 forceOpaque
            lastMs_ = 0.0;
            g_noFaceFrames++;
            return true;
        }

        // 3.1.10 掩码↔帧对齐：只在「worker 的结果刚到」这一帧把它描述的原始帧
        // 拿来处理，掩码与画面就逐像素同源了。没赶上（worker 晚一帧）就照旧用
        // 当前帧 + 旧掩码 —— 停顿一次比一帧淡边更显眼。
        if (alignOn_ && maskFresh_ && haveMask && heldFrame_.size() == need) {
            // 1.0.13.8：对齐加「画面几乎没动」这道门。
            //
            // 对齐的本意是让掩码与它描述的那一帧逐像素同源（3.1.10）。但它的实现
            // 是「有结果 → 拿上一帧画面输出；没结果 → 拿当前帧」，于是 worker 一忙
            // 一闲，输出就在两帧之间来回跳。实测（face_src 每帧 +1° 旋转，异步检测）：
            //
            //   对齐命中帧 meanD 1.67   未命中帧 7.09   差 5.4 灰阶
            //   0→57° 全程这个差值一直在，肉眼就是「卡一帧 / 闪一下」
            //   BEAUTY_MASK_ALIGN=0 时同一段扫描 meanD 恒定 1.3~1.7，跳变消失
            //
            // 所以判据改成两条：**有新鲜掩码 且 画面几乎没动** 才对齐。
            //   · 静止：两帧本来就一样，对齐零代价，还保住了「掩码与画面同源」；
            //   · 运动：宁可让掩码晚一帧，也不要画面重复一帧 —— 重复帧是硬的，
            //     掩码晚一帧在皮肤大块区域里根本看不出来。
            // 歪头过渡期正是运动最大、worker 最慢（探测帧多两次推理）的时候，
            // 这条门正好落在最需要它的地方。
            const bool sameish =
                (g_cfg.alignDiff <= 0.0f) ||
                frameNearlySame(src, &heldFrame_[0], w, h,
                                (double)g_cfg.alignDiff);
            if (sameish) {
                src = &heldFrame_[0];
                g_alignUsed++;
            } else {
                g_alignRejected++;
            }
        }
        g_alignTotal++;
        maskFresh_ = false;   // 新鲜度只对「到货那帧」有效，过了这帧就作废

        bool didSurface3 = false;
        if (t > 0.0f) {
            if (g_cfg.smoothModel == 1) {
                // ---- surface3：三层表面模糊（C22）------------------------
                // 档位曲线用 参考实现的 I = min(1, k·t)（不是 legacy 的饱和曲线），
                // 所以这里用 tLin 而不是上面的 t。
                beautycore::Surface3Params sp;
                // 半径随档位线性增长（C22 §4），并按**人脸宽度归一化**：
                // 真机 1080p 素材脸宽 532px 上拟合出 r(50)≈8、r(100)≈14；
                // face_src 640×394 的脸只有 111px，等效半径就是它的 1/4.8。
                // 不做归一化的话，小脸会被大半径糊成一片（face_src 100 档
                // 实测细纹理 70.2% vs参考实现 75.7%，归一化后 72.4%）。
                float scale = 1.0f;
                if (!faces_.empty()) {
                    float fw = 0.0f;
                    for (size_t i = 0; i < faces_.size(); i++)
                        if (faces_[i].w > fw) fw = faces_[i].w;
                    if (fw > 8.0f) {
                        scale = fw / 532.0f;          // 532 = 拟合素材的脸宽
                        if (scale < 0.20f) scale = 0.20f;
                        if (scale > 2.50f) scale = 2.50f;
                    }
                }
                int r1 = (int)((g_cfg.s3R0 + (g_cfg.s3R1 - g_cfg.s3R0) * tLin)
                               * scale + 0.5f);
                int r2 = (int)((g_cfg.s3R0 + (g_cfg.s3R2 - g_cfg.s3R0) * tLin)
                               * scale + 0.5f);
                sp.r1 = (r1 < 1) ? 1 : r1;
                sp.r2 = (r2 < 1) ? 1 : r2;
                sp.it1 = g_cfg.s3It1;
                sp.it2 = g_cfg.s3It2;
                sp.thr1 = g_cfg.s3Thr1;
                sp.thr2 = g_cfg.s3Thr2;
                // intensity = mix(t·K, 1.0, step(0.7, t))
                //   step 的自变量是**乘之前的 tLin** —— GLSL 的 mix 三个参数先
                //   求值，所以右式的 intensity 还是旧值。因为 K = 1/0.7，这一行
                //   在数值上等价于 min(1, tLin·K)，但保留原式写法以免后人再"优化"掉。
                float I;
                if (g_cfg.lvTable) {
                    // 3.1.18：档位查表。旧式 min(1, t/0.7) 在 t≥0.7 就恒为 1，
                    // 75 与 100 档输出逐字节相同 —— 那是「拉满没反应」的根因。
                    I = g_cfg.lvShape ? lvLerp7(g_cfg.lvI7, tLin)
                                      : lvLerp5(g_cfg.lvI, tLin);
                } else {
                    I = (tLin >= g_cfg.s3ESat) ? 1.0f : (tLin * g_cfg.s3K);
                }
                if (I > 1.0f) I = 1.0f;
                sp.I = I;
                // evenfactor = mix(E0, intensity − E0, step(0.6, intensity))
                // 三段：[0,0.42] 恒 0.3；(0.42,0.70] 升到 0.7；[0.70,1] 恒 0.7。
                float e;
                if (g_cfg.s3EFix >= 0.0f) {
                    e = g_cfg.s3EFix;
                } else if (g_cfg.lvTable) {
                    e = lvLerp5(g_cfg.lvE, tLin);
                } else {
                    e = (I >= g_cfg.s3EThr) ? (I - g_cfg.s3E0) : g_cfg.s3E0;
                }
                if (e < 0.0f) e = 0.0f;
                sp.e = e;
                sp.protectK = g_cfg.s3EyeK;

                beautycore::RoiRect s3roi;
                if (haveMask && g_cfg.roi && !bounds_.empty()) {
                    s3roi = bounds_;
                } else {
                    s3roi.x0 = 0; s3roi.y0 = 0; s3roi.x1 = w; s3roi.y1 = h;
                }
                const unsigned char* pr3 =
                    (haveMask && protect_.size() == (size_t)w * h)
                        ? &protect_[0] : nullptr;
                if (g_cfg.s3Band) {
                    // 双尺度带通 + 振幅门控（第 2 批-B）。与 25 tap 路径的差别
                    // 只有「两个低频层怎么算」——B1/B2 换成两个不同尺度的模糊，
                    // 外加一道振幅门控；合成段 I/e/skin/eye 仍逐行同口径。
                    // s3R0/R1/R2、s3Sx/s3Sy、s3YF1/YF2 在这条路上**都不参与**。
                    beautycore::BandParams bp;
                    bp.T = g_cfg.lvTable ? lvLerp5(g_cfg.lvT, tLin) : g_cfg.s3BandT;
                    bp.gwp = g_cfg.s3Gwp;
                    bp.halfRes = g_cfg.s3Half;
                    bp.I = I;
                    blurRefillI = I;
                    // I 出来了才能判定要不要做基准回填（见 wantBlurRefill 的注释）
                    wantBlurRefill = (t > 0.0f) && (g_cfg.blurRefill > 0.0f) &&
                                     (s.panel[P_SHARPEN] <= 0.0) &&
                                     (s.panel[P_CLARITY] <= 0.0) &&
                                     (blurRefillI >= g_cfg.blurRefillMinI);
                    bp.e = e;
                    bp.protectK = g_cfg.s3EyeK;
                    beautycore::surface3RgbBand(src, dst, w, h,
                                                haveMask ? &mask_[0] : nullptr,
                                                pr3, bp, s3roi, g_cfg.threads,
                                                s3ScratchA_);
                } else if (g_cfg.s3Tap25) {
                    // 25 tap 表面模糊（第 2 批 #5/#6/#7）。与下面盒式路径的
                    // 唯一差别是「两个低频层怎么算」；合成段 I/e/skin/eye 逐行相同。
                    // 半径参数 s3R0/R1/R2 在这条路上**完全不参与** —— 真结构里
                    // 核是固定的，档位只改 I 和 e。fw/532 的归一化也一并作废。
                    beautycore::Surface25Params p25;
                    p25.sx = g_cfg.s3Sx;
                    p25.sy = g_cfg.s3Sy;
                    p25.yFactor1 = g_cfg.s3YF1;
                    p25.yFactor2 = g_cfg.s3YF2;
                    p25.halfRes = g_cfg.s3Half;
                    p25.I = I;
                    p25.e = e;
                    p25.protectK = g_cfg.s3EyeK;
                    beautycore::surface3Rgb25(src, dst, w, h,
                                              haveMask ? &mask_[0] : nullptr, pr3,
                                              p25, s3roi, g_cfg.threads,
                                              s3ScratchA_);
                } else {
                    beautycore::surface3Rgb(src, dst, w, h,
                                            haveMask ? &mask_[0] : nullptr, pr3,
                                            sp, s3roi, g_cfg.threads,
                                            s3ScratchA_, s3ScratchB_);
                }
                didSurface3 = true;
            } else if (g_cfg.down > 1) {
                // 降采样路径已实测失败（档位曲线误差 27+），只为复现当年结论保留
                beautycore::bilateralRgbaDown(src, sm, w, h,
                                              g_cfg.radius, g_cfg.sigmaSpace,
                                              g_cfg.sigmaColor, g_cfg.down);
            } else if (haveMask && g_cfg.roi && !bounds_.empty() && g_cfg.freqMode) {
                // 高低频分离：低频用大半径高斯，只压小幅度高频，低频结构原样保留。
                // strength 传 100（全强度），面板档位由后面的 blendWithMask 按 t 缩放。
                beautycore::FreqParams fp = makeFreqParams();
                beautycore::highLowSmooth(src, sm, w, h, fp, bounds_, g_cfg.threads,
                                          lowBuf_, scratch_, guideScratch_);
            } else if (haveMask && g_cfg.roi && !bounds_.empty()) {
                // 只磨掩码包围盒。逐像素独立，结果与全帧跑逐字节一致，纯省算力。
                beautycore::bilateralRgbaRoi(src, sm, w, h,
                                             g_cfg.radius, g_cfg.sigmaSpace,
                                             g_cfg.sigmaColor,
                                             bounds_, g_cfg.threads);
            } else if (g_cfg.freqMode) {
                // 没有可用掩码（模型没加载 / 这一轮没检出脸）或关掉 ROI 对照时，
                // 同样走高低频，只是范围放到全图 —— 否则「ROI 开/关」对比的是
                // 两种不同算法，等价性测试就失去意义了。
                beautycore::FreqParams fp = makeFreqParams();
                beautycore::RoiRect full;
                full.x0 = 0; full.y0 = 0; full.x1 = w; full.y1 = h;
                beautycore::highLowSmooth(src, sm, w, h, fp, full, g_cfg.threads,
                                          lowBuf_, scratch_, guideScratch_);
            } else {
                // 没有可用掩码（模型没加载 / 这一轮没检出脸）时退回全帧：
                // 宁可多算，也不能出现「有脸却不磨」。
                beautycore::bilateralRgba(src, sm, w, h,
                                          g_cfg.radius, g_cfg.sigmaSpace,
                                          g_cfg.sigmaColor, g_cfg.threads);
            }

            if (didSurface3) {
                // dst 已由 surface3Rgb 写满（含 I / e / skin / eye 四步），
                // 不能再走 blendWithMask —— 否则 skin 与 t 会被应用两遍。
            } else if (haveMask) {
                const unsigned char* pr =
                    (protect_.size() == (size_t)w * h) ? &protect_[0] : nullptr;
                blendWithMask(src, sm, dst, w, h, t, &mask_[0], pr, g_cfg.protectK);
            } else {
                beautycore::mixRgba(src, sm, dst, w, h, t);
            }
        } else {
            // 磨皮为 0：其余各项仍要在原图基础上生效，所以先把原图铺到 dst
            if (dst != src) memcpy(dst, src, need);
        }

        st_[1] = nowMsCore() - tSt;     // 分段 1：磨皮（含混合）
        tSt = nowMsCore();              // 1.0.9.0

        if (haveMask) {
            // 清晰 / 美白 / 红润：三项合并成一次遍历（toneColor）。
            //
            // 2026-10-30 起三项都改成**照抄原生 参考实现的逐通道查找表**，不再有各自
            // 的拟合公式。理由：把它们拆开量化后发现"箱内 σ"只有零点几灰阶
            // （clarity 0.08~0.27 / color_level 0.36~1.24 / red_level 0.73）——
            // 即它们与空间位置、邻域无关，是纯颜色变换。改表即可对齐到量化误差。
            //
            // 顺序：清晰 → 美白 → 红润。先抬对比再提亮，否则提亮会把对比压平。
            // 输入用 dst（磨皮之后）而不是 src：拿原图算会把刚磨掉的瑕疵加回来。
            //
            // 旧实现（12px 中频回填当"清晰"）保留在 BEAUTY_CLARITY_LEGACY=1 下，
            // 只作 A/B 对照，不再走默认路径。
            static const bool legacyClarity =
                (beauty_env("BEAUTY_CLARITY_LEGACY") != nullptr);
            const float cv = wantClarity ? (float)(s.panel[P_CLARITY] / 100.0) : 0.0f;
            const float wv = (float)(s.panel[P_WHITEN] / 100.0);
            const float rv = (float)(s.panel[P_RED] / 100.0);
            if (legacyClarity) {
                if (cv > 0.0f) {
                    beautycore::ClarityParams cp;
                    cp.gain = cv * g_cfg.clarityMax;
                    cp.radius = g_cfg.clarityRadius;
                    cp.kneeLo = g_cfg.clarityKneeLo;
                    cp.kneeHi = g_cfg.clarityKneeHi;
                    beautycore::clarityRgb(dst, w, h, &mask_[0], bounds_, cp,
                                           g_cfg.threads, clarityScratch_);
                }
                if (wv > 0.0f || rv > 0.0f) {
                    beautycore::toneWhitenRosy(dst, w, h, &mask_[0], bounds_,
                                               wv, rv, g_cfg.threads);
                }
            } else {
                alphaDone = beautycore::toneColor(dst, w, h, &mask_[0], bounds_,
                                                  cv, wv, rv, g_cfg.threads);
            }

            // 五官局部五项：妆容层，放在磨皮与美白之后（理由见 applyFaceRegions
            // 的注释）。祛斑痘也在里面 —— 它要「修掉刚磨过之后还剩下的斑点」。
            if (wantRegion) applyFaceRegions(S, dst, w, h, s);
        }

        st_[2] = nowMsCore() - tSt;     // 分段 2：色调（清晰/美白/红润）+ 五官
        tSt = nowMsCore();              // 1.0.9.0

        // ---- 细节回填（锐化 / 全局锐化）------------------------------------
        // 放在整条链的最后一个「加法」位置，理由：
        //   · 亮度平面取自 **src（原图）**，所以磨皮抹掉多少都不影响可回填的量；
        //   · 加在 dst 上，不会再被磨皮平均掉，也不会被美白曲线压平；
        //   · 全局锐化在「没有掩码」时也要跑 —— 否则掩码一丢，背景锐度跟着跳档，
        //     这正是参考实现 3.0.13 修过的那个 bug，core 不能重演。
        if (wantFaceDetail || wantGlobalDetail || wantBlurRefill) {
            // 运动判据每帧算一次（4×4 抽样，720p 约 5.7 万次比较，可忽略）。
            // 只在真的要跑锐化时才算 —— 锐化关着就没有噪点放大问题。
            const double motion = updateMotion(S, src, w, h);
            const float beta = emaBeta(motion);

            beautycore::DetailParams dp;
            if (wantFaceDetail && haveMask) {
                dp.fine = shFace;
                dp.mid = shFace * g_cfg.detailMidGain;
                if (dp.mid > 3.0f) dp.mid = 3.0f;
                // 3.1.35：磨皮=0 时是「纯锐化」语义（dst≈src，回填 src 高频 = 叠加锐化）。
                // 这条路不能用中频带（会在全脸皮肤产生与档位无关的固定基底），
                // 也不能用默认细频阈值（会把小幅度高频削光），所以走专属参数：
                //   细频满增益 × faceSharpGain、中频关、阈值放开到 faceSharpThrFine。
                // 磨皮>0 时是「回填被磨掉的高频」，增益沿历史曲线不变。
                if (t <= 0.0f) {
                    dp.fine = shFace * g_cfg.faceSharpGain;
                    dp.mid = 0.0f;
                    dp.thrFine = g_cfg.faceSharpThrFine;
                }
            }
            if (wantBlurRefill && haveMask) {
                // 基准回填：只还细频，不碰中频。
                // 中频是「我方比参照多出来的那部分能量」，还回去只会更糟。
                //
                // 比例随**实际磨皮强度 I** 缩放：磨皮削掉的高频本来就正比于 I，
                // 不乘 I 的话低档会把原图细节放大成超过原图
                // （实测 25 档 dret 从 1.000 涨到 1.083、改动量 0.000→0.104）。
                //
                // delta 模式（加回「原图细频 − dst 细频」）实测更保守：
                // 100 档细节保留只从 0.737 到 0.761（目标 0.835），因为
                // 被磨掉的细频差值本身就在 1 灰阶上下，被软阈值削掉大半。
                // 所以生产用「I 缩放 + 低档不启用」，delta 留作开关备用。
                dp.fine = g_cfg.blurRefill * blurRefillI;
                dp.mid = 0.0f;
                dp.deltaRefill = g_cfg.blurRefillDelta != 0;
            }
            if (wantGlobalDetail) {
                // 全局锐化用**自己**的中频/细频基准（3.1.22 从 detailMidGain 拆出）。
                // 参照路径那边也是两条独立曲线（见 g_cfg.globalMidGain 的注释）。
                dp.globalFine = shGlobal * g_cfg.globalFineGain;
                dp.globalMid = shGlobal * g_cfg.globalMidGain;
                if (dp.globalMid > 3.0f) dp.globalMid = 3.0f;
                dp.thrFineGlobal = g_cfg.globalThrFine;
                dp.thrMidGlobal = g_cfg.globalThrMid;
            }
            // 基准回填用自己的一套细频阈值（默认 0.8，比锐化那套的 3.0 低得多）：
            // 磨皮要还的就是「小幅值细频」，而锐化要防的是「噪点被放大」，
            // 两者的取舍正好相反，所以不能共用一个阈值。
            dp.thrFine = wantBlurRefill ? g_cfg.blurRefillThr : g_cfg.detailThrFine;

            // 有全局档就整帧跑（掩码只决定「用哪一档权重」）；否则只跑掩码包围盒。
            beautycore::RoiRect droi;
            if (wantGlobalDetail) {
                droi.x0 = 0; droi.y0 = 0; droi.x1 = w; droi.y1 = h;
            } else {
                droi = bounds_;
            }
            if (!droi.empty() && (dp.fine > 0.0f || dp.mid > 0.0f ||
                                  dp.globalFine > 0.0f || dp.globalMid > 0.0f)) {
                // ---- 时序 EMA 的上下文 --------------------------------------
                // lumT 传 nullptr 时 detailRefill 走原路径，逐字节等于 0.7.1。
                // 所以 BEAUTY_EMA=0 是「完全关闭」而不是「beta=1 的近似关闭」。
                beautycore::DetailEma ema;
                if (g_cfg.emaOn) {
                    const size_t np = (size_t)w * (size_t)h;
                    if (detailLumT_.size() != np) {
                        detailLumT_.assign(np, 0);
                        detailEmaReset_ = true;   // 尺寸变了，历史整片作废
                    }
                    // 上一帧没写历史（断帧）→ 这一帧必须用当前帧重置，
                    // 否则会把陈旧位置的亮度混进来。
                    if (detailEmaGen_ + 1 != frameNo_) detailEmaReset_ = true;
                    ema.lumT = &detailLumT_[0];
                    ema.beta = beta;
                    ema.reset = detailEmaReset_;
                    detailEmaReset_ = false;
                }
                beautycore::detailRefill(src, dst, w, h,
                                         haveMask ? &mask_[0] : nullptr,
                                         droi, dp, g_cfg.threads, detailScratch_,
                                         ema);
                detailEmaGen_ = frameNo_;
            }
        }

        st_[3] = nowMsCore() - tSt;     // 分段 3：细节回填（锐化/清晰/基准回填）
        tSt = nowMsCore();              // 1.0.9.0

        // ---- 美形三项（3.1.27）--------------------------------------------
        // 为什么放在**最末端**而不是最前面：
        //   · 前面十项都是逐像素颜色运算，先上色再变形与先变形再上色在颜色上
        //     等价（变形只是重采样，不改变颜色本身）；
        //   · 皮肤掩码 / ROI 包围盒 / 五官椭圆全是异步在**原图**上算的。放到
        //     前面就必须把「掩码↔画面同源」那套对齐逻辑重做一遍，风险大得多；
        //   · 放末端只需一次重采样，不碰任何已验收过的路径。
        // 代价：位移场的几何基准来自**原图**的人脸框，如果一帧内脸动得很快，
        // 变形会比磨皮晚一帧生效。实测 30fps 下不可见（与掩码滞后同源）。
        if (wantWarp && !faces_.empty()) {
            beautycore::WarpParams wp;
            wp.thin = clampi01((float)(s.panel[P_THIN_FACE] / 100.0));
            wp.eye = clampi01((float)(s.panel[P_BIG_EYE] / 100.0));
            wp.chin = clampi01((float)(s.panel[P_CHIN] / 100.0));
            if (wp.thin > 0.0f || wp.eye > 0.0f || wp.chin > 0.0f) {
                // 逐脸处理。多张脸时 ROI 互不重叠（检测框本身就不会大面积交叠），
                // 所以串行就地修改是安全的。
                for (size_t i = 0; i < faces_.size(); i++)
                    beautycore::warpFace(dst, w, h, faces_[i], wp, warpScratch_);
            }
        }

        // 1.0.8.0：A 通道强制不透明，原来在插件层（obs-beauty.cpp）逐像素跑，
        // 挪到这里是因为此时 dst 刚被本帧写过、还在 cache 里。计进 lastMs_
        // 是诚实的做法 —— 它确实是本帧的成本，只是从「上传段」挪到了「引擎段」。
        //
        // 1.0.12.0（A6）：如果色调整帧分支已经把 A 写成 255（alphaDone），这里
        // 就跳过 —— 那一遍是完整的整帧读改写，省掉它等于白赚 0.7 ms。
        // 中间隔着 applyFaceRegions、细节回填、warpFace 三道，都只写 RGB
        // （beauty_freq/smooth 里对 A 全是 `dst[o+3] = src[o+3]` 的保持写法，
        // warpFace 对 4 个通道一起做双线性插值，255 插值后仍是 255），所以
        // 「色调写过的 255」能一直活到这一步。
        if (alphaInEngine() && !alphaDone) forceOpaque(dst, (size_t)w * (size_t)h);
        st_[4] = nowMsCore() - tSt;     // 分段 4：美形（warp）
        st_[5] = 0.0;                   // 分段 5：其它（保留位）

        lastMs_ = nowMsCore() - t0;
        return true;
    }

    int lastFaces() const override { return slots_[diagSlot_].lastFaces; }
    bool regionActive() const override { return faceOk_; }
    double lastCoreMs() const override { return slots_[diagSlot_].lastMs; }
    void lastStageMs(double* out6) const override {
        // 1.0.13.3：分段耗时随上下文走，读的是「刚刚处理过的那一路」。
        // 原先恒读同一个成员，多实例下 A 的耗时会被 B 覆盖。
        if (!out6) return;
        const DetState& d = slots_[diagSlot_];
        for (int i = 0; i < 6; i++) out6[i] = d.st[i];
    }
    void lastRoi(int* rw, int* rh, int* px) const override {
        const DetState& d = slots_[diagSlot_];
        if (rw) *rw = d.bounds.width();
        if (rh) *rh = d.bounds.y1 - d.bounds.y0;
        if (px) *px = d.maskPixels;
    }
    const char* lastErr() const override {
        if (!faceLoadErr_.empty()) return faceLoadErr_.c_str();
        return slots_[diagSlot_].faceErr.c_str();
    }
    int itemId() const override { return 0; }
    unsigned long ownerThread() const override { return (unsigned long)GetCurrentThreadId(); }

    // 仅供离线对拍：把「最近一次检测得到的人脸几何」写进文本。
    //
    // 存在的理由：美形（瘦脸 / 下巴）的位移场完全由这一个框 + 5 个关键点决定，
    // 判断「形变位置对不对」必须先看到框在哪、关键点在哪。没有这个出口时，
    // 只能靠改动区反推几何，误差比框本身还大。
    int dumpFaceInfo(int slot, char* buf, int cap) const {
        if (!buf || cap <= 0) return -1;
        buf[0] = 0;
        if (slot < 0 || slot >= kMaxSlots) slot = 0;
        const DetState& S = slots_[slot];
        const int n = (int)S.faces.size();
        int used = snprintf(buf, (size_t)cap, "faces=%d", n);
        for (int i = 0; i < n && i < 4; i++) {
            const beautycore::FaceBox& f = S.faces[i];
            if (used < 0 || used >= cap) break;
            used += snprintf(buf + used, (size_t)(cap - used),
                             " | f%d x=%.1f y=%.1f w=%.1f h=%.1f roll=%.1f"
                             " rw=%.1f rh=%.1f kps=%.1f,%.1f %.1f,%.1f %.1f,%.1f"
                             " %.1f,%.1f %.1f,%.1f hasKps=%d",
                             i, f.x, f.y, f.w, f.h, f.roll, f.rw, f.rh,
                             f.kps[0], f.kps[1], f.kps[2], f.kps[3],
                             f.kps[4], f.kps[5], f.kps[6], f.kps[7],
                             f.kps[8], f.kps[9], f.hasKps ? 1 : 0);
        }
        return n;
    }

    // 仅供离线对拍：强制重算一次掩码并拷出，不改磨皮状态、不动时序。
    // 返回 false 表示本帧没有可用掩码，此时 out 全 0。
    bool computeMaskForDump(int slot, const unsigned char* src, int w, int h,
                            unsigned char* out) {
        if (!out) return false;
        if (slot < 0 || slot >= kMaxSlots) slot = 0;
        // 离线对拍必须确定性：停掉 worker，并且以后都走同步路径。
        // 异步下「第 k 帧用哪份掩码」取决于线程调度，哈希会飘。
        stopAsync();
        asyncOn_ = false;
        DetState& S = slots_[slot];
        BEAUTY_BIND_DET_ALL(S);
        maskAge_ = 999;                 // 让它走重算分支，不吃缓存
        const bool ok = updateMask(slot, src, w, h);
        if (!ok) {
            memset(out, 0, (size_t)w * h);
            return false;
        }
        memcpy(out, &mask_[0], (size_t)w * h);
        return true;
    }

    void release() override {
        stopAsync();          // 先停 worker，否则它可能正在用 face_
        face_.release();
        faceTried_ = false;
        faceOk_ = false;      // 模型已经卸了，别再让 process() 以为掩码路径可用
        // 关闭开关后再开，应当是「干净的一次启用」：掩码重新从零开始。
        // release() 是模块级收尾，之后本进程不再使用，所以所有 slot 一起清。
        for (int i = 0; i < kMaxSlots; i++) {
            slots_[i].maskValid = false;
            slots_[i].everHadMask = false;
            slots_[i].maskAge = 999;
            slots_[i].heldFrame.clear();
            slots_[i].maskFresh = false;
            slots_[i].mask = std::vector<unsigned char>();
            slots_[i].protect = std::vector<unsigned char>();
        }
        // 3.1.21：持久线程池也要收掉。否则 OBS 卸载滤镜后 worker 线程还在，
        // 它们持有本 DLL 里的代码地址 —— 模块卸载时就是一次野跳转。
        beautycore::poolShutdown();
    }

private:
    // 首帧预热点（3.1.21）。
    //
    // 「开关美颜时预览窗卡一下」的根因不是稳态算力，而是**第一帧**要额外付三笔
    // 一次性成本，全部压在渲染线程上：
    //   ① smooth_ 这块 1080p 8.3MB 的工作缓冲要 malloc + 逐页缺页；
    //   ② 持久线程池的 7 个 worker 要创建、栈要缺页；
    //   ③ ORT 的第一次推理要分配 arena 并选定 kernel。
    // 实测 1080p 首帧 43.2 ms vs 稳态 21 ms，多出来的 22 ms 就是这三笔（外加
    // 首帧必然要跑的一次检测）。把它们挪到模块加载阶段（那里本来就要花 200 ms
    // 加载模型），用户开开关时就是纯稳态开销。
    //
    // 注意**不跑完整的 process()**：那会把肤色自适应中心（g_skinCb/Cr）按合成
    // 帧算歪，真机前几帧的掩码跟着错。这里只碰纯缓存与纯推理。
    void warmUp() {
        if (beauty_env("BEAUTY_NO_PREWARM")) return;   // A/B 用：跳过预热看首帧原始成本
        const int w = 1920, h = 1080;
        const size_t need = (size_t)w * h * 4;
        const size_t px = (size_t)w * h;
        if (smooth_.size() < need) {
            smooth_.assign(need, 0);   // 分配 + 逐页触碰（等价于首帧那次缺页）
        }
        // 低频/中间缓冲：默认路径未必用到，但一旦用到就是 8MB 级的首次缺页，
        // 这里先垫上（纯 scratch，写 0 不影响任何结果）。
        if (lowBuf_.size() < need) lowBuf_.assign(need, 0);
        if (scratch_.size() < need) scratch_.assign(need, 0);
        // 掩码与五官保护区同理。maskAge_ 显式压回 999，保证首帧仍然走重算分支，
        // 不会因为「缓冲已经有内容」而误用一份全 0 的掩码。
        // 只垫 0 号上下文：预热是「让首帧少付缺页钱」，其它 slot 创建时会
        // 各自按真实分辨率分配，垫 1080p 反而白占内存。
        if (slots_[0].mask.size() != px) {
            slots_[0].mask.assign(px, 0);
            slots_[0].protect.assign(px, 0);
            slots_[0].maskAge = 999;
        }
        // 池提前建好；数量取和 process 里同一口径（≤8，且不超过核数）
        unsigned hc = std::thread::hardware_concurrency();
        int n = (hc == 0) ? 4 : (int)hc;
        if (n > 8) n = 8;
        beautycore::poolReserve(n);
        // ORT 首次推理：只走人脸检测，输入用 640×360 的合成灰帧（模型内部本来
        // 就缩到 640×640，用 1080p 只是白付 8MB 的分配）。
        if (faceOk_) {
            std::vector<unsigned char> fake((size_t)640 * 360 * 4, 128);
            std::vector<beautycore::FaceBox> dummy;
            std::string e;
            face_.detect(&fake[0], 640, 360, dummy, e, 0.9f, 0.3f, 4);
        }
    }

    // 生成「肤色 ∩ 人脸框」掩码。返回 false 表示本帧没有可用掩码。
    //
    // 这个函数只做三件轻活：① 收走 worker 算好的结果（O(1) swap）；② worker 空闲
    // 时把本帧提交出去；③ 沿用上一份掩码。**检测本身不在这里跑** —— 1080p 下
    // YuNet 一次约 15ms，压在渲染线程上就是 60fps 每 4 帧掉 1 帧。
    bool updateMask(int slot, const unsigned char* src, int w, int h) {
        if (!faceOk_) return false;
        DetState& S = slots_[slot];
        BEAUTY_BIND_DET_ALL(S);
        if (mask_.size() != (size_t)w * h) {
            mask_.assign((size_t)w * h, 0);
            protect_.assign((size_t)w * h, 0);
            maskAge_ = 999;
            maskValid_ = false;      // 换分辨率等于重来：别拿旧尺寸的掩码凑合
            everHadMask_ = false;    // 新尺寸下第一帧按「透传」处理，见 process()
            // 1.0.0.3 真机崩溃修复：换尺寸时 bounds_/faces_ 还是旧坐标系的。
            // bounds_ 是 mask 的包围盒，会被 toneColor / highLowSmooth 等下游
            // 按 (y*w+x) 遍历 —— 旧坐标系 bounds 配新 w 直接越界（真机
            // e2e 已 2/2 复现 0xc0000005）。旋转 -90°（宽高互换、像素总数
            // 相同）走不进这个 if，是同族问题的另一入口，见 design 文档。
            bounds_ = beautycore::RoiRect();
            faces_.clear();
        }

        if (asyncOn_) {
            startAsyncIfNeeded();
            collectAsync(slot, w, h);       // 每帧都收，不受周期限制
            // 到了重算周期：提交一帧给 worker。周期 0 = 每帧提交。
            // worker 忙时 submitAsync 会自己放弃这一轮（见它的注释），
            // 所以 60fps + 1080p 这种「推理 15ms / 帧 16.7ms」的极端情况
            // 会自我节流成「隔帧一次」，滞后从 1 帧变成 1~2 帧，不会堆积。
            if (maskAge_ >= g_cfg.maskEveryAsync) {
                maskAge_ = 0;
                submitAsync(slot, src, w, h);
            } else {
                maskAge_++;
            }
            // 1.0.0.3 兜底防线：掩码与包围盒必须与当前帧同尺寸同坐标系，
            // 否则宁可这一帧不用掩码（透传/全帧路径），也不能让下游越界。
            if (maskValid_ &&
                (mask_.size() != (size_t)w * h ||
                 bounds_.x0 < 0 || bounds_.y0 < 0 ||
                 bounds_.x1 > w || bounds_.y1 > h)) {
                maskValid_ = false;
            }
            return maskValid_;              // 结果没回来就继续用旧掩码，不等
        }

        if (maskAge_ < kMaskEverySync) {    // 沿用上一次的掩码
            maskAge_++;
            return maskValid_;
        }
        maskAge_ = 0;

        std::string msg;
        int px = 0, faces = 0;
        if (!buildMaskInto(S, src, w, h, mask_, protect_, bounds_, faces_,
                           px, faces, msg)) {
            return onDetectFailed(S, msg, face_.inputSize(), S.detBest);
        }
        maskPixels_ = px;
        lastFaces_ = faces;
        maskHold_ = 0;
        maskValid_ = true;
        faceErr_ = msg;
        return true;
    }

    // 检测 + 肤色掩码 + 五官保护 + 包围盒，全部算进调用方给的缓冲。
    //
    // 刻意做成**只读 src、不碰任何成员**的函数：异步化时它整段跑在 worker 线程上，
    // 只要不碰成员就不存在数据竞争。这也是异步化能做得这么轻的原因 ——
    // 不需要给磨皮链加锁。
    // 1.0.0.2 的人脸框 EMA 与方向状态一样按 slot 存在 DetState 里，
    // 函数本身只碰调用方传进来的 S，不碰任何文件级状态。
    bool buildMaskInto(DetState& S, const unsigned char* src, int w, int h,
                       std::vector<unsigned char>& maskOut,
                       std::vector<unsigned char>& protectOut,
                       beautycore::RoiRect& boundsOut,
                       std::vector<beautycore::FaceBox>& fboxOut,
                       int& pxOut, int& facesOut, std::string& msgOut) {
        BEAUTY_BIND_DET_DIR(S);
        if (maskOut.size() != (size_t)w * h) maskOut.assign((size_t)w * h, 0);
        if (protectOut.size() != (size_t)w * h) protectOut.assign((size_t)w * h, 0);

        std::vector<beautycore::FaceBox> faces;
        std::string ferr;
        // 1.0.3.0：换分辨率（含「横屏源 ↔ 竖屏源」这种宽高互换）时把方向结论
        // 重来 —— 上一台摄像头的「源被转了 90°」不能套到另一路上。
        if (w != rotLastW_ || h != rotLastH_) {
            rotLastW_ = w;
            rotLastH_ = h;
            autoMiss_ = 0;
            autoCool_ = 0;
            autoProbeLogged_ = false;
            effRot_ = rotManual_;     // 手工声明的不动，自动认定的作废
            effRoll_ = 0.0f;           // 1.0.5.0：倾斜结论同样作废
            rollMiss_ = 0;
            rollCool_ = 0;
            rollCheck_ = 0;            // 1.0.13.9：对照计数一并作废
        }
        // 直接喂 RGBA（stride=4）。原先要先摊一份全分辨率 RGB，1080p 下那是
        // 600 万字节的写入，而检测只吃 640x640 —— 这份中间缓冲是纯浪费。
        //
        // 1.0.3.0：按本帧有效方向检测（旋转做进 letterbox 的重采样）。
        // 1.0.5.0：再加上平面内倾斜补偿，合成一个角度喂给检测器。
        // 1.0.13.1：**不能是 const**。下面两条兜底会换一个角度重检并覆盖 faces，
        // 成功时必须把 detRot 同步成那次实际使用的角度 —— 否则反变换会按一个
        // 与 faces 不对应的角度搬坐标，人脸框落到画面别处（框在「歪头回正」
        // 和「自动方向判定失效」的那一帧会短暂糊到背景上，并污染
        // estimateSkinCenter 的采样）。改前这里是 const，靠「反变换直接读
        // effRot_ 成员、而兜底分支顺手改了它」碰巧一致；冻结成局部量后就露出来了。
        float detRot = (float)effRot_ + effRoll_;
        beautycore::DetMeta dmeta;
        bool detOk = face_.detect(src, w, h, faces, ferr, 0.6f, 0.3f, 4, detRot,
                                  &dmeta) &&
                     !faces.empty();
        // 只取「主检测」这一枪的置信度：下面的兜底与探测是**为了救回来**而额外
        // 打的，它们的分数属于别的角度，记进来会让「本路到底看清了多少」失真。
        S.detBest = dmeta.best;
        /* 1.0.5.0：倾斜补偿失效（头已经回正、或那一次 roll 判错了）。
         * 与下面「方向兜底」同构：一旦按带倾斜的角度检不到，**当帧**就退回
         * 不带倾斜再试一次。命中即清掉 roll —— 于是「歪头 → 回正」只丢 0 帧，
         * 不需要等计数器攒够。 */
        if (!detOk && effRoll_ != 0.0f) {
            std::string e3;
            if (face_.detect(src, w, h, faces, e3, 0.6f, 0.3f, 4, (float)effRot_) &&
                !faces.empty()) {
                detOk = true;
                ferr = e3;
                detRot = (float)effRot_;   // 这次用的是「方向角」，不含倾斜
                effRoll_ = 0.0f;
                rollMiss_ = 0;
                rollCool_ = 0;
                rollCheck_ = 0;            // 1.0.13.9：已回 0，对照计数无意义
                // 1.0.13.7：滚转释放同样是一帧内的几何突变（45° → 0°），
                // 从上一帧的框过渡过去，别让「歪完回正」也闪一下。
                startGeoFade(S);
                resetFaceEmaState(S);
            }
        }
        /* 方向选错时（源其实正立、却按 90° 检测）YuNet 在躺倒的脸上一个框都
         * 出不来 —— 掩码为空 → 磨皮/美白整段静默失效。这里退一步再试一次
         * 「不旋转」：能检出就说明这一档方向与源不匹配，于是本帧改按 0° 走，
         * 并把自动探测的状态清空（下一轮从 0 重来）。
         * 只在「已经检不到」时多跑一次推理，正常帧一分钱不花。 */
        if (!detOk && effRot_ != 0) {
            std::string e2;
            if (face_.detect(src, w, h, faces, e2, 0.6f, 0.3f, 4, 0.0f) &&
                !faces.empty()) {
                const int prevRot = effRot_;
                detOk = true;
                ferr = e2;
                effRot_ = 0;
                detRot = 0.0f;             // 这次检测用的就是 0°，反变换必须一致
                effRoll_ = 0.0f;
                autoMiss_ = 0;
                autoCool_ = 0;
                rollCheck_ = 0;            // 1.0.13.9
                autoProbeLogged_ = false;
                resetFaceEmaState(S);
                if (!rotFallbackLogged_) {
                    rotFallbackLogged_ = true;
                    NALOG(BEAUTY_LOG_WARNING,
                          "[美颜] 输入方向 %d° 在本源上检不到脸，已自动改用 0°"
                          "（画面正常；删掉 BEAUTY_INPUT_ROT 环境变量可消掉这条）",
                          prevRot);
                }
            }
        }
        /* 1.0.5.0：这次命中出来的框**像不像人脸**。
         *
         * 为什么「检到了」还不够：45° 歪头时 YuNet 经常不是给不出框，而是给一个
         * **敷衍框** —— 实测真机方向（270°）下 score 0.759、双眼间距只有框宽的
         * 28%（正立脸是 43~47%）：框在那儿，但位置和大小都不对，掩码照样糊到脸
         * 外面。用户看到的还是「美颜失效」，而且这种帧连方向兜底都不会触发
         * （detOk 为真），倾斜探测也永远轮不到。
         *
         * 所以判定分两档：合格 → 直接用；不合格 → 这一帧先凑合用着（不要闪），
         * 同时开始攒计数器，攒够了去试 ±45°，**只有找到明显更好的角度才切换**。 */
        bool plausOk = false;
        float curBest = -1.0f;
        // 1.0.13.9：**通过 rollBoxPlausible 的框里**分数最高的那个。倾斜释放要和
        // 0° 对照比，必须两边同口径 —— 拿「所有框的最高分」比，会被一个不 plausible
        // 的高分假框顶住，该释放时释放不了。
        float plausBest = -1.0f;
        if (detOk) {
            for (size_t i = 0; i < faces.size(); i++) {
                if (faces[i].score > curBest) curBest = faces[i].score;
                if (rollBoxPlausible(faces[i])) {
                    plausOk = true;
                    if (faces[i].score > plausBest) plausBest = faces[i].score;
                }
            }
        }
        /* 1.0.5.0：平面内倾斜探测。走到这里说明「按当前方向 + 当前倾斜」要么检不到
         * 脸，要么检出来的框明显不像人脸。先试 ±45° 各一次（合成到方向角上），
         * 命中就把 roll 记下来，下一帧起按它检测。这条路与上面的 90/270 方向探测
         * **互不干扰**：方向管「源躺没躺」，倾斜管「头歪没歪」。
         *
         * 阈值比方向探测小得多（默认 8 次 ≈ 0.27 秒）：本来就检得到脸的人突然
         * 检不到、或者框突然变敷衍，最常见的原因就是头歪了，要立刻补上；人真走开
         * 时多两次推理（各 640×640）也无所谓，且有冷却。 */
        if ((!detOk || !plausOk) && g_cfg.autoRoll) {
            if (rollCool_ > 0) {
                rollCool_--;
            } else if (++rollMiss_ >= g_cfg.rollMiss) {
                rollMiss_ = 0;
                rollCool_ = g_cfg.autoRotCool;
                // 两个候选：±45°。为什么要「两个都试、再挑」而不是「命中就收」：
                // YuNet 对 ≥60° 的侧躺脸也会给出 0.66~0.69 的假框（不空），
                // 先试哪个就收哪个有 50% 概率锁死到错的方向。
                //
                // 候选只有 ±45，不铺更细的梯子，是**成本**决定的：每多一个候选就是
                // 一次 640×640 推理（~2ms），而 ±45 能覆盖的区间正好是「0° 已经检不到」
                // 的那一段（实测 YuNet 的容忍边界在 30~40°，±45 各自还剩 5~15° 余量）。
                // 两个都不像人脸就不锁定，等冷却结束再试 —— 宁可不补偿，也不能锁错。
                const float cand[2] = {45.0f, -45.0f};
                float bestRoll = 0.0f;
                // 已经有框但框不像人脸时，要求候选**明显更好**才换角度。0.05 是照着
                // 实测留的余量（真机敷衍框 0.759 / 换对角度后 0.906）；门槛太松会在
                // 两个角度之间来回跳，而每跳一次都要清掉人脸框的 EMA —— 画面会抖。
                float bestScore = detOk ? (curBest + 0.05f) : -1.0f;
                for (int c = 0; c < 2; c++) {
                    std::vector<beautycore::FaceBox> pf;
                    std::string pe;
                    if (!face_.detect(src, w, h, pf, pe, 0.6f, 0.3f, 4,
                                      (float)effRot_ + cand[c]) ||
                        pf.empty())
                        continue;
                    for (size_t k = 0; k < pf.size(); k++) {
                        if (!rollBoxPlausible(pf[k])) continue;
                        if (pf[k].score > bestScore) {
                            bestScore = pf[k].score;
                            bestRoll = cand[c];
                        }
                    }
                }
                if (bestRoll != 0.0f) {
                    effRoll_ = bestRoll;
                    rollCheck_ = 0;    // 1.0.13.9：刚锁定，对照计数从头开始
                    // 1.0.13.7：滚转从 0 跳到 ±45 是「一帧内整个换几何」——
                    // 关键点从塌成水平恢复成真倾斜、rw/rh 从外接盒变成紧框。
                    // 记下切换前那一帧的框，接下来几帧插值过去。
                    startGeoFade(S);
                    resetFaceEmaState(S);
                    if (!rollProbeLogged_) {
                        rollProbeLogged_ = true;
                        NALOG(BEAUTY_LOG_WARNING,
                              "[美颜] 倾斜探测命中 %+.0f°（score=%.3f）：本帧人脸在"
                              "画面内倾斜了约 %.0f°，已自动补偿。若判定有误，设 "
                              "BEAUTY_AUTO_ROLL=0 关闭。",
                              bestRoll, bestScore, fabsf(bestRoll));
                    }
                    if (!detOk) {
                        // 本来就没框：本帧仍丢（下一帧起按新角度检测）。探测出来的
                        // 框不复用 —— 丢一帧（33ms）最省事，也不会把两个坐标系的量
                        // 混在一个返回值里。
                        facesOut = 0;
                        msgOut = ferr;
                        return false;
                    }
                    // 有框只是敷衍：这一帧的框已经在手上了，照旧用掉，别为了一次
                    // 换角度再闪一帧。下一帧起按新角度检测（本分支**不动** detRot，
                    // 本帧的 faces 本来就是按 detRot 检出来的，反变换两边一致）。
                }
                // 两个候选都不像人脸：不锁定，保持 effRoll_ 现状（可能是 0，
                // 也可能还是上一轮的倾斜角）。冷却结束再试。
            }
        }
        /* 1.0.13.9：倾斜锁死的周期性释放。
         *
         * 上面那条「按锁定角检不到脸就退回 0°」的兜底覆盖不到一种情况：头回正后
         * YuNet 在 -45° 输入下**仍然给得出框**，而且框还落在 rollBoxPlausible 的
         * 区间里。于是 detOk / plausOk 全为真，兜底与倾斜探测两条出口都不触发，
         * roll 就永久停在 -45 —— 位置看着还对，只是因为关键点 phi 收敛到反向角
         * 与 roll 互相抵消（实测 phi +42.6° vs roll -45，掩码却大了 30%）。
         *
         * 所以「看起来一切正常」的时候反而要定期怀疑一次：每 rollCheckFrames 帧
         * 在同一条路上额外跑一次 0°（不含倾斜）检测，只有它**明显更好**才释放。
         *
         * 为什么门槛取「score 高出 rollReleaseMargin」而不是「0° 也能检出就行」：
         * 真歪头时 0° 大概率也能检出个框，只是撑大的敷衍框。要求明显更好，才
         * 不会在该补偿的时候把补偿撤掉。实测真歪 45° 时 0° 那一路的框
         * 双眼间距比只有 0.216，根本过不了 rollBoxPlausible。
         */
        if (detOk && plausOk && effRoll_ != 0.0f && g_cfg.rollCheckFrames > 0) {
            if (++rollCheck_ >= g_cfg.rollCheckFrames) {
                rollCheck_ = 0;
                std::vector<beautycore::FaceBox> cf;
                std::string ce;
                if (face_.detect(src, w, h, cf, ce, 0.6f, 0.3f, 4, (float)effRot_) &&
                    !cf.empty()) {
                    float cBest = -1.0f;
                    for (size_t k = 0; k < cf.size(); k++) {
                        if (!rollBoxPlausible(cf[k])) continue;
                        if (cf[k].score > cBest) cBest = cf[k].score;
                    }
                    if (cBest >= 0.0f && cBest >= plausBest + g_cfg.rollReleaseMargin) {
                        effRoll_ = 0.0f;
                        rollMiss_ = 0;
                        rollCool_ = 0;
                        rollCheck_ = 0;
                        // 与倾斜切换同一条过渡路径：本帧 faces 仍是按旧角检出来的，
                        // 下一帧才按 0° 走，中间几帧由 applyGeoFade 插值。
                        startGeoFade(S);
                        resetFaceEmaState(S);
                        if (rollReleaseLog_ < 3) {
                            rollReleaseLog_++;
                            NALOG(BEAUTY_LOG_WARNING,
                                  "[美颜] 倾斜补偿已释放（0° 对照 score=%.3f 高于"
                                  "当前 %.3f）。若本不该释放，调大 BEAUTY_ROLL_CHECK "
                                  "或设 0 关闭这道门。",
                                  cBest, plausBest);
                        }
                    }
                }
            }
        } else {
            // roll 为 0 或本帧不正常时不攒计数：计数只该衡量「连续看起来正常
            // 却可能是锁死」的时长。
            rollCheck_ = 0;
        }
        if (!detOk) {
            /* 1.0.3.0（自动输入方向）：**用户没声明方向**（BEAUTY_INPUT_ROT 未设）
             * 而源被转过 90° 时，上面那条反向兜底救不了 —— 它只在 effRot_≠0 时才
             * 跑，而这里 effRot_ 一直是 0。这正是「竖屏摄像头美颜完全没效果」那条链：
             *   OBS 场景项旋转只作用于显示合成 → 滤镜拿到的帧仍是横躺的
             *   → YuNet 在躺脸上一个框都出不来 → 掩码为空 → 磨皮/美白/红润全乘 0。
             *
             * 试法：连续 N 次检不到脸后，在**同一张输入图**上各跑一次 90°/270° 的
             * 重采样检测；任一方向出脸就把 effRot_ 定为该角度，下一帧起按它检测，
             * 再把几何反变换回源坐标（与手工 BEAUTY_INPUT_ROT 完全同一条路径）。
             *
             * 三条取舍，写在这里免得以后又当 bug 改：
             *   · 命中后 **本帧仍返回 false**（丢 1 帧）。探测出来的框不复用：丢一帧
             *     （33ms）最省事，且不会把两个坐标系的量混在一个返回值里。
             *   · 探测本身是**额外两次推理**（各 640×640），只发生在「已经检不到脸」
             *     的帧上，且有冷却，正常人走开的场景不会烧推理。
             *   · 只认 90/270，不试 180：YuNet 对倒立脸的召回本来就差，而源被倒装
             *     接法几乎没有。
             * BEAUTY_AUTO_ROT=0 可整段关掉。 */
            const bool autoEligible = g_cfg.autoRot && (rotManual_ == 0) &&
                                      (effRot_ == 0);
            if (autoEligible) {
                if (autoCool_ > 0) {
                    autoCool_--;
                } else if (++autoMiss_ >= g_cfg.autoRotMiss) {
                    autoMiss_ = 0;
                    autoCool_ = g_cfg.autoRotCool;
                    // 用 DEBUG：人走开时探测会周期性重试，INFO 会按「每 N 次检测
                    // 一条」刷日志。要看它就用 OBS 的 --verbose。
                    NALOG(BEAUTY_LOG_DEBUG,
                          "[美颜] 自动方向探测开始（连续 %d 次无脸，w=%d h=%d）",
                          g_cfg.autoRotMiss, w, h);
                    // 两个方向都跑，取**分数高的那个**（顺序无关）。
                    //
                    // 与 GPU 版的差异（有意为之）：GPU 版是「先试一个，命中就收」，
                    // 靠顺序在两个方向间轮换。实测这台机器上，YuNet 对**倒立脸**也
                    // 会给 0.82 级的框（同一帧：正立 0.920 / 翻转 0.820），所以「首个
                    // 命中」有一半概率挑到翻转方向 —— 掩码仍落在脸上，但五位关键点
                    // 会跑到嘴的位置，亮眼/去黑眼圈/法令纹随之错位。多跑一次推理
                    // （只在「已经连续无脸」的探测帧上发生，且有冷却）换正确方向，划算。
                    const int cand[2] = {90, 270};
                    int bestRot = 0;
                    float bestScore = -1.0f;
                    for (int c = 0; c < 2; c++) {
                        std::vector<beautycore::FaceBox> pf;
                        std::string pe;
                        if (!face_.detect(src, w, h, pf, pe, 0.6f, 0.3f, 4,
                                          (float)cand[c]) ||
                            pf.empty())
                            continue;
                        float s = 0.0f;
                        for (size_t k = 0; k < pf.size(); k++)
                            if (pf[k].score > s) s = pf[k].score;
                        if (s > bestScore) { bestScore = s; bestRot = cand[c]; }
                    }
                    if (bestRot != 0) {
                        effRot_ = bestRot;
                        effRoll_ = 0.0f;   // 1.0.5.0：方向一定，倾斜结论作废重来
                        rollMiss_ = 0;
                        rollCool_ = 0;
                        rollCheck_ = 0;    // 1.0.13.9
                        resetFaceEmaState(S);
                        msgOut = ferr;      // 本帧仍然没有掩码
                        facesOut = 0;
                        if (!autoProbeLogged_) {
                            autoProbeLogged_ = true;
                            NALOG(BEAUTY_LOG_WARNING,
                                  "[美颜] 连续 %d 次检不到脸，自动方向探测命中 %d°"
                                  "（score=%.3f）：本源的画面相对正立被转了 %d°，"
                                  "已自动补偿。下一帧起按该方向检测；若判定有误，设 "
                                  "BEAUTY_AUTO_ROT=0 关闭本功能。",
                                  g_cfg.autoRotMiss, bestRot, bestScore, bestRot);
                        }
                        return false;
                    }
                    /* 两个方向都没出脸：保持 effRot_=0，冷却之后再试。
                     * 不写「试过都不行」的状态 —— 人可能只是暂时走开。 */
                }
            }
            msgOut = ferr;
            facesOut = 0;
            return false;
        }
        /* 几何此刻在「旋转后整图」坐标系里，必须立刻反变换回源坐标系。
         * 位置有两条硬约束：
         *   · 必须在 estimateSkinCenter 之前 —— 那个函数拿 faces 去采 src 的真实
         *     像素，src 是全帧原图未旋转，坐标差一次旋转就会把肤色椭圆中心采到别处；
         *   · 必须在 fboxOut 赋值之前 —— 交出去的那份要供五官/美形段用。 */
        if (detRot != 0.0f) {
            // 画布尺寸必须与检测侧 letterboxRgbRot 用同一对数（rotCanvasSize），
            // 否则中心差半像素、整框平移。
            float Wr = 0.0f, Hr = 0.0f;
            beautycore::rotCanvasSize(detRot, w, h, Wr, Hr);
            for (size_t i = 0; i < faces.size(); i++)
                invRotateFace(faces[i], detRot, Wr, Hr, (float)w, (float)h);
        }
        // 1.0.0.2：时序平滑 + 遮挡迟滞。放在这里是为了让随后的肤色掩码、
        // 五官保护区、estimateSkinCenter 与交出去的 fboxOut 用同一组框。
        // BEAUTY_FACE_EMA=0 且 BEAUTY_FACE_HOLD=0 时整段空转。
        smoothFaceBoxes(S, faces, w, h);
        // 1.0.13.7：几何过渡。必须在画掩码、估肤色中心、交 fboxOut 之前 ——
        // 这三处都要用同一组框，晚一步就会出现「掩码按新几何、形变按旧几何」。
        applyGeoFade(S, faces);
        // 记下「这一帧真正交给下游的几何」，供下一次滚转切换当插值起点。
        // 放在 applyGeoFade 之后：过渡中的帧记的是插值结果，接着插值才连续。
        if (!faces.empty()) S.geoLast = faces;
        facesOut = (int)faces.size();
        // 关键点要留给后续的「五官局部」五项用（亮眼/去黑眼圈/法令纹…都要位置）。
        // 在这里一次性交出去，而不是让那几项自己去调检测 —— 一帧只跑一次推理。
        fboxOut = faces;

        unsigned char* mask = &maskOut[0];
        unsigned char* protect = &protectOut[0];
        memset(mask, 0, (size_t)w * h);

        // 肤色椭圆中心自适应（C20）：先按本帧画面估计一次，再画掩码。
        //
        // 线程安全：g_skinCb/g_skinCr 只有这一处写。异步模式下本函数整段跑在
        // 唯一的 worker 上，同步模式下跑在渲染线程上，两条路径互斥（asyncOn_），
        // 不存在并发写。skinWeight() 也只被下面的 paintSkin 调用，磨皮链不读它。
        //
        // EMA 平滑：默认 1.0 = 每帧直接采纳（纯函数，与调用次数无关）。
        // <1 的系数只在真机防抖时用，理由见 g_skinAdaptEma 的定义处。
        if (g_skinAdapt) {
            float ecb = 0.0f, ecr = 0.0f;
            if (estimateSkinCenter(src, w, h, faces, ecb, ecr)) {
                if (!g_skinAdaptValid) {
                    g_skinCb = ecb;          // 首帧直接采纳，避免从旧值慢慢爬
                    g_skinCr = ecr;
                    g_skinAdaptValid = true;
                    g_skinAnnounce.store(true, std::memory_order_relaxed);
                } else {
                    g_skinCb += (ecb - g_skinCb) * g_skinAdaptEma;
                    g_skinCr += (ecr - g_skinCr) * g_skinAdaptEma;
                }
            }
            // 估计失败（脸太小 / 被遮挡 / 极暗）时保持上一帧中心，不重置
        }

        // 掩码像素数与包围盒在写入时顺带统计，不再单独扫两遍全帧。
        // 1080p 下那两遍各是 200 万次内存访问，纯属为诊断付的代价。
        // 只有「从 0 变 255」才计数，否则脸框与脖子通道重叠处会被重复算。
        int px = 0;
        int bx0 = w, by0 = h, bx1 = -1, by1 = -1;

        // 单像素落笔：肤色权重 × 边界羽化系数，取最大值合并（脸框与脖子通道重叠）。
        // 返回 true = 这一像素真的落了非零值（用于统计包围盒的 y 范围）。
        auto paintSkin = [&](unsigned char* mrow, const unsigned char* row,
                             int x, int feather) {
            const int wgt = skinWeight(row[x * 4 + 0], row[x * 4 + 1],
                                       row[x * 4 + 2]);
            if (wgt <= 0) return false;
            const int v = (feather >= 256) ? wgt : (wgt * feather + 128) / 256;
            if (v <= 0) return false;
            if (!mrow[x]) {
                px++;
                if (x < bx0) bx0 = x;
                if (x > bx1) bx1 = x;
            }
            // 脸框与脖子通道可能重叠：取较大值，别让后画的覆盖掉
            if (v > (int)mrow[x]) mrow[x] = (unsigned char)v;
            return true;
        };

        // paintSkin 的「权重已算好」版本。脖子跟随肤色时，同一像素的权重
        // 要先用一次（探边界）、再用一次（落笔），重复调 skinWeight 里那个 sqrt
        // 是白费的。
        auto paintW = [&](unsigned char* mrow, int x, int wgt, int feather) {
            if (wgt <= 0) return false;
            const int v = (feather >= 256) ? wgt : (wgt * feather + 128) / 256;
            if (v <= 0) return false;
            if (!mrow[x]) {
                px++;
                if (x < bx0) bx0 = x;
                if (x > bx1) bx1 = x;
            }
            if (v > (int)mrow[x]) mrow[x] = (unsigned char)v;
            return true;
        };

        for (const auto& f : faces) {
            const float cx = f.x + f.w * 0.5f, cy = f.y + f.h * 0.5f;
            /* 1.0.5.0（头歪补偿）：头歪的时候检测框只能退化成**轴对齐外接矩形**，
             * 45° 时外接盒面积是脸本身的 2.8 倍。要是还照外接盒画掩码，磨皮会糊到
             * 脸外面去，ROI 也白涨一倍 —— 实测 45° 时磨皮 10.5 → 19.5 ms、掩码覆盖
             * 12.5% → 25.2%，而脸一点没变大。
             *
             * 所以：bw/bh 取**脸自身**的宽高（倾斜矩形的边长），roll 是它的倾角，
             * 逐像素先把坐标转进脸自己的坐标系，再按 (bw, bh) 画。
             *
             * 未倾斜时 f.rw 恒为 0 → bw=f.w、bh=f.h、roll=0、cos=1/sin=0，
             * 下面每一处都退化成原式，0/90/180/270 逐字节不变。 */
            const float bw = (f.rw > 0.0f) ? f.rw : f.w;
            const float bh = (f.rh > 0.0f) ? f.rh : f.h;
            const float rolled = f.roll;
            const float rrad = rolled * (3.14159265358979323846f / 180.0f);
            const float rct = cosf(rrad), rst = sinf(rrad);
            // 绘制范围 = 倾斜矩形（按 grow 放大后）的外接盒。未倾斜时 = cx±bw*grow/2。
            const float hw = 0.5f * (bw * fabsf(rct) + bh * fabsf(rst)) * kFaceBoxGrow;
            const float hh = 0.5f * (bw * fabsf(rst) + bh * fabsf(rct)) * kFaceBoxGrow;
            int x0 = (int)(cx - hw), x1 = (int)(cx + hw);
            int y0 = (int)(cy - hh), y1 = (int)(cy + hh);
            if (x0 < 0) x0 = 0;
            if (y0 < 0) y0 = 0;
            if (x1 > w) x1 = w;
            if (y1 > h) y1 = h;

            // 脖子通道的横向范围。脸框底边在它之内时**不做下羽化**，否则下巴
            // 与脖子之间会出现一条水平接缝。
            int nx0 = (int)(cx - bw * g_neck.halfW);
            int nx1 = (int)(cx + bw * g_neck.halfW);
            if (nx0 < 0) nx0 = 0;
            if (nx1 > w) nx1 = w;

            int fe = (g_maskFeatherPx >= 0)
                         ? g_maskFeatherPx
                         : (int)(bw * kMaskFeatherRatio + 0.5f);
            if (fe > kFeatherMax) fe = kFeatherMax;
            if (fe < 0) fe = 0;
            // 脖子通道的羽化宽度**不能**用这个 fe：3.1.9 用脸宽 12%，等价于脖子半宽的
            // 27%，整个脖子外侧四分之一都被压成半强度，这是真机上「效果弱了较多」的
            // 主力来源。脖子的羽化按脖子自己的宽度算，见下面的 feN —— 而且旋转源上
            // 横向的「脸宽」不是 bw，必须按投影重算。

            if (g_maskShape & 1) {
                // 椭圆距离场（3.1.20）：边界按 (x/a)²+(y/b)² = 1 收敛，四条直边消失。
                // 到边界的像素距离用 (1−q)·rEff 近似（q 是归一化半径），脸框接近方形
                // 时误差 <10%；羽化斜坡吃的是整数像素，这点误差看不出来。
                //
                // 1.0.5.0：半轴取**脸自身**的半宽半高，不是外接盒的。45° 时外接盒是
                // 正方形，拿它当半轴等于把椭圆画成圆，横向多糊一大圈。
                // 未倾斜时 hw/hh 逐位等于这两个值。
                const float a = 0.5f * bw * kFaceBoxGrow;
                const float b = 0.5f * bh * kFaceBoxGrow;
                const float ia2 = 1.0f / (a * a), ib2 = 1.0f / (b * b);
                const float rEff = 0.5f * (a + b);
                for (int y = y0; y < y1; y++) {
                    const unsigned char* row = src + ((size_t)y * w) * 4;
                    unsigned char* mrow = &mask[(size_t)y * w];
                    const float dy = (float)y + 0.5f - cy;
                    bool any = false;
                    for (int x = x0; x < x1; x++) {
                        const float dx = (float)x + 0.5f - cx;
                        // 转进脸自己的坐标系（未倾斜时 cos=1/sin=0，逐位等于 dx/dy）
                        const float ux = dx * rct + dy * rst;
                        const float uy = dy * rct - dx * rst;
                        const float q = sqrtf(ux * ux * ia2 + uy * uy * ib2);
                        if (q >= 1.0f) continue;      // 椭圆外不落笔，等价于旧的矩形裁剪
                        const int dpx = (int)((1.0f - q) * rEff + 0.5f);
                        if (paintSkin(mrow, row, x, featherRamp(dpx, fe))) any = true;
                    }
                    // 只在**这一行真的落了像素**时扩 y：否则椭圆上下顶点那几行没肤色，
                    // 也会把包围盒拽到最大、ROI 白白变大、性能数据失真。
                    if (any) {
                        if (y < by0) by0 = y;
                        if (y > by1) by1 = y;
                    }
                }
            } else if (rolled != 0.0f) {
            /* 1.0.5.0：头歪时的**倾斜矩形**距离场。
             * 与上面那个轴对齐矩形路径同一套羽化口径（到边界的像素距离 →
             * featherRamp），只是边界在脸自己的坐标系里，所以 45° 时画出来的是
             * 一个跟着头转的斜方框，而不是把整张脸套进去的大方块。
             * 脖子接缝那套「底边不羽化」在这里不做：外接盒的底边是斜框的一个**角**，
             * 不是下巴线，按它放开反而会在脸侧漏一条不羽化的边。 */
            const float a = 0.5f * bw * kFaceBoxGrow;
            const float b = 0.5f * bh * kFaceBoxGrow;
            for (int y = y0; y < y1; y++) {
                const unsigned char* row = src + ((size_t)y * w) * 4;
                unsigned char* mrow = &mask[(size_t)y * w];
                const float dy = (float)y + 0.5f - cy;
                bool any = false;
                for (int x = x0; x < x1; x++) {
                    const float dx = (float)x + 0.5f - cx;
                    const float ux = dx * rct + dy * rst;
                    const float uy = dy * rct - dx * rst;
                    const float ex = a - fabsf(ux);
                    const float ey = b - fabsf(uy);
                    if (ex <= 0.0f || ey <= 0.0f) continue;
                    const int dpx = (int)((ex < ey ? ex : ey) + 1.0f);
                    if (paintSkin(mrow, row, x, featherRamp(dpx, fe))) any = true;
                }
                if (any) {
                    if (y < by0) by0 = y;
                    if (y > by1) by1 = y;
                }
            }
            } else {
            for (int y = y0; y < y1; y++) {
                const unsigned char* row = src + ((size_t)y * w) * 4;
                unsigned char* mrow = &mask[(size_t)y * w];
                const int fTop = featherRamp(y - y0 + 1, fe);
                const int fBot = featherRamp(y1 - y, fe);
                bool any = false;
                for (int x = x0; x < x1; x++) {
                    const int dl = x - x0 + 1, dr = x1 - x;
                    int feather = fTop;
                    const int fx = featherRamp(dl < dr ? dl : dr, fe);
                    if (fx < feather) feather = fx;
                    // 下巴正下方交给脖子通道续上，底边不羽化（否则出现水平线）
                    if ((x < nx0 || x >= nx1) && fBot < feather) feather = fBot;
                    if (paintSkin(mrow, row, x, feather)) any = true;
                }
                // 只在**这一行真的落了像素**时扩 y：否则脸框下沿那几行没肤色，
                // 也会把包围盒拽到最大，ROI 白白变大、性能数据失真。
                if (any) {
                    if (y < by0) by0 = y;
                    if (y > by1) by1 = y;
                }
            }
            }

            /* 1.0.7.0：脖子通道按**立正方向**重画（1.0.6.0 的止血版是「旋转源上不画」）。
             *
             * ≤1.0.5.0 的实现在源坐标里从脸框下沿按 +y 往下推。源要转 90/270° 才立正
             * 时（本机摄像头就是这一档），源 +y 在立正画面里是横向的，掩码就画成一条
             * 横穿肩膀落到窗帘上的带子，真正的脖子一点没磨 ——
             * 见 docs/design/design-face-mask.md §15。
             *
             * 现在把「正下方」写成单位向量 (ndx,ndy)，几何全部参数化成 (u,v)：
             *   u = 沿正下方离开脸框下沿的距离（像素，≥0）
             *   v = 横向偏移（像素，左右为负正）
             * 三种形状（跟随肤色 / 椭圆 / 矩形）都只跟 u、v 走，与源朝向无关。
             *
             * 0° 源上 (ndx,ndy)=(0,1)、(ldx,ldy)=(1,0)，并且原点与取整口径照旧
             * （u 从已 clamp 的 y1 起算、x 用 (int) 截断），所以 roll==0 时**逐字节
             * 不变**；90/180/270 源的输出会变，那正是要修的东西。
             *
             * BEAUTY_NECK=0 整段关闭（A/B 与「只要脸不要脖子」）。 */
            int ndx = 0, ndy = 1;
            switch (((effRot_ % 360) + 360) % 360) {
            case 90:  ndx = 1;  ndy = 0;  break;
            case 180: ndx = 0;  ndy = -1; break;
            case 270: ndx = -1; ndy = 0;  break;
            default: break;
            }
            // 横向单位向量。竖直方向（0°/180°）取 +x，水平方向（90°/270°）取 ∓y。
            // 0° 必须取 +x：旧实现在 x 上从 nx0 递增，羽化按「离左右边界的距离」算，
            // 取 -x 会把羽化与肤色探测一起镜像，输出就不再逐字节相同。
            const int ldx = (ndy == 0) ? 0 : 1;
            const int ldy = (ndy == 0) ? ndx : 0;
            const bool flat = (ndx == 0 && ndy == 1);  // 0° 源：沿用旧取整口径

            // 脖子起点 = 脸框沿「正下方」的下沿中心。脸框（可能被 tilt 转过 rolled）
            // 沿 (ndx,ndy) 的半跨度 = 两条半边在 n 上的投影之和的一半。
            // roll==0 时它退化成 hh（ndy=±1）或 hw（ndx=±1），与画面自洽。
            const float uAbsX = fabsf(rct * (float)ndx + rst * (float)ndy);
            const float uAbsY = fabsf(-rst * (float)ndx + rct * (float)ndy);
            const float vAbsX = fabsf(rct * (float)ldx + rst * (float)ldy);
            const float vAbsY = fabsf(-rst * (float)ldx + rct * (float)ldy);
            // 脸框沿「正下方」与「横向」的两个半跨度。**旋转源的宽高是交换过的**：
            // 源被转 270° 时 bw 是脸的纵向尺寸（脸高）、bh 才是横向尺寸（脸宽）。
            // 照旧把 bw 当脸宽用，脖子会按脸的长边铺开 —— 实测宽度多 1.4 倍。
            const float halfAlong  = 0.5f * (bw * uAbsX + bh * uAbsY);
            const float halfAcross = 0.5f * (bw * vAbsX + bh * vAbsY);
            const float extU = halfAlong * kFaceBoxGrow;
            const int oxI = flat ? (int)cx : (int)lroundf(cx + extU * (float)ndx);
            const int oyI = flat ? y1      : (int)lroundf(cy + extU * (float)ndy);
            int ny1 = (int)(cy + extU + 2.0f * halfAlong * g_neck.len);
            if (ny1 > h) ny1 = h;
            const int uLen = flat ? (ny1 - y1) : (int)(2.0f * halfAlong * g_neck.len);
            // 脖子羽化宽度按脖子的实际宽度给（理由见 kMaskFeatherRatio 那段注释）。
            // 这里重算一遍而不是复用外面的 feNeck：旋转源上横向脸宽不是 bw。
            int feN = (g_maskFeatherPx >= 0)
                          ? g_maskFeatherPx
                          : (int)(2.0f * g_neck.halfW * (2.0f * halfAcross)
                                      * kMaskFeatherRatio + 0.5f);
            if (feN > kFeatherMax) feN = kFeatherMax;
            if (feN < 0) feN = 0;
            const int vHalf = (int)(2.0f * g_neck.halfW * halfAcross);
            // 椭圆分支的横向中心相对 oxI 的偏移（flat 时 oxI 是 (int)cx，差一个亚像素）。
            const float vCen = flat ? ((float)oxI - cx) : 0.0f;

            if (g_neckOn && uLen > 0) {
                auto atUV = [&](int u, int v, int& X, int& Y) {
                    X = oxI + u * ndx + v * ldx;
                    Y = oyI + u * ndy + v * ldy;
                };
                auto paintUV = [&](int u, int v, int feather) -> bool {
                    int X = 0, Y = 0;
                    atUV(u, v, X, Y);
                    if (X < 0 || X >= w || Y < 0 || Y >= h) return false;
                    const unsigned char* row = src + ((size_t)Y * w) * 4;
                    unsigned char* mrow = &mask[(size_t)Y * w];
                    if (!paintSkin(mrow, row, X, feather)) return false;
                    if (Y < by0) by0 = Y;      // 包围盒按**源** y 记，不按 u
                    if (Y > by1) by1 = Y;
                    return true;
                };
                // paintSkin 的「权重已算好」版本（跟随肤色时同一像素要算两次权重）
                auto paintWUV = [&](int u, int v, int wgt, int feather) -> bool {
                    int X = 0, Y = 0;
                    atUV(u, v, X, Y);
                    if (X < 0 || X >= w || Y < 0 || Y >= h) return false;
                    unsigned char* mrow = &mask[(size_t)Y * w];
                    if (!paintW(mrow, X, wgt, feather)) return false;
                    if (Y < by0) by0 = Y;
                    if (Y > by1) by1 = Y;
                    return true;
                };

                // 矩形与椭圆共用的横向范围。flat 用已 clamp 过的 nx0/nx1，保证逐位相同；
                // 其余方向 nx0/nx1 是按源 x 算的，与 v 无关，必须重算。
                const int vLo = flat ? (nx0 - oxI) : -vHalf;
                const int vHi = flat ? (nx1 - oxI) : (vHalf + 1);

                if (g_maskShape & 4) {
                    // 脖子：**逐行跟随肤色的实际边界**（3.1.20）。这里的「行」是 u、
                    // 「列」是 v，与源朝向无关；边界仍落在肤色真正结束的位置。
                    static thread_local std::vector<unsigned char> nvw;
                    const int maxHalf = (int)(2.0f * halfAcross * kNeckSkinMaxHalf);
                    const int minHalf = (int)(2.0f * halfAcross * kNeckSkinMinHalf);
                    const int span = 2 * maxHalf + 1;
                    if ((int)nvw.size() < span) nvw.assign((size_t)span, 0);
                    const int vL = -maxHalf, vR = maxHalf;
                    const int gap = 3;      // 连续 3 个非肤色像素算「到头」
                    for (int u = 0; u < uLen; u++) {
                        for (int v = vL; v <= vR; v++) {
                            int X = 0, Y = 0;
                            atUV(u, v, X, Y);
                            unsigned char wv = 0;
                            if (X >= 0 && X < w && Y >= 0 && Y < h) {
                                const unsigned char* row = src + ((size_t)Y * w) * 4;
                                wv = (unsigned char)skinWeight(row[X * 4 + 0],
                                                               row[X * 4 + 1],
                                                               row[X * 4 + 2]);
                            }
                            nvw[v - vL] = wv;
                        }
                        int lo = 0, hi = 0;
                        if (nvw[-vL] == 0) {
                            // 中心不是肤色（衣领挡住、下巴阴影）：这一行退回兜底宽度，
                            // 落笔时 nvw 仍然会把非肤色挡掉，不会真的画上去。
                            lo = -minHalf;
                            hi = minHalf;
                        } else {
                            int miss = 0;
                            for (int v = 0; v >= vL; v--) {
                                if (nvw[v - vL]) { lo = v; miss = 0; }
                                else if (++miss >= gap) break;
                            }
                            miss = 0;
                            for (int v = 0; v <= vR; v++) {
                                if (nvw[v - vL]) { hi = v; miss = 0; }
                                else if (++miss >= gap) break;
                            }
                            // 探到的范围太窄说明肤色被打断（胡须、镜框、阴影），
                            // 按兜底宽度铺开，免得掩码被切成碎片。
                            if (hi - lo < 2 * minHalf) {
                                lo = -minHalf;
                                hi = minHalf;
                            }
                        }
                        if (lo < vL) lo = vL;
                        if (hi > vR) hi = vR;
                        const int fBot = featherRamp(uLen - u, feN);
                        for (int v = lo; v <= hi; v++) {
                            int feather = fBot;
                            const int dl = v - lo + 1, dr = hi - v + 1;
                            const int fx2 = featherRamp(dl < dr ? dl : dr, feN);
                            if (fx2 < feather) feather = fx2;
                            paintWUV(u, v, nvw[v - vL], feather);
                        }
                    }
                } else if (g_maskShape & 2) {
                    // 脖子也用椭圆距离场（3.1.20）：最宽处落在下颌线 u=0，向下按椭圆收窄。
                    const float A = 2.0f * g_neck.halfW * halfAcross;
                    const float B = 2.0f * halfAlong * g_neck.len;
                    const float ia2 = 1.0f / (A * A), ib2 = 1.0f / (B * B);
                    const float rEff = 0.5f * (A + B);
                    const int eu0 = (int)(-B), eu1 = (int)(B);
                    for (int u = eu0; u < eu1; u++) {
                        const float dy = (float)u + 0.5f;
                        const float ty = dy * dy * ib2;
                        for (int v = vLo; v < vHi; v++) {
                            const float dx = (float)v + 0.5f + vCen;
                            const float q = sqrtf(dx * dx * ia2 + ty);
                            if (q >= 1.0f) continue;
                            const int dpx = (int)((1.0f - q) * rEff + 0.5f);
                            paintUV(u, v, featherRamp(dpx, feN));
                        }
                    }
                } else {
                    // 矩形（生产默认）：从 u=0 往下 uLen 像素，横向 vLo..vHi。
                    for (int u = 0; u < uLen; u++) {
                        const int fBot = featherRamp(uLen - u, feN);
                        for (int v = vLo; v < vHi; v++) {
                            const int dl = v - vLo + 1, dr = vHi - v;
                            int feather = fBot;
                            const int fx = featherRamp(dl < dr ? dl : dr, feN);
                            if (fx < feather) feather = fx;
                            paintUV(u, v, feather);
                        }
                    }
                }
            }
        }

        // 五官保护区：**只画眼睛，不画嘴巴**。
        // 参考实现的掩码只有 .g = eyes 一个保护通道，没有 lip —— 嘴唇在参考实现那里
        // 是被当皮肤磨的。3.1.14 之前我们多画了一个嘴部椭圆（kps[6..9] 那四行），
        // 那是自创的保护，100 档唇区残差 +25.5 的最可能根因，已删除以对齐结构。
        // 尺寸按脸框比例给（YuNet 只给 5 个点，没有轮廓，只能这样估）。
        memset(protect, 0, (size_t)w * h);
        for (const auto& f : faces) {
            if (!kpsSane(f)) continue;    // 关键点飞出去就跳过这张脸的保护
            // 1.0.5.0：脸宽高取**脸自身**的（未倾斜时 rw 为 0，退回 w/h）。
            // 用外接盒的话 45° 时眼罩被撑大 1.68 倍，眼睛周围一大片都不磨了。
            const float pw = (f.rw > 0.0f) ? f.rw : f.w;
            const float ph = (f.rh > 0.0f) ? f.rh : f.h;
            const float ex = pw * 0.12f, ey = ph * 0.075f;
            paintProtectEllipse(protect, w, h, f.kps[0], f.kps[1], ex, ey);
            paintProtectEllipse(protect, w, h, f.kps[2], f.kps[3], ex, ey);
        }

        pxOut = px;
        // ROI 只在这里算一次（掩码每 4 帧才重算），中间帧直接复用。
        // pad 必须 >= radius：ROI 边缘像素的邻域会往外读，切掉了结果就变了。
        if (bx1 < 0) {
            boundsOut = beautycore::RoiRect();          // 全零掩码
        } else {
            const int pad = g_cfg.radius + 1;
            beautycore::RoiRect r;
            r.x0 = (bx0 - pad < 0) ? 0 : bx0 - pad;
            r.y0 = (by0 - pad < 0) ? 0 : by0 - pad;
            r.x1 = (bx1 + pad + 1 > w) ? w : bx1 + pad + 1;
            r.y1 = (by1 + pad + 1 > h) ? h : by1 + pad + 1;
            boundsOut = r;
        }

        // 诊断：五官保护覆盖率按椭圆面积估，不扫全帧
        double prArea = 0.0;
        for (const auto& f : faces) {
            if (!f.hasKps) continue;
            const double pw = (f.rw > 0.0f) ? f.rw : f.w;
            const double ph = (f.rh > 0.0f) ? f.rh : f.h;
            const double ex = pw * 0.12, ey = ph * 0.075;
            prArea += 2.0 * 3.14159265 * ex * ey;
            const double mrx = fabsf(f.kps[8] - f.kps[6]) * 0.5 + pw * 0.05;
            prArea += 3.14159265 * mrx * (ph * 0.09);
        }
        char b[192];
        snprintf(b, sizeof(b),
                 "mask=%d px (%.2f%%) faces=%d roi=%.2f%% protect=%.2f%% kps=%d",
                 px, 100.0 * px / (double)((size_t)w * h), facesOut,
                 100.0 * (double)boundsOut.area() / (double)((size_t)w * h),
                 100.0 * prArea / (double)((size_t)w * h),
                 (faces.empty() || !faces[0].hasKps) ? 0 : 1);
        msgOut = b;
        return true;
    }

    // 检不出脸时的统一处理（同步/异步两条路共用）：
    // 丢掉一次检测结果 ≠ 脸消失了，先沿用旧掩码最多 kMaskHold 次。
    bool onDetectFailed(DetState& S, const std::string& ferr, int inputSize,
                        float bestScore) {
        BEAUTY_BIND_DET_ALL(S);
        lastFaces_ = 0;
        if (maskValid_ && maskHold_ < kMaskHold) {
            maskHold_++;
            char b[128];
            snprintf(b, sizeof(b), "detect lost, holding mask %d/%d",
                     maskHold_, kMaskHold);
            faceErr_ = b;
            return true;
        }
        maskValid_ = false;
        bounds_ = beautycore::RoiRect();     // 空矩形 = 无 ROI，调用方退回全帧
        // 诊断：把「推理输入边长」和「最高置信度」留下来。检不出脸时这两个
        // 数决定了该调尺寸还是该调阈值，缺了就只能瞎猜。
        char b[160];
        snprintf(b, sizeof(b), "no face x%d (input=%d best=%.3f%s%s)",
                 kMaskHold + 1, inputSize, bestScore,
                 ferr.empty() ? "" : " err=", ferr.c_str());
        faceErr_ = b;
        return false;
    }

    // ---- 异步检测 ------------------------------------------------
    //
    // 模型：一个 worker 线程 + 一个「输入槽」+ 一个「输出槽」。
    //   · 渲染线程：把结果 swap 走（O(1)），把本帧 memcpy 进输入槽（空闲时）。
    //   · worker：等输入槽有货 → 跑 buildMaskInto → 结果放进输出槽。
    // 渲染线程**永远不 wait**，所以检测再慢也只是「掩码晚一帧到位」。
    //
    // 为什么不做多缓冲/队列：检测只要 15ms，而提交周期是 4 帧（133ms），
    // 一个槽位绰绰有余。排队的意义是「一帧都不能丢」，但掩码本来就只需要最新
    // 那份 —— 中间结果没有价值（wtnl-zhi 的做法也是「只保留最新帧」）。
    struct AsyncState {
        std::mutex m;
        std::condition_variable cv;
        // 2026-11-10 代码审查 #1：worker 收工通知，供 releaseSlot 排空该 slot 的
        // pending 任务时等待。与 cv 分开，避免 submitAsync 的 notify_one 被
        // 等待者抢走（单 condition_variable 多谓词的经典丢唤醒问题）。
        std::condition_variable cvDone;
        std::thread th;
        bool quit = false;
        bool hasJob = false;      // 输入槽有货
        bool working = false;     // worker 正在算
        bool ready = false;       // 输出槽有结果待取
        std::vector<unsigned char> frame;
        int w = 0, h = 0;
        std::vector<unsigned char> mask;
        std::vector<unsigned char> protect;
        beautycore::RoiRect bounds;
        std::vector<beautycore::FaceBox> fbox;   // 本帧人脸（含关键点）
        int pixels = 0;
        int faces = 0;
        bool valid = false;
        int inputSize = 0;
        float bestScore = 0.0f;
        std::string msg;
        double ms = 0.0;
        int slot = 0;        // 这活是哪个实例提交的（结果只交还给它的上下文）
        // 2026-11-10 #1：worker 正在为哪个 slot 跑 buildMaskInto()。
        // 与 slot 分开记：releaseSlot 会把 slot 置为无效值，而等待谓词需要
        // 知道「旧任务是否真的结束」，不能靠被改过的 slot 判断。
        int runningSlot = -1;
    };
    AsyncState async_;
    bool asyncOn_ = true;         // 由 g_cfg.asyncDetect 初始化
    bool asyncStarted_ = false;
    double asyncMs_ = 0.0;        // 最近一次 worker 的耗时（诊断用）

    // ---- 3.1.10 掩码 ↔ 帧对齐（修「羽化压不住的拖影」）----------------------
    //
    // 3.1.9 之前，`mask_` 与它描述的帧是**脱钩**的：worker 在帧 k 上算掩码，
    // 渲染线程在帧 k+1~k+2 上用它。皮肤在动，掩码就永远落后 1~2 帧，边界每一帧
    // 都在脸后扫一条带 —— 羽化只能把这条带从"硬边"软成"淡边"，消不掉。
    //
    // 修法：把「掩码 + 它描述的那一帧」作为**一个整体**扣下来，磨皮直接处理那一帧。
    // 数据本来就在：worker 的输入槽 `async_.frame` 里存着它算掩码用的原始帧，而且
    // 结果收走时（collectAsync）worker 一定已经空闲 —— 交换出去零拷贝、无竞态。
    // 代价是输出整体落后 1 帧（30fps 下 33ms，摄像头链路里本来就不可见），
    // 收益是**掩码与画面逐像素同源**：脸后的背景不再被扫出一条带，脸的前缘也不再
    // 有一条"没磨"的粗边。
    //
    // 只在「结果刚到」的那一帧用（maskFresh_）：worker 偶尔慢了一帧，就退回旧的
    // 「当前帧 + 旧掩码」，**不重复输出已显示过的帧** —— 持续停顿比一次性对齐
    // 更显眼。30fps 下 worker 15ms < 33ms 帧预算，结果每帧都到，对齐是常态。
    std::vector<unsigned char> heldFrame_;   // 与 mask_ 同源的原始帧（RGBA）
    bool maskFresh_ = false;                 // 本帧刚收到一份新的有效结果
    bool alignOn_ = true;                    // BEAUTY_MASK_ALIGN=0 关闭（A/B 用）

    void startAsyncIfNeeded() {
        if (!asyncOn_ || asyncStarted_) return;
        asyncStarted_ = true;
        async_.th = std::thread([this] { asyncWorker(); });
        // 把 worker 降到「低于正常」：它晚一两帧出结果完全没关系（掩码本来就
        // 4 帧才更新一次），但渲染线程晚一帧就掉帧。让 OS 优先保渲染线程。
        SetThreadPriority(async_.th.native_handle(), THREAD_PRIORITY_BELOW_NORMAL);
    }

    void stopAsync() {
        if (!asyncStarted_) return;
        {
            std::lock_guard<std::mutex> lk(async_.m);
            async_.quit = true;
        }
        async_.cv.notify_all();
        async_.cvDone.notify_all();   // 2026-11-10 #1：唤醒可能正在排空的 releaseSlot
        if (async_.th.joinable()) async_.th.join();
        asyncStarted_ = false;
    }

    // 把本帧交给 worker。worker 忙就直接放弃这一轮（下一个周期再说）——
    // 排队没有意义，掩码只需要最新的那份。
    void submitAsync(int slot, const unsigned char* src, int w, int h) {
        if (!src || w <= 0 || h <= 0) return;
        const size_t bytes = (size_t)w * (size_t)h * 4;
        {
            std::lock_guard<std::mutex> lk(async_.m);
            // 2026-11-10 代码审查 #4：ready 还没被取走时不能覆盖输出槽，
            // 否则提交它的那个 slot 永远拿不到结果（多实例下掩码静默不更新）。
            if (async_.hasJob || async_.working || async_.ready) return;
            if (async_.frame.size() != bytes)
                async_.frame.resize(bytes);
            async_.w = w;
            async_.h = h;
            async_.slot = slot;
            // 2026-11-10 #4：帧拷贝与 collectAsync 的 heldFrame_.swap 共用
            // async_.m。原来放锁外是为了省 0.7ms 持锁时间，但与 swap 无互斥。
            // worker 读帧时 working=true，这里被 hasJob/working 门挡住，天然串行。
            memcpy(&async_.frame[0], src, bytes);
            async_.hasJob = true;
            g_maskSubmits++;      // 诊断计数：只在**真的提交了**时才加
        }
        async_.cv.notify_one();
    }

    // 收走 worker 的结果。返回 true = 这一轮确实消费了一个结果。
    // cw/ch 是当前帧尺寸（1.0.0.3 加入）：worker 的结果是按「提交那一刻」的
    // 帧尺寸算的，跨尺寸的结果一律丢弃 —— 交换进来的 mask/bounds 是旧坐标
    // 系的，配当前帧就是越界（真机 e2e 复现的崩溃点）。
    bool collectAsync(int slot, int cw, int ch) {
        DetState& S = slots_[slot];
        BEAUTY_BIND_DET_ALL(S);
        beautycore::RoiRect b;
        int px = 0, faces = 0, inputSize = 0;
        float best = 0.0f;
        bool valid = false, got = false, sizeOk = true;
        std::string msg;
        double ms = 0.0;
        {
            std::lock_guard<std::mutex> lk(async_.m);
            // 结果只交给**提交它的那个 slot**。别的实例来取就当作还没到 ——
            // 否则 A 会拿走 B 的掩码，等于把刚修掉的串扰换个地方又装回来。
            if (async_.ready && async_.slot == slot) {
                // 只有「有脸」时才换缓冲：没脸时 worker 的 mask 内容无意义，
                // 换进来会把当前正在用的掩码冲掉（丢帧保持就失效了）。
                // 1.0.0.3：还要「尺寸一致」—— 场景切换等时刻，提交任务时的
                // 帧尺寸可能已经不等于当前帧尺寸，旧结果必须整批丢弃。
                sizeOk = (async_.w == cw && async_.h == ch);
                if (async_.valid && sizeOk) {
                    mask_.swap(async_.mask);
                    protect_.swap(async_.protect);
                    faces_.swap(async_.fbox);
                    // 3.1.10：把**这份掩码描述的原始帧**一起扣下来。此时 worker
                    // 必然空闲（ready=working 结束），帧槽没人读写，swap 无竞态；
                    // swap 之后帧槽里是被换出的旧 heldFrame_，下一次 submitAsync
                    // 的 memcpy（同样要求 worker 空闲）会先把它覆盖掉再交活。
                    if (async_.frame.size() ==
                        (size_t)async_.w * async_.h * 4) {
                        heldFrame_.swap(async_.frame);
                        maskFresh_ = true;   // 渲染线程自己在 process 里消费
                    }
                }
                b = async_.bounds;
                px = async_.pixels;
                faces = async_.faces;
                valid = async_.valid && sizeOk;
                inputSize = async_.inputSize;
                best = async_.bestScore;
                msg = async_.msg;
                ms = async_.ms;
                async_.ready = false;
                got = true;
            }
        }
        if (!got) return false;
        asyncMs_ = ms;
        if (valid) {
            bounds_ = b;
            maskPixels_ = px;
            lastFaces_ = faces;
            maskHold_ = 0;
            maskValid_ = true;
            faceErr_ = msg;
        } else if (sizeOk) {
            onDetectFailed(S, msg, inputSize, best);
        }
        // 尺寸不一致的结果（!sizeOk）：整批丢弃，且**不**计入检测失败迟滞 ——
        // 检测本身没失败，只是结果属于旧坐标系。
        return true;
    }

    void asyncWorker() {
        for (;;) {
            std::vector<unsigned char> mask, protect;
            int w = 0, h = 0, slot = 0;
            {
                std::unique_lock<std::mutex> lk(async_.m);
                async_.cv.wait(lk, [this] { return async_.quit || async_.hasJob; });
                if (async_.quit) return;
                mask.swap(async_.mask);
                protect.swap(async_.protect);
                w = async_.w;
                h = async_.h;
                slot = async_.slot;
                async_.hasJob = false;
                async_.working = true;
                async_.runningSlot = slot;   // 2026-11-10 #1：供 releaseSlot 排空等待
            }
            if (slot < 0 || slot >= kMaxSlots) slot = 0;

            beautycore::RoiRect b;
            std::vector<beautycore::FaceBox> fbox;
            int px = 0, faces = 0, inputSize = 0;
            float best = 0.0f;
            std::string msg;
            const double t0 = nowMsCore();
            const bool ok = buildMaskInto(slots_[slot], &async_.frame[0], w, h,
                                          mask, protect, b, fbox, px, faces, msg);
            inputSize = face_.inputSize();
            // 1.0.13.4：从本 slot 的 DetState 取，不读共用检测器的成员
            best = slots_[slot].detBest;
            const double ms = nowMsCore() - t0;

            {
                std::lock_guard<std::mutex> lk(async_.m);
                async_.mask.swap(mask);
                async_.protect.swap(protect);
                async_.fbox.swap(fbox);
                async_.bounds = b;
                async_.pixels = px;
                async_.faces = faces;
                async_.valid = ok;
                async_.inputSize = inputSize;
                async_.bestScore = best;
                async_.msg = msg;
                async_.ms = ms;
                async_.working = false;
                async_.ready = true;
                async_.runningSlot = -1;     // 2026-11-10 #1：旧任务已收工
            }
            async_.cvDone.notify_all();      // 唤醒正在排空该 slot 的 releaseSlot
        }
    }

    // 亮度 Sobel 梯度 → 0..256 的「边缘强度」（256 = 强边缘，完全不磨）。
    //
    // 为什么需要它：双边滤波靠「颜色差大 → 权重小」隐式保护边缘，对高频纹理
    // 有效，但对**同色系的硬边**（黑眉毛压在皮肤上、眼镜框边缘）保护不足，
    // 会把边缘磨成渐变。显式梯度门控把「真边缘」和「皮肤瑕疵」分开：
    // 前者梯度大、后者梯度小。
    //
    // 用 |gx|+|gy| 代替 sqrt(gx²+gy²)：边缘检测本来就容忍近似，L1 省掉一次
    // 开方，在 1080p 十几万像素上是实打实的差别。
    //
    // 阈值为什么是「死区 + 斜坡」而不是 wuxiwuhen 的「线性 ×10」：
    // 实测这张图的梯度分布（归一化到 0..1）是
    //     脸颊平坦处  中位 0.020 / 90 分位 0.082
    //     眉毛横带    中位 0.017 / 90 分位 0.111   ← 中位数比脸颊还低！
    // 眉毛横带的**中位数**和脸颊一样，因为那个区域里大部分像素是眉间的皮肤，
    // 只有眉毛本体是高梯度。所以 Sobel 标的是「边缘线」而不是「区域」，
    // 线性放大 ×10 会让皮肤纹理（0.02×10=0.2）也吃到 20% 门控 —— 实测确实
    // 如此：低梯度区保留率被从 84% 抬到 94%，等于整体少磨了一大截。
    // 正确做法是给死区：低于 0.10 完全不门控，高于 0.30 完全门控。
    // 阈值按 G 通道尺度标定（G 0..255，Sobel 系数和 4 → gx 上界 ±1020）。
    // 原 luma*1000 口径下的 0.10/0.30 归一化，等价换算到这里是 102/306。
    static const int kEdgeLo = 102;
    static const int kEdgeHi = 306;

    static int sobelEdge(const unsigned char* src, int w, int h,
                         int x, int y, int k) {
        const int xm = (x > 0) ? (x - 1) : 0;
        const int xp = (x + 1 < w) ? (x + 1) : (w - 1);
        const int ym = (y > 0) ? (y - 1) : 0;
        const int yp = (y + 1 < h) ? (y + 1) : (h - 1);
        const unsigned char* r0 = src + (size_t)ym * w * 4;
        const unsigned char* r1 = src + (size_t)y * w * 4;
        const unsigned char* r2 = src + (size_t)yp * w * 4;

        // 用 G 通道当亮度（人眼对绿最敏感，梯度性质与 luma 基本一致）。
        // 完整 luma 要 3 次乘加 × 8 邻居 = 24 次/像素，实测这占了门控开销的
        // 大头；换成直接读 G 通道后少掉 2/3 的算术，阈值按同一口径重新标定过。
        const int l00 = r0[xm * 4 + 1];
        const int l01 = r0[x * 4 + 1];
        const int l02 = r0[xp * 4 + 1];
        const int l10 = r1[xm * 4 + 1];
        const int l12 = r1[xp * 4 + 1];
        const int l20 = r2[xm * 4 + 1];
        const int l21 = r2[x * 4 + 1];
        const int l22 = r2[xp * 4 + 1];

        const int gx = (l02 + 2 * l12 + l22) - (l00 + 2 * l10 + l20);
        const int gy = (l20 + 2 * l21 + l22) - (l00 + 2 * l01 + l02);
        const int mag = ((gx < 0 ? -gx : gx) + (gy < 0 ? -gy : gy)) / 2;

        // k 是灵敏度倍数（越大越容易判为边缘）：k=10 用标定好的阈值，
        // k=5 把上阈值翻倍（更难门控），k=20 减半（更激进）。
        int hi = (k > 0) ? (kEdgeHi * 10 / k) : kEdgeHi;
        if (hi <= kEdgeLo + 1) hi = kEdgeLo + 1;
        if (mag <= kEdgeLo) return 0;
        if (mag >= hi) return 256;
        return (int)((long long)(mag - kEdgeLo) * 256 / (hi - kEdgeLo));
    }

    // 线程数决策。行数太少时线程创建开销大于收益，直接单线程。
    static int blendThreads(int threads, int h) {
        int n = threads;
        if (n <= 0) {
            const unsigned hc = std::thread::hardware_concurrency();
            n = hc ? (int)hc : 4;
            if (n > 8) n = 8;
        }
        if (h < 32) return 1;
        const int byRows = h / 16;
        if (n > byRows) n = byRows;
        return (n < 1) ? 1 : n;
    }

    // 只在掩码内混合：掩码外逐字节保持原图。
    // 按行多线程：掩码外虽然是简单拷贝，1080p 也是 200 万像素，单线程要 2~3ms。
    static void blendWithMask(const unsigned char* src, const unsigned char* sm,
                              unsigned char* dst, int w, int h, float t,
                              const unsigned char* mask,
                              const unsigned char* protect, int protectK) {
        const int ti = (int)(t * 256.0f + 0.5f);
        const int inv = 256 - ti;
        const int kEdge = g_cfg.edgeK;
        const int kLimitThr = g_cfg.limitThr;

        auto runRows = [&](int yBegin, int yEnd) {
        for (int y = yBegin; y < yEnd; y++) {
            const size_t rowOff = (size_t)y * w;
            for (int x = 0; x < w; x++) {
                const size_t o = (rowOff + x) * 4;
                if (mask[rowOff + x] == 0) {    // 掩码外：逐字节还原
                    dst[o + 0] = src[o + 0];
                    dst[o + 1] = src[o + 1];
                    dst[o + 2] = src[o + 2];
                    dst[o + 3] = src[o + 3];
                    continue;
                }
                int k = (ti * mask[rowOff + x]) >> 8;   // 掩码值也参与权重
                // 五官保护：眼睛、嘴巴上的磨皮按 protectK 减弱
                if (protect && protectK > 0) {
                    const int p = (int)protect[rowOff + x] * protectK / 100;
                    k = (k * (256 - p)) >> 8;
                }
                if (kEdge > 0) {
                    const int e = sobelEdge(src, w, h, x, y, kEdge);
                    // e=0 时与上面的公式逐位相同，保证「不门控」与旧行为一致
                    k = (k * (256 - e)) >> 8;
                }
                // 阈值软膝（立体感）：只抹「小幅度起伏」（坑洼、斑点、毛孔），
                // 鼻梁两侧、下颌线这类**大幅度明暗过渡**按比例保住，
                // 否则过渡带被抹平后脸会显得塌、出现台阶。
                // 公式同 lumina：limit = 1 - smoothstep(thr, thr*2.5, |src-sm|)
                if (kLimitThr > 0 && k > 0) {
                    int dmax = 0;
                    for (int c = 0; c < 3; c++) {
                        int dv = (int)src[o + c] - (int)sm[o + c];
                        if (dv < 0) dv = -dv;
                        if (dv > dmax) dmax = dv;
                    }
                    const int hi = kLimitThr * 5 / 2;
                    int limit;
                    if (dmax <= kLimitThr) {
                        limit = 256;
                    } else if (dmax >= hi) {
                        limit = 0;
                    } else {
                        limit = 256 * (hi - dmax) / (hi - kLimitThr);
                    }
                    k = (k * limit) >> 8;
                }
                const int ki = 256 - k;
                dst[o + 0] = (unsigned char)(((int)src[o + 0] * ki + (int)sm[o + 0] * k + 128) >> 8);
                dst[o + 1] = (unsigned char)(((int)src[o + 1] * ki + (int)sm[o + 1] * k + 128) >> 8);
                dst[o + 2] = (unsigned char)(((int)src[o + 2] * ki + (int)sm[o + 2] * k + 128) >> 8);
                dst[o + 3] = src[o + 3];
            }
        }
        };

        const int nt = blendThreads(g_cfg.threads, h);
        if (nt <= 1) {
            runRows(0, h);
            return;
        }
        // 持久线程池（3.1.21）。这里原来每帧 new 一组 std::thread 再 join，
        // 实测光建线程就要 0.29 ms × nt，一帧 21 趟下来 6 ms 上下。
        beautycore::parallelRows(0, h, nt, runRows);
        (void)inv;
    }

    // **同步**路径的重算周期（帧）。异步路径用 g_cfg.maskEveryAsync（默认 0 = 每帧）。
    // 两条路必须分开：同步时检测压在渲染线程上，每帧跑就是每帧 +14ms（掉帧）；
    // 异步时它跑在 worker 上，每帧跑只多烧 42% 的一个核。
    // 这个 4 也决定了离线台架的口径 —— cpu_bench / verify_roi / detail_test 全走同步，
    // 所以它们报的每帧毫秒里，检测成本是按 1/5 摊的。别拿它直接对生产值。
    static const int kMaskEverySync = 4;
    // 连续丢检多少次之后才真正放弃掩码。
    //
    // 1.0.13.6：6 → 8。这个数是「丢检**次数**」不是帧数，两条路口径不同：
    // 同步路径每 kMaskEverySync(4) 帧检测一次，异步路径每帧一次（默认）。
    // 原来 6 次在异步下只等于 6 帧，而「头歪到 45° 时 YuNet 连续检不出」实测
    // 就是 8 帧 —— 第 7、8 帧掩码被清空，磨皮和三项形变整块停用，画面上就是
    // 一次可见的闪。取 8 正好盖住这个窗口；同步路径下 8×4=32 帧 ≈ 1 秒，只影响
    // 台架口径（真机走异步）。
    static const int kMaskHold = 8;

    // 检测态（方向 / 掩码 / 计数）已全部下沉到 DetState：每个 slot 存一份，
    // 不再有「一份状态给所有实例用」。类型与绑定宏见类首。
    beautycore::FaceDetector face_;
    bool faceTried_ = false;
    bool faceOk_ = false;

    DetState slots_[kMaxSlots];
    bool slotUsed_[kMaxSlots] = {};
    std::string faceLoadErr_;   // 模型加载错误（发生在 slot 分配之前）
    std::mutex slotsMtx_;      // 只保护 slotUsed_ 的发放/回收，不保护上下文内容
    std::mutex initMtx_;       // 1.0.13.4：串行化 ensureReady（faceTried_ 闸门）
    int diagSlot_ = 0;         // lastFaces / lastRoi / lastErr 读哪个 slot

    // slot 的检测态初值。方向来自 BEAUTY_INPUT_ROT（环境变量是进程级配置，
    // 每个实例读到的都一样），计数器一律归零。
    void initDetState(DetState& d) {
        const char* ird = beauty_env("BEAUTY_INPUT_ROT");
        if (ird && *ird) {
            int v = ((atoi(ird) % 360) + 360) % 360;
            if (v == 90 || v == 180 || v == 270) d.rotManual = v;
        }
        d.effRot = d.rotManual;     // 手工声明优先；0 时交给自动探测
        if (d.rotManual != 0) {
            NALOG(BEAUTY_LOG_INFO,
                  "[美颜] 输入方向由 BEAUTY_INPUT_ROT 指定为 %d°（自动探测关闭）",
                  d.rotManual);
        }
    }
    // ---- 纯 scratch（**故意留在类上，不按 slot 分**）----------------------
    // 这些缓冲的共同点：每次调用都是「先整片写、再读」，内容不跨帧传递，
    // 所以多实例顺序复用它不会串数据，只是省内存（1080p 下这堆合计 ~60 MB，
    // 按 8 个 slot 各一份会直接吃掉半个 GB）。
    // 前提是「同一时刻只有一个线程在跑 process」—— 现在是成立的：OBS 的
    // video_render 只从渲染线程进来，异步检测走的是另一条路径（只碰 DetState）。
    // 如果将来出现多线程同时调 process 的场景，这批缓冲必须跟着下沉。
    std::vector<unsigned char> smooth_;
    std::vector<unsigned char> warpScratch_;   /* 3.1.27：美形的 ROI 采样源 */
    std::vector<unsigned char> lowBuf_;   // 高低频的低频层
    std::vector<unsigned char> scratch_;  // 可分离高斯的中间缓冲
    std::vector<float> guideScratch_;     // 引导滤波的 float 缓冲
    std::vector<float> clarityScratch_;   // clarity 的灰度 box 缓冲
    std::vector<float> detailScratch_;    // 锐化的 4 个亮度平面
    std::vector<float> spotScratch_;      // 祛斑痘的两个浮点平面
    std::vector<float> s3ScratchA_;       // surface3 的 b1 平面（6 个 ROI 平面）
    std::vector<float> s3ScratchB_;       // surface3 的 b2 平面（同上，不能共用）
    // 时序 EMA（motionPrev / detailLumT / frameNo / detailEmaGen）与分段耗时
    // 已全部下沉到 DetState —— 它们都是有记忆的状态，共享会让两个实例互相
    // 推进帧序号、互相覆盖耗时。判据见 DetState 里的注释。

    // 运动判据：全帧亮度帧间差的均值（4×4 抽样，单位=灰阶，0..255）。
    // 顺手把快照推进一帧。首帧返回一个「大值」，让调用方按运动处理（beta=1），
    // 避免从空历史起步时把画面拉向黑。
    double updateMotion(DetState& S, const unsigned char* src, int w, int h) {
        const int sw = w / 4, sh = h / 4;
        if (!src || sw <= 0 || sh <= 0) return 255.0;
        const size_t n = (size_t)sw * (size_t)sh;
        if (S.motionPrev.size() != n) {
            S.motionPrev.assign(n, 0);
            S.motionHave = false;
        }
        uint64_t acc = 0;
        for (int y = 0; y < sh; y++) {
            const unsigned char* row = src + (size_t)(y * 4) * w * 4;
            unsigned char* pr = &S.motionPrev[(size_t)y * (size_t)sw];
            for (int x = 0; x < sw; x++) {
                const unsigned char* q = row + (size_t)(x * 4) * 4;
                // 77/151/28 是整数版 0.299/0.587/0.114，和 detailRefill 的浮点
                // 权重略有出入，但这里只用来判「动没动」，不需要与它逐位一致。
                const int l = (q[0] * 77 + q[1] * 151 + q[2] * 28) >> 8;
                const int d = l - (int)pr[x];
                acc += (uint64_t)(d < 0 ? -d : d);
                pr[x] = (unsigned char)l;
            }
        }
        if (!S.motionHave) {
            S.motionHave = true;
            return 255.0;
        }
        return (double)acc / (double)n;
    }

    // 帧间差 → 新帧权重 beta。<= still 视为静止（强平滑），>= full 完全不平滑。
    // 中间线性过渡，避免在阈值附近抖动导致「时有时无」的观感。
    float emaBeta(double motion) const {
        if (!g_cfg.emaOn) return 1.0f;
        if (motion <= (double)g_cfg.emaStill) return g_cfg.emaBetaStill;
        if (motion >= (double)g_cfg.emaFull) return 1.0f;
        const double t = (motion - (double)g_cfg.emaStill) /
                         ((double)g_cfg.emaFull - (double)g_cfg.emaStill);
        return (float)(g_cfg.emaBetaStill + (1.0 - g_cfg.emaBetaStill) * t);
    }

    // ---- 人脸局部五项 ------------------------------------------------------
    // 五官立体 / 亮眼 / 去黑眼圈 / 去法令纹 / 祛斑痘。
    //
    // 几何全部相对**脸框 + 5 个关键点**，没有一个绝对像素值 —— 理由见
    // beauty_region.h：绝对像素在 720p 会移到瞳孔上、在 4K 又跑到下眼睑。
    //
    // 为什么必须放在磨皮与美白之后：
    //   · 放磨皮之前，刚提亮的眼白会被磨皮平均掉，变成一片雾；
    //   · 放美白之前，两次抬亮叠加容易把眼白/牙齿推过 255，出现死白斑。
    //
    // 五项共用一次 applyEllipses（增益相加），因为它们的贡献互不干扰：
    // 面板为 0 的那项贡献恒为 0，所以「只开一项」和「五项全开」都能各自对拍。
    void applyFaceRegions(DetState& S, unsigned char* dst, int w, int h,
                          const BeautySettings& s) {
        BEAUTY_BIND_DET_ALL(S);
        const float threed = clampi01(s.panel[P_THREED] / 100.0);
        const float eye = clampi01(s.panel[P_EYEBRIGHT] / 100.0);
        const float pouch = clampi01(s.panel[P_POUCH] / 100.0);
        const float naso = clampi01(s.panel[P_NASOLABIAL] / 100.0);
        const float spot = clampi01(s.panel[P_DELSPOT] / 100.0);
        if (threed <= 0.0f && eye <= 0.0f && pouch <= 0.0f && naso <= 0.0f &&
            spot <= 0.0f)
            return;
        if (beauty_env("BEAUTY_REGION_DEBUG")) {
            for (const auto& f : faces_) {
                fprintf(stderr, "[dbg] face x=%.1f y=%.1f w=%.1f h=%.1f kps=%d "
                        "kps=(%.1f,%.1f)(%.1f,%.1f)(%.1f,%.1f)(%.1f,%.1f)(%.1f,%.1f)\n",
                        f.x, f.y, f.w, f.h, (int)f.hasKps,
                        f.kps[0], f.kps[1], f.kps[2], f.kps[3], f.kps[4], f.kps[5],
                        f.kps[6], f.kps[7], f.kps[8], f.kps[9]);
            }
        }
        if (faces_.empty() || mask_.size() != (size_t)w * h) return;

        const unsigned char* mk = &mask_[0];
        std::vector<beautycore::Ellipse> els;
        els.reserve(48);
        // 法令纹走的是「暗度填平」模型，区域椭圆与其它三项分开收集，
        // 因为它的作用方式不是「加常量」而是「min(封顶, 斜率×暗差)」。
        std::vector<beautycore::Ellipse> nasoEls;
        nasoEls.reserve(4);
        // 法令纹**下瓣**（常量增益椭圆）：在 applyFoldRemoval 之后叠加，
        // 免得影响上瓣的邻域最大 LR 计算。
        std::vector<beautycore::Ellipse> nasoTailEls;
        nasoTailEls.reserve(2);
        float nasoSlope = 0.0f;


        for (const auto& f : faces_) {
            if (f.w < 8.0f || f.h < 8.0f) continue;
            const float fx = f.x, fy = f.y, fw = f.w, fh = f.h;
            // 关键点不可信时只保留「不需要位置」的祛斑痘，其余四项跳过：
            // 位置错了会把亮度糊到脸颊/背景上，比不做更糟。
            const bool kp = kpsSane(f);

            if (kp) {
                // 归一化坐标（相对脸框）
                auto nx = [&](float px) { return (px - fx) / fw; };
                auto ny = [&](float py) { return (py - fy) / fh; };
                const float e0x = nx(f.kps[0]), e0y = ny(f.kps[1]);
                const float e1x = nx(f.kps[2]), e1y = ny(f.kps[3]);
                const float nsx = nx(f.kps[4]), nsy = ny(f.kps[5]);
                const float m0x = nx(f.kps[6]), m0y = ny(f.kps[7]);
                const float m1x = nx(f.kps[8]), m1y = ny(f.kps[9]);

                if (threed > 0.0f) {
                    // 3.1.22：五官立体 = 8 个锚在关键点上的宽椭圆。
                    //
                    // 三条实测结论（数据见 06_离线验证/全项对齐_20261030/
                    // _grid_seg.py 的分段输出 与 fit_threed.json）：
                    //  1. 参照是**解剖/网格驱动**的：额头恒亮、脖子恒暗，与画面
                    //     自身明暗无关。之前的「低频明暗场」路线实测 corr≈0.05，
                    //     已废弃。
                    //  2. 参照的**面部中线 = 双眼中点**，不是 YuNet 的鼻尖 ——
                    //     侧脸时鼻尖会偏 0.12 脸宽，参照中线不偏。鼻梁/鼻底/
                    //     额头/下颌全部锚在 midX/midY 上。
                    //  3. 提亮区是**大片平顶**、压暗区是**窄带**，所以 feather
                    //     分两组（亮 0.705 / 暗 0.378）。
                    //
                    // 拟合集（m00/m03/m06）评分 79.67，留出集（m01/m02/m04/
                    // m05/m07）78.17 —— 没有过拟合。
                    //
                    // 3.1.23：重新拟合时把**引擎自己的皮肤软掩码**也模拟进去了
                    // （applyEllipses 会 acc *= mw）。不模拟这一层会高估增益。
                    const float g = g_cfg.regThreedGain * threed;
                    const float midX = (e0x + e1x) * 0.5f;
                    const float midY = (e0y + e1y) * 0.5f;
                    const float mouthMidX = (m0x + m1x) * 0.5f;
                    const float mouthMidY = (m0y + m1y) * 0.5f;
                    const float feB = 0.705f;   // 亮部 feather（大平顶）
                    const float feD = 0.378f;   // 暗部 feather（窄带）
                    const float sh = 0.15f;
                    // 3.1.23：8 帧**统一**重拟合（_fit_region.py threed --all），
                    // 模拟器评分 80.36（chg 2.491 / 参照 2.479，corr 0.798）。
                    // 绝对值 = THREED_SPEC 基准 + 拟合偏移（fit_threed.json）。
                    // 额头（宽、浅、在眉线上方）
                    els.push_back({midX - 0.010000f, midY - 0.210000f, 0.350f,
                                   0.115f, 0.0f, g * 8.525f, sh, feB});
                    // 眉弓 / 眼窝（压暗）
                    els.push_back({midX - 0.030000f, midY - 0.060000f, 0.352500f,
                                   0.145f, 0.0f, g * -2.150f, sh, feD});
                    // 鼻梁（窄竖条）
                    els.push_back({midX - 0.025000f, midY + 0.000000f, 0.050f,
                                   0.180f, 0.0f, g * 6.900f, sh, feB});
                    // 左 / 右颧骨
                    els.push_back({e0x - 0.045000f, e0y + 0.117500f, 0.152500f,
                                   0.100f, 0.0f, g * 7.650f, sh, feB});
                    els.push_back({e1x - 0.012500f, e1y + 0.125000f, 0.150f,
                                   0.112500f, 0.0f, g * 10.6375f, sh, feB});
                    // 鼻底 / 上唇阴影（横向压暗）
                    els.push_back({midX - 0.005000f, midY + 0.195000f, 0.290f,
                                   0.092500f, 0.0f, g * -7.250f, sh, feD});
                    // 下巴
                    els.push_back({mouthMidX - 0.020000f, mouthMidY + 0.155000f,
                                   0.110f, 0.070f, 0.0f, g * 9.650f,
                                   sh, feB});
                    // 下颌 / 脖子（大面积压暗）
                    els.push_back({midX + 0.067500f, midY + 0.500000f, 0.507500f,
                                   0.190f, 0.0f, g * -4.800f, sh, feD});
                }
                if (eye > 0.0f) {
                    const float g = g_cfg.regEyeGain * eye;
                    // 眼白提亮。shade 给 0.35：眼白本来就接近饱和，按亮度加权
                    // 之后高光不会继续被推（推过去就是一块死白，观感比不提更差）。
                    // rx 从 0.075 放到 0.10：参考实现的亮眼 bbox 宽 0.65 脸宽
                    // （从内眼角一直盖到外眼角），0.075 只盖住瞳孔那一小块，
                    // 眼白提亮不完整，观感是「两个亮点」而不是「眼睛变亮」。
                    els.push_back({e0x, e0y, 0.100f, 0.055f, 0.0f, g, 0.35f, 0.35f});
                    els.push_back({e1x, e1y, 0.100f, 0.055f, 0.0f, g, 0.35f, 0.35f});
                }
                if (pouch > 0.0f) {
                    // 3.1.22：去黑眼圈 = 双层椭圆（亮核 + 淡晕）。
                    //
                    // 实测：参照的两个眼袋与**暗度无关**（corr(原亮度,Δ) ≈ +0.1），
                    // 是纯几何区域 —— 所以用固定形状的椭圆是对的。
                    // 3.1.23：改成**斜向窄脊**（_pouch_map.py 实测）。
                    //
                    // 参照的响应不是水平椭圆带，而是一条斜向窄脊：
                    // m00 眼R 从 (x=0.66,y=0.43) 斜向右下到 (x=0.74,y=0.50)，
                    // 宽约 12 px、长约 62 px、方向约 41°。
                    // 椭圆能表达这条脊：rx = 脊长（脸宽单位）、ry = 脊宽（脸高单位）、
                    // rot = 脊方向。注意 rx 按 faceW 缩放、ry 按 faceH 缩放。
                    //
                    //  · 核   ：rx 0.0950 / ry 0.0300，增益 10.25，平台窄
                    //  · 晕   ：rx 0.2050 / ry 0.0600，增益 3.00，铺开
                    //  · 位置 ：眼下方 0.064 脸高
                    //  · 转头时近侧眼袋在画面上被拉宽 → rx *= 1 − yawK·yaw·side
                    //    （yaw = 鼻尖相对眼中点的横向偏移 / 眼距）
                    const float g = g_cfg.regPouchScale * pouch;
                    const float eyeDist = e1x - e0x;
                    const float yaw = (eyeDist > 0.01f)
                                          ? (nsx - (e0x + e1x) * 0.5f) / eyeDist
                                          : 0.0f;
                    struct Side { float ex, ey, dx, dy, rot; int sgn; };
                    const Side sides[2] = {
                        {e0x, e0y, -0.0532f, 0.0638f, 0.0633f, -1},
                        {e1x, e1y, 0.0094f, 0.0666f, 0.5817f, +1},
                    };
                    for (int i = 0; i < 2; i++) {
                        const Side& s = sides[i];
                        float w = 1.0f - g_cfg.regPouchYawK * yaw * (float)s.sgn;
                        if (w < 0.25f) w = 0.25f;
                        const float r = s.rot * (float)s.sgn;
                        // 核（窄而强）
                        els.push_back({s.ex + s.dx, s.ey + s.dy,
                                       0.0750f * w, 0.0220f, r, g * 10.2500f,
                                       0.4000f, 0.3187f});
                        // 晕（宽而弱）
                        els.push_back({s.ex + s.dx, s.ey + s.dy,
                                       0.2050f * w, 0.0600f, r, g * 3.0000f,
                                       0.2000f, 0.4600f});
                    }
                }
                if (naso > 0.0f) {
                    // 3.1.22：去法令纹 = **暗度驱动**（不是固定形状 + 固定亮度）。
                    //
                    // 实测（_region_model.py / _naso_fill.py）：
                    //  · 参照的峰值像素 Δ **恒等于 +52**（封顶）
                    //  · corr(原亮度, Δ) = −0.37 ~ −0.44 → 越暗提得越多
                    //  · 输出值可以超过邻域最大值 → 不是「填到邻域均值」
                    // 所以模型是：Δ = min(maxLift, slope·max(0, LR − Y))，
                    // LR = 邻域最大亮度（半径 6）。区域用两个椭圆限定（哪条线
                    // 是法令纹由「暗线在哪」自己决定，脸一转也跟得上）。
                    //
                    // 拟合集 60.18，留出集 54.65。
                    //
                    // 3.1.23：模型升级（8 帧统一拟合）
                    //  1. 区域改成**窄椭圆**，锚在「眼正下方 0.13 脸高」——
                    //     实测参照的法令纹响应就在这个位置（沿眼下方竖线扫描，
                    //     峰值 Δ 恒为 51~52，且只有 5~8 px 宽）。
                    //  2. 限制因子从「皮肤掩码」改成 max(皮肤掩码, 区域权重)：
                    //     皮肤掩码是肤色椭圆，褶皱越深掩码越低，引擎恰好在
                    //     最该提亮的线上把效果掐掉（corr(掩码,参照Δ) = −0.66）。
                    //  3. 加**暗线闸门** gate(d)，把响应宽度收到褶皱线上。
                    //
                    // 3.1.23 第二轮：改成**双瓣**模型（naso6，8 帧统一拟合）
                    //
                    // 依据（_naso_line.py，沿眼下方竖线扫描的峰值剖面，m00 眼R）：
                    //     dy(眼下方脸高)  参照 Δ   旧模型(naso5) Δ
                    //          0.13          11.7        23.9
                    //          0.15          18.3        60.0（封顶，过冲）
                    //          0.17          48.0（峰）  60.0（封顶）
                    //          0.19           5.2        14.0
                    //          0.23           6.7         3.8
                    //          0.25           8.0         0    ← 下瓣从这开始
                    //          0.31          12.0         0    ← 下瓣自己的峰
                    //          0.45           0.7         0
                    // 参照的响应有**两个瓣**：
                    //   · 上瓣 = 真正的褶皱线（窄、强，峰在眼下方 0.17 脸高）
                    //   · 下瓣 = 褶皱朝嘴角延伸的那一段（宽、弱，dy 0.25~0.45）
                    // 旧模型只有上瓣，而且上瓣还过冲到封顶 60（参照峰才 48）。
                    //
                    // 下瓣的幅度只有 3~12 灰阶，且和亮度无关（那儿并不暗），
                    // 所以**不能**用暗度驱动表达 —— 改用**常量增益椭圆**
                    // （和五官立体同一套原语）。下瓣在 applyFoldRemoval **之后**
                    // 叠加，避免影响上瓣的邻域最大 LR 计算。
                    const float g = naso;
                    const float slope = g_cfg.regNasoSlope * g;
                    struct Side { float ex, ey, dx, dy, rot; };
                    const Side sides[2] = {
                        //   dx      dy      rot      rx     ry
                        {e0x, e0y, -0.0085f, 0.1496f, 0.2766f},
                        {e1x, e1y, -0.0295f, 0.1148f, 0.3266f},
                    };
                    for (int i = 0; i < 2; i++) {
                        const Side& s = sides[i];
                        nasoEls.push_back({s.ex + s.dx, s.ey + s.dy, 0.0800f,
                                           0.1500f, s.rot, 0.0f, 0.0f, 0.4000f});
                    }
                    // 下瓣：常量增益椭圆（fit_naso6.json，8 帧统一拟合）
                    struct Tail { float ex, ey, dx, rot; int sgn; };
                    const Tail tails[2] = {
                        {e0x, e0y, -0.0631f, 0.2294f, -1},
                        {e1x, e1y, -0.0332f, -0.2007f, +1},
                    };
                    const float eyeDist = e1x - e0x;
                    const float yaw = (eyeDist > 0.01f)
                                          ? (nsx - (e0x + e1x) * 0.5f) / eyeDist
                                          : 0.0f;
                    for (int i = 0; i < 2; i++) {
                        const Tail& t = tails[i];
                        float w = 1.0f - 1.9508f * yaw * (float)t.sgn;
                        if (w < 0.25f) w = 0.25f;
                        nasoTailEls.push_back({t.ex + t.dx, t.ey + 0.2843f,
                                               0.1000f * w, 0.1200f,
                                               t.rot * (float)t.sgn,
                                               g * 4.0000f, 0.15f, 0.5500f});
                    }
                    nasoSlope = slope;
                }
            }

            if (!els.empty()) {
                // 每个椭圆坐标都是**相对这张脸的归一化值**，所以这里传脸框，
                // 一次调用把这五项的贡献一起加掉（增益相加，互不干扰）。
                beautycore::applyEllipses(dst, w, h, mk, fx, fy, fw, fh,
                                          &els[0], (int)els.size(), g_cfg.threads);
                els.clear();
            }
            if (!nasoEls.empty()) {
                // 法令纹：Δ = min(maxLift, slope·max(0, LR − Y)) × 区域权重
                beautycore::applyFoldRemoval(dst, w, h, mk, fx, fy, fw, fh,
                                             &nasoEls[0], (int)nasoEls.size(),
                                             nasoSlope, g_cfg.regNasoMaxLift,
                                             g_cfg.regNasoLrRadius,
                                             g_cfg.regNasoGateLo,
                                             g_cfg.regNasoGateHi,
                                             g_cfg.threads);
                nasoEls.clear();
            }
            if (!nasoTailEls.empty()) {
                // 法令纹**下瓣**：常量增益椭圆（参照的褶皱朝嘴角延伸的那一段，
                // 幅度 3~12 灰阶，与亮度无关）。必须在 applyFoldRemoval 之后，
                // 否则上瓣的邻域最大 LR 会被下瓣抬起来。
                beautycore::applyEllipses(dst, w, h, mk, fx, fy, fw, fh,
                                          &nasoTailEls[0],
                                          (int)nasoTailEls.size(),
                                          g_cfg.threads);
                nasoTailEls.clear();
            }
        }

        if (spot > 0.0f && !bounds_.empty()) {
            beautycore::applySpotFix(dst, w, h, mk, bounds_,
                                     g_cfg.regSpotK * spot, g_cfg.regSpotRadius,
                                     g_cfg.regSpotThrLo, g_cfg.regSpotThrHi,
                                     g_cfg.threads, spotScratch_);
        }
    }

    // 高低频参数在两个分支里各拼一次，抽出来避免两处漂移（以前就是改一处忘一处）。
    beautycore::FreqParams makeFreqParams() const {
        beautycore::FreqParams fp;
        fp.radius = g_cfg.radius;          // 沿用标定好的 r=2
        fp.iters = g_cfg.freqIters;        // 迭代次数决定低频尺度
        fp.sigmaSpace = g_cfg.sigmaSpace;
        fp.sigmaColor = g_cfg.sigmaColor;
        fp.magLo = g_cfg.freqMagLo;
        fp.magHi = g_cfg.freqMagHi;
        fp.grain = g_cfg.freqGrain;
        fp.strength = 100;                 // 面板档位由 blendWithMask 按 t 缩放
        fp.lowMode = g_cfg.freqLowMode;
        fp.guideRadius = g_cfg.guideRadius;
        fp.guideEps = g_cfg.guideEps;
        fp.lowPath = g_cfg.lowPath;
        fp.refRadius = g_cfg.refRadius;
        fp.boxRadius = g_cfg.boxRadius;
        fp.boxIters = g_cfg.boxIters;
        return fp;
    }
};

// 绑定宏只服务于 CoreEngine 的成员函数体，出了类就不该再存在（否则后面任何一个
// 叫 mask_ / faceErr_ 的局部变量都会被悄悄替换掉）。
#undef BEAUTY_BIND_DET_ALL
#undef BEAUTY_BIND_DET_DIR

// 选择实现。只解析一次环境变量。
//
// 3.1.7 起**默认是 core**（自研引擎）。离线基准 DLL 里可用 BEAUTY_ENGINE_IMPL=legacy 切回旧链路。
// 为什么现在敢切：
//   · 面板 11/11 项已覆盖（3.1.2 起）；
//   · 真机 3.1.5 日志确认 engine=core/region=on/faces=1（3.1.4 修好的人脸模型加载）；
//   · 最后一个已知画质缺口（锐化放大的噪点闪烁）在 3.1.6 用时序 EMA 补掉。
//
// 未知值（比如写错成 "cor"）当作「没设置」处理，走默认。为什么不静默退回旧链路：
// 那样写错一个字母会悄悄跑回旧引擎，用户以为自己在测新引擎。
// 写错是可见的 —— init OK 那行会打出 engine=core/0.7.2，一眼能看出来。
IBeautyEngine* createEngine() {
    const char* v = beauty_env("BEAUTY_ENGINE_IMPL");
    if (v && v[0]) {
#ifdef BEAUTY_WITH_LEGACY_ENGINE
        if (strcmp(v, "legacy") == 0) return new LegacyAdapter();
#endif
        if (strcmp(v, "passthrough") == 0) return new PassthroughEngine();
        if (strcmp(v, "core") == 0) return new CoreEngine();
    }
    return new CoreEngine();
}

}  // namespace

// 皮肤判据快照（C20，只用于日志）。定义放在匿名命名空间外面 —— 否则外部
// （obs-beauty.cpp）链接不到，与上面 beautyCoreSetSmoothParams 同一规则。
// 内部的 g_skin* 仍在匿名空间里，同一 TU 内可见。
const char* beautyCoreSkinInfo() {
    static char buf[192];
    snprintf(buf, sizeof(buf),
             "skin=%s cb=%+.4f cr=%+.4f r=%.4f/%.4f ema=%.2f%s",
             g_skinAdapt ? "adapt" : "fixed",
             g_skinCb, g_skinCr, g_skinRu, g_skinRv, g_skinAdaptEma,
             g_skinAdaptValid ? "" : " (center=default, not yet estimated)");
    return buf;
}

// 估计首次收效后返回 true（并清标志），渲染线程按它决定要不要补打一行
// skin= —— 与 beautyCoreSkinInfo() 连用，两步之间没有别的线程会再改 g_skin*。
// 注意：g_skinAdaptValid 一旦置位整个会话不会再翻回 false（估计连续失败也
// 只沿用上一帧中心），所以这个标志整个生命周期至多被置位一次，取走即完。
bool beautyCoreSkinAnnounce() {
    return g_skinAnnounce.exchange(false, std::memory_order_relaxed);
}

// 自研核参数（离线调参入口）。定义必须放在匿名命名空间**外面**，否则外部
// （core_probe.cpp）链接不到；g_cfg 本身仍在匿名空间内，只给 CoreEngine 用。
void beautyCoreSetSmoothParams(int radius, float sigmaSpace,
                               float sigmaColor, int down) {
    g_cfg.radius = radius;
    g_cfg.sigmaSpace = sigmaSpace;
    g_cfg.sigmaColor = sigmaColor;
    g_cfg.down = (down < 1) ? 1 : down;
}

// 性能相关开关（离线调参 / 对照实验入口）。定义同样要放在匿名命名空间外面。
//   threads <= 0 自动；1 强制单线程
//   useRoi  0 = 关掉 ROI 裁剪（只在测「全帧成本」时用，生产必须开）
void beautyCoreSetPerf(int threads, int useRoi) {
    g_cfg.threads = (threads < 1) ? 0 : threads;
    g_cfg.roi = (useRoi != 0);
}

// Sobel 边缘门控灵敏度（离线调参入口）。0 = 关闭。
void beautyCoreSetEdgeK(int k) {
    g_cfg.edgeK = (k < 0) ? 0 : k;
}

void beautyCoreSetClarity(float maxGain, int radius, float kneeLo, float kneeHi) {
    if (maxGain >= 0.0f) g_cfg.clarityMax = maxGain;
    if (radius > 0) g_cfg.clarityRadius = radius;
    if (kneeHi > kneeLo && kneeLo >= 0.0f) {
        g_cfg.clarityKneeLo = kneeLo;
        g_cfg.clarityKneeHi = kneeHi;
    }
}

void beautyCoreSetLowPath(int path, int refRadius) {
    g_cfg.lowPath = (path < 0) ? 0 : (path > 3 ? 3 : path);
    if (refRadius >= 0) g_cfg.refRadius = refRadius;
}

void beautyCoreSetGuide(int mode, int radius, float eps) {
    g_cfg.freqLowMode = (mode != 0) ? 1 : 0;
    if (radius > 0) g_cfg.guideRadius = radius;
    if (eps > 0.0f) g_cfg.guideEps = eps;
}

void beautyCoreSetFreqGrain(float g) {
    g_cfg.freqGrain = (g < 0.0f) ? 0.0f : ((g > 1.0f) ? 1.0f : g);
}

void beautyCoreSetFreq(int mode, float sigma, float magLo, float magHi) {
    g_cfg.freqMode = (mode != 0) ? 1 : 0;
    // sigma 参数在这里复用为「迭代次数」（1..6），保持导出签名不变
    if (sigma >= 1.0f) {
        g_cfg.freqIters = (int)(sigma + 0.5f);
        if (g_cfg.freqIters < 1) g_cfg.freqIters = 1;
        if (g_cfg.freqIters > 8) g_cfg.freqIters = 8;
    }
    if (magHi > magLo) {
        g_cfg.freqMagLo = magLo;
        g_cfg.freqMagHi = magHi;
    }
}

void beautyCoreSetLimitThr(int thr) {
    g_cfg.limitThr = (thr < 0) ? 0 : thr;
}

void beautyCoreSetProtectK(int k) {
    if (k < 0) k = 0;
    if (k > 100) k = 100;
    g_cfg.protectK = k;
}

// 掩码导出（离线对拍用）。同样必须放在匿名命名空间外面。
bool beautyCoreComputeMaskSlot(int slot, const unsigned char* src, int w, int h,
                               unsigned char* outMask) {
    if (!src || !outMask || w <= 0 || h <= 0) return false;
    CoreEngine* ce = dynamic_cast<CoreEngine*>(&beautyEngine());
    if (!ce) return false;
    return ce->computeMaskForDump(slot, src, w, h, outMask);
}

bool beautyCoreComputeMask(const unsigned char* src, int w, int h,
                           unsigned char* outMask) {
    return beautyCoreComputeMaskSlot(0, src, w, h, outMask);
}

int beautyCoreDumpFaceSlot(int slot, char* buf, int cap) {
    CoreEngine* ce = dynamic_cast<CoreEngine*>(&beautyEngine());
    if (!ce) return -1;
    return ce->dumpFaceInfo(slot, buf, cap);
}

IBeautyEngine& beautyEngine() {
    // 与 LegacyEngine::inst() 同一套路：魔法静态保证只初始化一次且线程安全；
    // 对象刻意不析构，避免宿主 FreeLibrary 时静态析构与渲染线程赛跑。
    static IBeautyEngine* s = createEngine();
    return *s;
}

const char* beautyEngineId() {
    return beautyEngine().id();
}

int beautyCoreMaskCadence() {
    return g_cfg.maskEveryAsync;
}

uint64_t beautyCoreMaskSubmits() {
    return g_maskSubmits;
}

uint64_t beautyCoreAlignUsed() {
    return g_alignUsed;
}

// 3.1.10 探针：一次调用带回 (对齐帧数, 处理总帧数)，供日志算比率。
int beautyCoreAlignStat(uint64_t* used, uint64_t* total) {
    if (used) *used = g_alignUsed;
    if (total) *total = g_alignTotal;
    return 0;
}

// 3.1.40 探针：启动以来「因确认无脸而整段跳过」的帧数（累计值）。
// 滤镜侧取窗口差值输出 noface=N，用来证明跳过真的发生了。
uint64_t beautyCoreNoFaceFrames() {
    return g_noFaceFrames;
}

// 3.1.40：给滤镜侧 init 日志用（1 = 开 / 0 = 旧的全帧兜底）。
int beautyCoreNoFaceSkip() {
    return g_cfg.noFaceSkip ? 1 : 0;
}

// 1.0.5.0：给滤镜侧 init 日志用（1 = 头歪补偿开 / 0 = 被 BEAUTY_AUTO_ROLL=0 关掉）。
int beautyCoreAutoRoll() {
    return g_cfg.autoRoll ? 1 : 0;
}

// 1.0.7.0：给滤镜侧 init 日志用（1 = 脖子通道开 / 0 = 被 BEAUTY_NECK=0 关掉）。
int beautyCoreNeckOn() {
    return g_neckOn ? 1 : 0;
}

// 1.0.10.0：A 通道归属（1 = 引擎做 / 0 = 插件在上传段做）。
int beautyCoreAlphaInEngine() {
    return alphaInEngine() ? 1 : 0;
}
