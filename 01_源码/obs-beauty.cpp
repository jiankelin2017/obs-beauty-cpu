//
// 结构：
//   obs-beauty.cpp     OBS 胶水层：属性页、帧捕获、CPU 回传、绘制、性能埋点
//   beauty_core.cpp    引擎抽象 + CoreEngine（自研实现，唯一的生产路径）
//   beauty_smooth.cpp  磨皮核（三层表面模糊 / 双尺度带通 + 振幅门控）
//   beauty_freq.cpp    色调（清晰 / 美白 / 红润）与细节回填（锐化）
//   beauty_region.cpp  五官局部五项
//
// 数据流（每帧）：
//   GPU 纹理 → 下载到 CPU（RGBA）→ CoreEngine::process（检测在独立 worker 上
//   异步跑）→ 上传回纹理 → 绘制。全 0 参数时逐字节透传，不进引擎。
//
// 唯一不能改的是 source id：OBS 场景 JSON 里存的就是这个字符串，改了老场景里
// 已挂好的滤镜会变成「缺失滤镜」。
//
// 3.1.21：删掉「镜头画面旋转」「恢复默认 / 保存 preset.json / 读取 preset.json」
// 三个属性；总开关置顶；旧 id 别名不再注册（老场景已一次性迁移）。
#include <windows.h>
#include <gl/gl.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <obs.h>
#include <obs-module.h>
#include <graphics/graphics.h>
#include <graphics/vec4.h>
#include <util/platform.h>
#include <util/bmem.h>

#include "beauty_env.h"   // beauty_env()：BEAUTY_* 覆盖的唯一入口（1.0.13.10 C-2/C-3）
#include "beauty_params.h"   // BeautySettings / P_*（纯数据，不引入任何引擎实现）
#include "beauty_log.h"
// 引擎抽象层：本文件只认 IBeautyEngine，不直接依赖任何具体实现。
// 3.1.7 起只有自研 CoreEngine 一条生产路径（旧链路只在离线基准 DLL 里保留）。
#include "beauty_core.h"
// 1.0.9.0：只为在 init 行打印盒式的两个可调项（boxBlockWidth / boxMinPixels）。
#include "beauty_smooth.h"
// 1.0.11.0：只为在 init 行打印色调走的是整数表还是浮点插值（toneIntLutOn）。
#include "beauty_freq.h"

#define PLUGIN_NAME "obs-beauty"
#define PLUGIN_VERSION BEAUTY_BUILD_STR

// source id。**永远不要改** —— 场景文件里存的就是这个字符串。
// 3.1.21 起不再注册「旧 id 别名」，留两个 id 只会让滤镜列表出现两个条目；
// 老场景已由装机脚本一次性把 id 改写成本值。
#define BEAUTY_FILTER_ID "obs_beauty_filter"

// source id。**永远不要改** —— 场景文件里存的是这个字符串。
// 3.1.21 起不再注册「旧 id 别名」：老场景已在装机脚本里一次性迁移到本 id
// （见 04_文档/CHANGELOG 3.1.21）。留两个 id 只会让滤镜列表出现两个条目。

// ---------------------------------------------------------------------------
// 引擎 → OBS 日志钩子。模块加载时装一次；不装的话引擎消息落到 stderr。
//
// 参数是否配对。3.1.4 就因此崩过：给 init OK 加了 engine=%s/%s 却忘了删掉后面
// 的 sdk=%s，7 个占位符配 6 个参数，region=%s 拿到的是整数 itemId，ucrtbase
// 解引用 0x5350 直接访问违例，OBS 在模块加载阶段连崩两次。
// **改下面任何一条多参数日志，必须手工数一遍 % 的个数与参数个数。**
// ---------------------------------------------------------------------------
static void beauty_obs_log(int level, const char* msg)
{
	blog(level == BEAUTY_LOG_ERROR	  ? LOG_ERROR
	     : level == BEAUTY_LOG_WARNING ? LOG_WARNING
	     : level == BEAUTY_LOG_DEBUG	  ? LOG_DEBUG
					  : LOG_INFO,
	     "[" PLUGIN_NAME "] %s", msg);
}

// region 状态的措辞。两种引擎的 off 含义完全不同，日志里必须能分开看：
//   旧链路 —— 没装 皮肤分割库 / 明文 bundle，退回 v1.4 的颜色启发式（画面仍然正常）；
//           （背景一起磨、CPU 顶满），且清晰/美白/红润/五官五项/脸内锐化全部不执行。
static const char *region_state(const IBeautyEngine &e)
{
	if (e.regionActive()) {
		// 自研核额外报出掩码提交节奏：0 = 每帧（3.1.8 起的默认），4 = 老节奏。
		// 真机上要对比「拖影 / CPU」就用 BEAUTY_MASK_EVERY 改，这里能看出改没改上。
		if (e.id() && strcmp(e.id(), "core") == 0) {
			static char buf[48];
			snprintf(buf, sizeof(buf), "on(every=%d)", beautyCoreMaskCadence());
			return buf;
		}
		return "on";
	}
	if (e.id() && strcmp(e.id(), "core") == 0)
		return "off(无掩码/全帧)";
	return "off(颜色启发式)";
}

// ------------------------------------------------------------------
// Parameter table
//
// 每一行是属性页上的一个滑块。key 同时是 OBS settings key（预设/场景文件里
// 存的就是它，**不要改**）。面板刻度统一 0..100，max_val 是面板 100 对应的
// 内部量程（value = panel / 100 * max_val）。
//
// 面板一共 11 项：磨皮 / 清晰 / 美白 / 红润 / 锐化 / 全局锐化 / 五官立体 /
// 亮眼 / 去黑眼圈 / 去法令纹 / 祛斑痘。
// ------------------------------------------------------------------
struct beauty_param_def {
	const char *key;    // 同时是 OBS settings key
	const char *label;  // panel label
	double dflt;        // default, panel units (0..100)
	double max_val;     // 面板 100 对应的内部量程
};

static const struct beauty_param_def g_params[] = {
	{"blur_level", "磨皮", 20.0, 6.0},
	{"clarity", "清晰", 0.0, 1.0},
	{"color_level", "美白", 0.0, 2.0},
	{"red_level", "红润", 0.0, 1.0},
	{"sharpen", "锐化", 0.0, 1.0},
	{"global_sharpen", "全局锐化", 0.0, 1.0},
	{"face_threed", "五官立体", 0.0, 1.0},
	{"eye_bright", "亮眼", 0.0, 1.0},
	{"remove_pouch_strength", "去黑眼圈", 0.0, 1.0},
	{"remove_nasolabial_folds_strength", "去法令纹", 0.0, 1.0},
	// 3.0.16 新增：祛斑痘。确实生效，但会让帧间闪动上升约 56%，
	// 且官方说明「消耗较多的电脑资源」，所以默认 0（关）。
	{"delspot_level", "祛斑痘", 0.0, 1.0},
	// 3.1.27 新增：美形三项。默认全 0 —— 几何变形会改变人脸轮廓，属于
	// 「用户主动要才做」的一类；默认关掉保证升级后画面逐字节不变。
	{"thin_face", "瘦脸", 0.0, 1.0},
	{"big_eye", "大眼", 0.0, 1.0},
	{"chin", "下巴", 0.0, 1.0},
};

#define BEAUTY_NPARAM ((int)(sizeof(g_params) / sizeof(g_params[0])))

// 3.0.13：把「一一对应」从注释变成编译期约束。以前只写在注释里，改了枚举
// 忘了改表（或反之）会静默错位一个滑块 —— 这正是历史上 P_WHITEN=2 那个坑。
static_assert(BEAUTY_NPARAM == P_COUNT,
              "g_params[] 与 beauty_engine.h 的 P_* 枚举必须一一对应");

// 与引擎的参数枚举一一对应（compile-time 断言在文件末尾）。
#define BEAUTY_IDX_BLUR P_BLUR

// Bumped whenever the meaning of a stored slider changes.
//   1 = 1.x：滑块从内部原值改成 0..100 面板刻度
//   2 = 2.0：删除 17 项美型 / 脸型预设 / 滤镜（旧预设里这些值被忽略）
#define BEAUTY_PARAM_VERSION 2

// ------------------------------------------------------------------
// OBS filter
// ------------------------------------------------------------------
struct beauty_filter {
	obs_source_t *context;
	gs_texrender_t *tr;    // capture upstream frame
	gs_stagesurf_t *stage; // CPU readback
	gs_texture_t *out_tex; // processed result
	uint32_t w, h;
	uint8_t *buf_in;
	uint8_t *buf_out;
	int frame_id;
	bool verified;
	// 性能埋点（BEAUTY_PROFILE=1 时才统计/输出）
	// 为什么要埋这个：插件每帧要把整帧从 GPU 下载到 CPU 再传回去，
	// 1080p RGBA 是 8 MB × 2。这笔开销从未实测过，而它是「要不要整体
	bool prof_on;
	int prof_frames;
	double prof_dl;    // 累计下载耗时 ms
	double prof_proc;  // 累计引擎耗时 ms
	double prof_up;    // 累计上传+绘制耗时 ms
	double prof_t0;    // 本次计时的起点
	// 3.1.10：掩码↔帧对齐计数的窗口基线（见 prof_frames 归零处的用法）。
	// 探针给的是从启动起的全量值，这里存「上个日志窗口结束时」的值，
	// 打印时取差值得到**本窗口内**的对齐比率 —— 90s @30fps 一个窗口，
	// 比全量比率更容易看出 worker 是不是间歇性追不上。
	uint64_t prof_align0_used;
	uint64_t prof_align0_total;
	// 3.1.40：无脸透传帧数的窗口基线（同上取差值）。
	// noface=N 表示「本窗口内有 N 帧因为确认没人而整段跳过」。没有它的话，
	// 引擎耗时归零既可能是跳过生效，也可能是磨皮压根没跑 —— 无法归因。
	uint64_t prof_noface0;
	// 1.0.9.0：引擎分段耗时累计（见 beauty_core.h 的 lastStageMs）。
	// 真机上「引擎 14 ms」到底花在检测、磨皮还是色调，只有分段能回答 ——
	// 整段一个数字时，任何优化都只能靠猜。
	double prof_st[6];
	// 1.0.13.12 D1：下面这组字段由参数线程（beauty_filter_update）写、
	// 渲染线程（beauty_filter_render）读。bzalloc/bfree 不调 C++ 构造析构，
	// 所以用 POD 的 SRWLOCK（全零初始化等价于 SRWLOCK_INIT），不能放 std::mutex。
	SRWLOCK param_lock;
	bool enabled;
	bool mirror;
	int blur_type;    // 1=双边(最强) 0=高斯 2=弱磨皮
	int skin_detect;  // 1 = 只磨皮肤（精准美肤）
	int smooth_mode;  // 3.0.17 磨皮模式 0人像 1清晰 2精细 3朦胧（纯 CPU 侧）
	int landmark_q;   // fuFaceProcessorSetFaceLandmarkQuality (面板: 识别模式)
	int max_faces;    // fuSetMaxFaces (面板: 人物个数)
	double v[BEAUTY_NPARAM]; // panel units, 0..100
	int slot;              // 引擎槽位（每个滤镜实例独占一份上下文）
	bool dirty;            // 进程级检测选项待下发（渲染线程 flush）
	bool err_reported;     // 引擎报错只提示一次，避免每帧刷屏
};

// 1.0.13.12 D1：参数线程与渲染线程共享字段的 POD 快照。
// render 每帧在 param_lock 下取一次快照，之后整帧只读这份局部副本。
struct beauty_param_snapshot {
	bool enabled;
	bool mirror;
	int blur_type;
	int skin_detect;
	int smooth_mode;
	int landmark_q;
	int max_faces;
	int slot;
	bool dirty;
	double v[BEAUTY_NPARAM];
};

// 面板值 → 引擎设置。每帧构一次，代价是 9 个 double 拷贝。
static void beauty_filter_settings(const struct beauty_param_snapshot *p, BeautySettings &s)
{
	for (int i = 0; i < BEAUTY_NPARAM; i++)
		s.panel[i] = p->v[i];
	s.blur_type = p->blur_type;
	s.skin_detect = p->skin_detect ? 1 : 0;
	s.smooth_mode = p->smooth_mode;
}

static void beauty_filter_read(struct beauty_filter *f, obs_data_t *s)
{
	f->enabled = obs_data_get_bool(s, "enabled");
	f->mirror = obs_data_get_bool(s, "mirror");
	f->blur_type = (int)obs_data_get_int(s, "blur_type");
	f->skin_detect = obs_data_get_bool(s, "skin_detect") ? 1 : 0;
	f->smooth_mode = (int)obs_data_get_int(s, "smooth_mode");
	f->landmark_q = (int)obs_data_get_int(s, "landmark_q");
	f->max_faces = (int)obs_data_get_int(s, "max_faces");
	for (int i = 0; i < BEAUTY_NPARAM; i++)
		f->v[i] = obs_data_get_double(s, g_params[i].key);
}

// Convert settings written by earlier builds.
//   v0 -> v1: pre-0.2 builds stored raw internal units on a handful of sliders.
//   v1 -> v2: 2.0 dropped the 17 美型 sliders, the 脸型预设 and the filter;
//             those keys are simply no longer read.
static void beauty_migrate(obs_data_t *s)
{
	const int ver = (int)obs_data_get_int(s, "param_version");
	if (ver >= BEAUTY_PARAM_VERSION)
		return;
	// v0 -> v1（2.0.0）：1.x 的滑块本来就是 0..100 面板刻度 —— 见 1.x 下发处
	// g_fuItemSetParamd(item, key, v / 100.0 * max_val)，存下来的 v 已经是
	// 面板值。所以这里**不做任何数值换算**。
	//
	// 早期版本误写成 v / max_val * 100：用户的磨皮 15 会算成 250，再被滑块
	// 上限截到 100，等于把调好的 15 直接拉到满格。max_val > 1 的两项
	// （磨皮 6.0、美白 2.0）受害最重，其余七项 max_val 都是 1.0，×100 之后
	// 一律顶到 100。
	//
	// v1 -> v2：只是删掉了 18 个已废弃的键（17 项美型 + 全局滤镜），
	// 同样不需要换算。
	obs_data_set_int(s, "param_version", BEAUTY_PARAM_VERSION);
	blog(LOG_INFO, "[" PLUGIN_NAME "] settings migrated to v%d (美型/滤镜 已移除)",
	     BEAUTY_PARAM_VERSION);
}

// 高精度单调时钟。GetTickCount64 只有 15.6ms 精度，量几毫秒的环节不够用。
static double beauty_now_ms(void)
{
	static double freq = 0.0;
	LARGE_INTEGER c;
	if (freq == 0.0) {
		LARGE_INTEGER f;
		QueryPerformanceFrequency(&f);
		freq = (f.QuadPart > 0) ? (double)f.QuadPart : 1.0;
	}
	QueryPerformanceCounter(&c);
	return (double)c.QuadPart * 1000.0 / freq;
}

// ---- 1.0.11.0（A5）：下载零拷贝，默认关闭 --------------------------------
//
// 打开后，`gs_stagesurface_map` 出来的指针直接当引擎的输入，省掉一次 8.3 MB
// 的整帧 memcpy。**默认关**，因为有一个真实风险需要实测：staging surface 映射
// 出来的内存往往是写合并/非缓存的，引擎会在不同 pass 里把同一片输入读好几遍
// （掩码、磨皮、色调、细节都读 src）。从缓存里读 8 MB 和从非缓存内存里读 8 MB
// 差一个数量级 —— 省下的 0.6 ms memcpy 可能被加倍的读取开销吃掉。
//
// 所以先让它可开关、可观测（init 日志里有 zc=），在同一次装机里用
// BEAUTY_ZERO_COPY=1 实测；赢了再改默认值。
static bool beauty_zero_copy(void)
{
	static const bool v = []() {
		const char *e = beauty_env("BEAUTY_ZERO_COPY");
		return e && e[0] == '1';
	}();
	return v;
}

// ---- 3.1.11：把滤镜版本号暴露给其它模块（面板左下角显示用）------------------
//
// 为什么：面板角标打的是**面板自己的版本**（3.0.22），用户看到它就会问
// 「装的滤镜是不是旧版」—— 版本号必须放在它能被看到的地方。proc handler 是
// OBS 官方的跨模块查询通道：面板拿到滤镜 source 后调 beauty_version 就能拿到，
// 老面板没有这个 proc 也只是显示不到，不会报错。
// 只报 meta（不加载引擎、不读设置），任何滤镜实例无论状态都能答。
// 参数全走 calldata，obs_source 不做隐式注入（见 callback/proc.c 的 dispatch）。
static void beauty_version_proc(void *, calldata_t *params)
{
	calldata_set_string(params, "version", PLUGIN_VERSION);
}

static void *beauty_filter_create(obs_data_t *settings, obs_source_t *source)
{
	struct beauty_filter *f = (struct beauty_filter *)bzalloc(sizeof(struct beauty_filter));
	/* 2026-11-10 代码审查 #2：bzalloc 可能返回 NULL，D1 把首个解引用点
	 * 提前到 InitializeSRWLock，必须先判空再写成员。 */
	if (!f)
		return NULL;
	InitializeSRWLock(&f->param_lock);
	f->context = source;
	f->frame_id = 0;
	{
		proc_handler_t *ph = obs_source_get_proc_handler(source);
		if (ph)
			proc_handler_add(ph, "void beauty_version(out string version)",
					 beauty_version_proc, NULL);
	}
	f->slot = -1;
	f->dirty = true;
	f->err_reported = false;
	// 只在显式开启时统计，避免给生产会话平白加两次计时调用
	{
		const char *p = beauty_env("BEAUTY_PROFILE");
		f->prof_on = (p && p[0] == '1');
	}
	beauty_migrate(settings);
	beauty_filter_read(f, settings);

	// 每个实例独占一份引擎上下文。第一次调用会顺带完成预热（约 2 秒），
	// 因此首个滤镜创建时会有一个可感的停顿 —— 与 1.x 在模块加载时预热相比，
	// 好处是「没拖滤镜的 OBS 会话完全不付这笔开销」。
	std::string err;
	f->slot = beautyEngine().acquireSlot(err);
	if (f->slot < 0)
		blog(LOG_ERROR, "[" PLUGIN_NAME "] 引擎槽位获取失败：%s（滤镜将直通）",
		     err.c_str());
	return f;
}

static void beauty_filter_destroy(void *data)
{
	struct beauty_filter *f = (struct beauty_filter *)data;
	if (!f)
		return;
	if (f->slot >= 0) {
		beautyEngine().releaseSlot(f->slot);
		f->slot = -1;
	}
	if (f->out_tex)
		gs_texture_destroy(f->out_tex);
	if (f->stage)
		gs_stagesurface_destroy(f->stage);
	if (f->tr)
		gs_texrender_destroy(f->tr);
	free(f->buf_in);
	free(f->buf_out);
	bfree(f);
}

static void beauty_filter_get_defaults(obs_data_t *settings)
{
	obs_data_set_default_bool(settings, "enabled", true);
	obs_data_set_default_bool(settings, "mirror", false);
	obs_data_set_default_int(settings, "blur_type", 1);
	obs_data_set_default_int(settings, "smooth_mode", 0);
	// 2.0 起默认开：BGRA 修正 + 语义掩码之后，"只磨皮肤"才是预期行为，
	// 1.x 默认关是因为当时人脸检测基本失效，开着只会全局磨糊。
	obs_data_set_default_bool(settings, "skin_detect", true);
	obs_data_set_default_int(settings, "landmark_q", 1);
	obs_data_set_default_int(settings, "max_faces", 4);
	obs_data_set_default_int(settings, "param_version", BEAUTY_PARAM_VERSION);
	for (int i = 0; i < BEAUTY_NPARAM; i++)
		obs_data_set_default_double(settings, g_params[i].key, g_params[i].dflt);
}

static const char *beauty_filter_name(void *unused)
{
	UNUSED_PARAMETER(unused);
	// 3.0.15：对外显示名统一为「OBS美颜」。source id 仍是 obs_beauty_filter，
	// 旧场景里已挂好的滤镜不受影响（OBS 按 id 查找，不按显示名）。
	return "OBS美颜";
}

/* 3.1.28：整段「参数悬停备注」已删除（beauty_param_note 函数一并移除）。
 *
 * 用户要求「悬停备注也不需要」—— 面板与 OBS 原生属性页都不再显示任何
 * long_description。标签名本身已经说清功能，长文案只会变成噪音。
 * 历史文案（3.1.21 重写的那一版，含各项实测量级）见 git 历史 /
 * 04_文档\CHANGELOG_提交记录.md 的 3.1.27 之前条目。 */

/* 3.1.22：按 key 建滑块。
 * 属性改成按功能分组之后，滑块不再是一个 for 循环建出来的，只能按名字找。
 * 找不到就报错返回 NULL —— 绝不静默建一个名字不对的滑块，
 * 那会写到用户设置里的另一个键上，把别的功能推歪。 */
static obs_property_t *add_beauty_slider(obs_properties_t *ppts, const char *key)
{
	for (int i = 0; i < BEAUTY_NPARAM; i++) {
		if (strcmp(g_params[i].key, key) != 0)
			continue;
		/* 3.1.28：不再挂 long_description（用户要求「悬停备注也不需要」）。
		 * 滑块只留标签本身，悬停无提示、原生属性页下方也不显示说明。 */
		return obs_properties_add_float_slider(
			ppts, g_params[i].key, g_params[i].label, 0.0, 100.0, 1.0);
	}
	blog(LOG_ERROR, "[%s] add_beauty_slider: unknown key '%s'",
	     PLUGIN_NAME, key ? key : "(null)");
	return NULL;
}

static obs_properties_t *beauty_filter_properties(void *data)
{
	UNUSED_PARAMETER(data);
	obs_properties_t *ppts = obs_properties_create();
	// 总开关放第一位：它是「关掉整个滤镜」的唯一入口，比任何滑块都用得多。
	// 3.1.22：标签去掉「（总开关）」。这一行本来就在属性表最顶上、又是第一个
	// 加进去的，位置已经说明了它是总开关，不必再在文字里喊一遍。
	obs_properties_add_bool(ppts, "enabled", "启用美颜");

	obs_property_t *dm = obs_properties_add_list(ppts, "landmark_q", "识别模式", OBS_COMBO_TYPE_LIST,
						     OBS_COMBO_FORMAT_INT);
	obs_property_list_add_int(dm, "标准", 0);
	obs_property_list_add_int(dm, "高精度", 1);

	obs_property_t *mf = obs_properties_add_list(ppts, "max_faces", "人物个数", OBS_COMBO_TYPE_LIST,
						     OBS_COMBO_FORMAT_INT);
	for (int i = 1; i <= 8; i++) {
		char lbl[8];
		snprintf(lbl, sizeof(lbl), "%d", i);
		obs_property_list_add_int(mf, lbl, i);
	}

	obs_properties_add_bool(ppts, "mirror", "镜像");

	// ---- 美颜：按功能类型分成 4 组 ----
	// 3.1.22：原来 11 个滑块 + 3 个选择器全塞在一个「美颜」组里，一屏拉到底
	// 还是很混。现在按类型拆成「磨皮 / 肤色 / 锐化 / 五官」四组，
	// OBS 原生滤镜属性页和自研面板同时受益（同一份属性表）。
	//
	// 顺序上有个巧合值得记一笔：分组后各组内、以及组与组之间合起来，
	// 恰好仍与 P_* 枚举同序（磨皮 → 清晰/美白/红润 → 锐化/全局锐化 → 五官五项）。
	// 引擎取参是按 key（obs_data 存 key→value），所以顺序其实不影响数值，
	// 但保持同序能让日志、截图、下标直觉都对得上。

	// ---- 3.1.29：磨皮算法 / 磨皮模式 提到**顶层** ----
	// 用户要求把这两个下拉放到面板**底部栏**（见 obs-beauty-ui.cpp 的 mode_row_）。
	// 它们不属于任何参数页：是「全局档位」，切到哪一页都该一直看得见。
	// 放在顶层还有一个好处 —— OBS 原生「滤镜属性」窗口里它们也落在参数组之前，
	// 与面板的视觉顺序一致。
	obs_property_t *bt = obs_properties_add_list(ppts, "blur_type", "磨皮算法",
						     OBS_COMBO_TYPE_LIST, OBS_COMBO_FORMAT_INT);
	obs_property_list_add_int(bt, "双边滤波", 1);
	obs_property_list_add_int(bt, "高斯滤波", 0);
	obs_property_list_add_int(bt, "弱磨皮", 2);

	obs_property_t *sm = obs_properties_add_list(
		ppts, "smooth_mode", "磨皮模式",
		OBS_COMBO_TYPE_LIST, OBS_COMBO_FORMAT_INT);
	obs_property_list_add_int(sm, "人像磨皮", 0);
	obs_property_list_add_int(sm, "清晰磨皮", 1);
	obs_property_list_add_int(sm, "精细磨皮", 2);
	obs_property_list_add_int(sm, "朦胧磨皮", 3);

	// ---- 组 1：美颜（3.1.29 合并磨皮与肤色；3.1.30 改名为「美颜」）----
	// 为什么合并：这两类是**天天要调的主参数**，分成两页反而每次都要切。
	// 合并后第一页 5 行：精准美肤 / 磨皮 / 清晰 / 美白 / 红润 —— 一屏看全，
	// 且顺序仍是 P_* 枚举顺序（磨皮 → 清晰/美白/红润）。
	// 「磨皮算法」「磨皮模式」已经移到顶层（底部栏），不在这里。
	obs_properties_t *gb_blur = obs_properties_create();
	obs_properties_add_bool(gb_blur, "skin_detect", "精准美肤");
	add_beauty_slider(gb_blur, "blur_level");
	add_beauty_slider(gb_blur, "clarity");
	add_beauty_slider(gb_blur, "color_level");
	add_beauty_slider(gb_blur, "red_level");
	obs_properties_add_group(ppts, "grp_blur", "美颜", OBS_GROUP_NORMAL, gb_blur);

	// ---- 组 2：锐化 ----
	obs_properties_t *gb_sharp = obs_properties_create();
	add_beauty_slider(gb_sharp, "sharpen");
	add_beauty_slider(gb_sharp, "global_sharpen");
	obs_properties_add_group(ppts, "grp_sharp", "锐化", OBS_GROUP_NORMAL, gb_sharp);

	// ---- 组 3：五官 ----
	obs_properties_t *gb_face = obs_properties_create();
	add_beauty_slider(gb_face, "face_threed");
	add_beauty_slider(gb_face, "eye_bright");
	add_beauty_slider(gb_face, "remove_pouch_strength");
	add_beauty_slider(gb_face, "remove_nasolabial_folds_strength");
	add_beauty_slider(gb_face, "delspot_level");
	obs_properties_add_group(ppts, "grp_face", "五官", OBS_GROUP_NORMAL, gb_face);

	// ---- 组 4：美形（3.1.27 新增）----
	// 与「五官」分开的原因：五官五项是**颜色层**（提亮/压暗/祛斑），像素位置
	// 不动；美形三项是**几何层**（改像素位置）。混在一页里用户会以为它们是
	// 同一类强度旋钮，而且几何变形的副作用（脸边轻微拖影、耗时更高）也该
	// 单独归一类说明。
	obs_properties_t *gb_shape = obs_properties_create();
	add_beauty_slider(gb_shape, "thin_face");
	add_beauty_slider(gb_shape, "big_eye");
	add_beauty_slider(gb_shape, "chin");
	obs_properties_add_group(ppts, "grp_shape", "美形", OBS_GROUP_NORMAL, gb_shape);

	// 3.1.21：不再提供「恢复默认 / 保存到 preset.json / 读取 preset.json」
	// 三个按钮。理由：面板底部已有「恢复默认」，预设文件的场景极少数人用，
	// 而三个长按钮会把属性页撑得很乱（用户明确要求删掉）。

	return ppts;
}

static void beauty_filter_update(void *data, obs_data_t *settings)
{
	struct beauty_filter *f = (struct beauty_filter *)data;
	beauty_migrate(settings);
	// 1.0.13.12 D1：与渲染线程的快照互斥，整组字段一次写完再置脏。
	AcquireSRWLockExclusive(&f->param_lock);
	beauty_filter_read(f, settings);
	// 只置脏；进程级检测选项（旋转/识别模式/人数）推迟到渲染线程下发。
	// 九个效果滑块不需要脏标记 —— 引擎每槽位做参数指纹比对，不变就不下发。
	f->dirty = true;
	ReleaseSRWLockExclusive(&f->param_lock);
}

// 取共享字段快照，并在同一临界区内消费 dirty。
// 用独占而非共享锁，是因为「读 dirty 并清零」必须是原子的；
// 十来个标量拷贝的粒度很小，无争用时开销可忽略。
static void beauty_filter_snapshot(struct beauty_filter *f,
				   struct beauty_param_snapshot *p)
{
	AcquireSRWLockExclusive(&f->param_lock);
	p->enabled = f->enabled;
	p->mirror = f->mirror;
	p->blur_type = f->blur_type;
	p->skin_detect = f->skin_detect;
	p->smooth_mode = f->smooth_mode;
	p->landmark_q = f->landmark_q;
	p->max_faces = f->max_faces;
	p->slot = f->slot;
	for (int i = 0; i < BEAUTY_NPARAM; i++)
		p->v[i] = f->v[i];
	p->dirty = f->dirty;
	f->dirty = false;
	ReleaseSRWLockExclusive(&f->param_lock);
}

// ------------------------------------------------------------------
// video_render: capture -> CPU roundtrip -> CoreEngine -> draw
// ------------------------------------------------------------------

// Mean |Laplacian| of the luma plane: a simple, scale-independent measure of
// image detail ("skin texture energy"). A working skin smoother must lower it.
//
// 3.1.21：改成 **4×4 抽样**。原来逐像素扫全帧，1080p 一趟 200 万次五点取样，
// 两次（buf_in + buf_out）在首帧上就是 15 ms 上下 —— 而这只是「开关有没有真的
// 生效」的一次性自检，抽样 1/16 的统计量完全够用（同一幅画面的均值误差 < 1%），
// 代价从 7 ms 降到 0.4 ms。首帧卡顿的一半来自这里。
static double frame_detail(const uint8_t *buf, uint32_t cx, uint32_t cy)
{
	if (!buf || cx < 3 || cy < 3)
		return 0.0;
	const uint32_t STEP = 4;
	uint64_t acc = 0;
	uint64_t n = 0;
	for (uint32_t y = 1; y + 1 < cy; y += STEP) {
		const uint8_t *row = buf + (size_t)y * cx * 4;
		const uint8_t *up = buf + (size_t)(y - 1) * cx * 4;
		const uint8_t *dn = buf + (size_t)(y + 1) * cx * 4;
		for (uint32_t x = 1; x + 1 < cx; x += STEP) {
			const size_t o = (size_t)x * 4;
			int c = row[o] + row[o + 1] + row[o + 2];
			int l = row[o - 4] + row[o - 3] + row[o - 2];
			int r = row[o + 4] + row[o + 5] + row[o + 6];
			int u = up[o] + up[o + 1] + up[o + 2];
			int d = dn[o] + dn[o + 1] + dn[o + 2];
			int lap = 4 * c - l - r - u - d;
			acc += (uint64_t)(lap < 0 ? -lap : lap);
			n++;
		}
	}
	return n ? (double)acc / (double)n / 3.0 : 0.0;
}

// Horizontal mirror on the RGBA buffer (the panel's 镜像 button).
static void frame_mirror(uint8_t *buf, uint32_t cx, uint32_t cy)
{
	const size_t row = (size_t)cx * 4;
	for (uint32_t y = 0; y < cy; y++) {
		uint8_t *r = buf + (size_t)y * row;
		for (uint32_t x = 0; x < cx / 2; x++) {
			uint8_t *a = r + (size_t)x * 4;
			uint8_t *b = r + (size_t)(cx - 1 - x) * 4;
			for (int k = 0; k < 4; k++) {
				const uint8_t t = a[k];
				a[k] = b[k];
				b[k] = t;
			}
		}
	}
}

/* 1.0.13.10（C-1）：整块资源的「全成或全不成」重分配。
 *
 * 旧写法先把 f->w / f->h 提交成新尺寸，再去 malloc / create，各自判空。
 * 于是任何一次「部分失败」都会留下一个**再也不会被修复**的状态：
 *   malloc 返回 NULL -> f->buf_in 是 NULL，但 f->w/h 已经是新值、f->tr 也建
 *   好了；下一帧的判据 `f->w != cx || f->h != cy || !f->tr` 三个条件全不成立，
 *   重分配被永久跳过，控制流直接走到 memcpy(f->buf_in, ...) 和
 *   gs_stage_texture(f->stage, ...) —— 对 NULL 解引用。
 *   （stagesurface 建失败、texrender 建成功，是同一个结局。）
 * 也不能「失败后继续用上一份缓冲」：cx/cy 已经是新尺寸，拿旧缓冲按新尺寸
 * 读写就会越界。
 *
 * 所以改成先建新的、全成才换：新资源全部落在局部变量里，任一失败就把已经
 * 建好的局部资源释放掉并返回 false，f 一个字段都不动 —— 上一帧那套仍然完整
 * 可用。调用方本帧直通，下一帧 `f->w != cx` 仍然成立，自然重试。
 */
static bool beauty_filter_alloc(struct beauty_filter *f, uint32_t cx, uint32_t cy)
{
	const size_t bytes = (size_t)cx * (size_t)cy * 4;
	uint8_t *buf_in = (uint8_t *)malloc(bytes);
	uint8_t *buf_out = (uint8_t *)malloc(bytes);
	gs_texrender_t *tr = NULL;
	gs_stagesurf_t *stage = NULL;
	gs_texture_t *out_tex = NULL;

	/* CPU 缓冲都拿不到就不必去建 GPU 资源：建了也用不上，只是白占一份显存。 */
	if (buf_in && buf_out) {
		tr = gs_texrender_create(GS_RGBA, GS_ZS_NONE);
		stage = gs_stagesurface_create(cx, cy, GS_RGBA);
		/* GS_DYNAMIC is MANDATORY here.
		 * gs_texture_set_image() is implemented on top of
		 * gs_texture_map(); the D3D11 backend maps via
		 * ID3D11DeviceContext::Map(), which only succeeds for
		 * D3D11_USAGE_DYNAMIC textures (created with GS_DYNAMIC).
		 * A plain DEFAULT texture makes Map() fail *silently*
		 * (no blog output), so gs_texture_set_image() becomes a
		 * no-op and the output texture keeps its uninitialised
		 * contents -> completely black video. */
		out_tex = gs_texture_create(cx, cy, GS_RGBA, 1, NULL, GS_DYNAMIC);
	}

	if (!buf_in || !buf_out || !tr || !stage || !out_tex) {
		blog(LOG_ERROR,
		     "[" PLUGIN_NAME "] alloc %ux%u failed (mem=%d/%d tr=%d stage=%d tex=%d); "
		     "frame skipped, retry next frame",
		     cx, cy, (int)(buf_in != NULL), (int)(buf_out != NULL),
		     (int)(tr != NULL), (int)(stage != NULL), (int)(out_tex != NULL));
		free(buf_in);
		free(buf_out);
		if (stage)
			gs_stagesurface_destroy(stage);
		if (tr)
			gs_texrender_destroy(tr);
		if (out_tex)
			gs_texture_destroy(out_tex);
		return false;
	}

	/* 新的一套已经齐了，这时才动旧的 —— 顺序反过来就是上面那个 bug 的变体。 */
	free(f->buf_in);
	free(f->buf_out);
	if (f->stage)
		gs_stagesurface_destroy(f->stage);
	if (f->tr)
		gs_texrender_destroy(f->tr);
	if (f->out_tex)
		gs_texture_destroy(f->out_tex);

	f->buf_in = buf_in;
	f->buf_out = buf_out;
	f->tr = tr;
	f->stage = stage;
	f->out_tex = out_tex;
	f->w = cx;
	f->h = cy;
	f->verified = false;
	return true;
}

static void beauty_filter_render(void *data, gs_effect_t *effect)
{
	struct beauty_filter *f = (struct beauty_filter *)data;
	obs_source_t *target = obs_filter_get_target(f->context);
	static int dbg = 0;

	// 1.0.13.12 D1：整帧只用这一份快照，不再触碰参数线程写的共享字段。
	struct beauty_param_snapshot snap;
	beauty_filter_snapshot(f, &snap);

	// 进程级检测选项（识别模式 / 人物个数）。这两个 setter 在引擎里
	// 是进程全局的，只能从渲染线程调；UI 线程只置脏。
	if (snap.dirty)
		beautyEngine().setDetectOptions(0, snap.landmark_q, snap.max_faces);

	if (!snap.enabled || snap.slot < 0 || !target) {
		obs_source_skip_video_filter(f->context);
		return;
	}

	const uint32_t cx = obs_source_get_base_width(target);
	const uint32_t cy = obs_source_get_base_height(target);
	if (!cx || !cy) {
		obs_source_skip_video_filter(f->context);
		return;
	}

	if (dbg < 3) {
		blog(LOG_INFO, "[" PLUGIN_NAME "] render#%d target=%s %ux%u (v%s, slot=%d)", dbg,
		     obs_source_get_name(target), cx, cy, PLUGIN_VERSION, snap.slot);
		dbg++;
	}

	// (re)allocate on size change.
	//
	// 判据里必须带上**所有**资源指针，不能只看 tr：任何一项为 NULL 都说明上次
	// 分配只成功了一半，必须重试。为什么（C-1，1.0.13.10）见 beauty_filter_alloc()。
	if (f->w != cx || f->h != cy || !f->tr || !f->stage || !f->out_tex ||
	    !f->buf_in || !f->buf_out) {
		if (!beauty_filter_alloc(f, cx, cy)) {
			obs_source_skip_video_filter(f->context);
			return;
		}
	}

	// 1) capture the upstream frame into our texrender.
	//
	//    (obs-source.c) exactly. Two details matter and are easy to get wrong:
	//
	//    a) the blend state + gs_clear before drawing the source;
	//    b) WHICH render call to use.  obs_source_default_render() begins the
	//       "Draw" technique first and works for synchronous sources;
	//       asynchronous sources (cameras, capture cards) must keep using
	//       obs_source_video_render().
	gs_texrender_reset(f->tr); // texrender is one-shot: clear 'rendered' before re-begin
	const bool tr_ok = gs_texrender_begin(f->tr, cx, cy);
	if (tr_ok) {
		gs_blend_state_push();
		gs_blend_function_separate(GS_BLEND_SRCALPHA, GS_BLEND_INVSRCALPHA, GS_BLEND_ONE,
					   GS_BLEND_INVSRCALPHA);

		struct vec4 clear_color;
		vec4_zero(&clear_color);
		gs_clear(GS_CLEAR_COLOR, &clear_color, 0.0f, 0);
		gs_ortho(0.0f, (float)cx, 0.0f, (float)cy, -100.0f, 100.0f);

		obs_source_t *parent = obs_filter_get_parent(f->context);
		const uint32_t parent_flags = parent ? obs_source_get_output_flags(parent) : 0;
		const bool custom_draw = (parent_flags & OBS_SOURCE_CUSTOM_DRAW) != 0;
		const bool async = (parent_flags & OBS_SOURCE_ASYNC) != 0;

		if (target == parent && !custom_draw && !async)
			obs_source_default_render(target);
		else
			obs_source_video_render(target);

		gs_blend_state_pop();
		gs_texrender_end(f->tr);
	}
	gs_texture_t *in_tex = gs_texrender_get_texture(f->tr);
	if (!in_tex || !f->out_tex) {
		obs_source_skip_video_filter(f->context);
		return;
	}

	// 2) download to CPU
	bool got = false;
	bool mapped_held = false;   // 1.0.11.0：零拷贝时 map 要一直持有到引擎读完
	const uint8_t *in_p = f->buf_in;
	const double t_dl = f->prof_on ? beauty_now_ms() : 0.0;
	gs_stage_texture(f->stage, in_tex);
	uint8_t *ptr = NULL;
	uint32_t linesize = 0;
	if (gs_stagesurface_map(f->stage, &ptr, &linesize) && ptr) {
		const size_t row = (size_t)cx * 4;
		if (linesize == row && beauty_zero_copy()) {
			/* A5：行内无 padding，直接把映射指针当输入，省掉整帧 memcpy。
			 * 代价是 map 必须持有到引擎读完（否则指针失效），所以这里不 unmap，
			 * 由下面第 4 步之前的收尾段负责。 */
			in_p = ptr;
			mapped_held = true;
		} else if (linesize == row) {
			memcpy(f->buf_in, ptr, row * cy);
			gs_stagesurface_unmap(f->stage);
		} else {
			for (uint32_t y = 0; y < cy; y++)
				memcpy(f->buf_in + (size_t)y * row, ptr + (size_t)y * linesize, row);
			gs_stagesurface_unmap(f->stage);
		}
		got = true;
	}

	/* 回读失败就直接直通，**不要**再喂一个上一帧的旧 buf_in 给引擎：
	 * 既有画面正确性问题（引擎会照着旧帧做人脸跟踪），也白白浪费一次
	 * 整帧处理。放在引擎调用之前判断。 */
	if (!got) {
		obs_source_skip_video_filter(f->context);
		return;
	}
	if (f->prof_on)
		f->prof_dl += beauty_now_ms() - t_dl;

	// 3) 引擎处理（自研核）。
	//
	// 全 0 参数时引擎输出与输入逐字节一致，直接透传，省掉一整个 CPU 往返
	// （含一次 BGRA 双换和一次 render 调用）。
	BeautySettings s;
	beauty_filter_settings(&snap, s);
	const bool skip_sdk = s.allZero();
	const double t_proc = f->prof_on ? beauty_now_ms() : 0.0;

	if (!skip_sdk) {
		const bool ok = beautyEngine().process(snap.slot, in_p, f->buf_out,
						       (int)cx, (int)cy, s);
		if (!ok) {
			// 每实例只报一次：恢复后清零，下次故障还会再报。
			if (!f->err_reported) {
				f->err_reported = true;
				blog(LOG_ERROR, "[" PLUGIN_NAME "] 引擎处理失败：%s（本实例直通）",
				     beautyEngine().lastErr());
			}
			// 零拷贝路径持有着 map，这条提前返回必须先放开，否则 stage
			// surface 会一直锁着，下一帧 gs_stage_texture 会失败。
			if (mapped_held)
				gs_stagesurface_unmap(f->stage);
			obs_source_skip_video_filter(f->context);
			return;
		}
		f->err_reported = false;

		// C20：肤色自适应首次估计收效后补打一行 skin=。init 那行永远是
		// "(center=default, not yet estimated)"，真机自查「第 2 帧以后真的
		// 在估计」全靠这一行 —— worker 一次性置位，这里取走即清，之后每帧零开销。
		if (beautyCoreSkinAnnounce())
			blog(LOG_INFO, "[" PLUGIN_NAME "] %s", beautyCoreSkinInfo());
	} else {
		memcpy(f->buf_out, in_p, (size_t)cx * cy * 4);
		/* 1.0.8.0：A 通道置位已搬进引擎（beauty_core.cpp 的 forceOpaque），
		 * 但「面板全 0」这条分支不调引擎，所以这里保留一份。这条路只在整块
		 * 面板为 0 时走到，一帧 0.4 ms 不在预算讨论范围内。 */
		uint32_t *pz = (uint32_t *)(void *)f->buf_out;
		const size_t pxn = (size_t)cx * cy;
		for (size_t k = 0; k < pxn; k++)
			pz[k] |= 0xFF000000u;
	}
	if (f->prof_on)
		f->prof_proc += beauty_now_ms() - t_proc;
	// 1.0.9.0：引擎分段耗时。skip_sdk 的帧没进引擎，分段值没有意义，不计。
	if (f->prof_on && !skip_sdk) {
		double st[6] = {0, 0, 0, 0, 0, 0};
		beautyEngine().lastStageMs(st);
		for (int i = 0; i < 6; i++)
			f->prof_st[i] += st[i];
	}

	// 4) upload the processed frame into our (dynamic) texture
	const double t_up = f->prof_on ? beauty_now_ms() : 0.0;
	/* 1.0.8.0：这里原来有一遍「全帧 207 万次 32 位读改写把 A 置 255」（1080p
	 * 实测约 0.4 ms）。现在由引擎在输出的最后一步做（beauty_core.cpp 的
	 * forceOpaque），那一刻 dst 刚被写过、还在 cache 里，同一件事便宜 3~4 倍。
	 * 上传段因此只剩 gs_texture_set_image 自己。
	 *
	 * 1.0.10.0：BEAUTY_ALPHA_IN_ENGINE=0 时引擎不碰 A，这里必须补回来 ——
	 * 否则 OBS 合成出来是黑的。这条分支只为真机对照实验存在。 */
	if (!skip_sdk && !beautyCoreAlphaInEngine()) {
		uint32_t *pa = (uint32_t *)(void *)f->buf_out;
		const size_t pxa = (size_t)cx * cy;
		for (size_t k = 0; k < pxa; k++)
			pa[k] |= 0xFF000000u;
	}

	// The first self-check compares the engine output before display transforms.
	// Save both metrics before buf_in is reused as the rotation scratch buffer.
	const double detail_in_check =
		!f->verified && !skip_sdk ? frame_detail(in_p, cx, cy) : 0.0;
	const double detail_out_check =
		!f->verified && !skip_sdk ? frame_detail(f->buf_out, cx, cy) : 0.0;

	/* 零拷贝路径的 map 到这里才放开：引擎、细节自检都读完了 in_p。
	 * 必须在下面的 self-check 之前 —— 那里会再 gs_stage_texture + map 一次
	 * f->stage，surface 还锁着的话那一步会失败。
	 * unmap 的耗时计进「下载」那一项，否则零拷贝会把成本藏到别处去。 */
	if (mapped_held) {
		const double t_un = f->prof_on ? beauty_now_ms() : 0.0;
		gs_stagesurface_unmap(f->stage);
		if (f->prof_on)
			f->prof_dl += beauty_now_ms() - t_un;
		mapped_held = false;
	}

	if (snap.mirror)
		frame_mirror(f->buf_out, cx, cy);

	gs_texture_set_image(f->out_tex, f->buf_out, cx * 4, false);

	// 性能埋点输出（BEAUTY_PROFILE=1）。每 180 帧（60fps 下 3 秒）报一次，
	// 免得刷爆日志。这三个数决定了「要不要整体改走 GPU」：
	// 下载那一项含 stagesurface map 的同步等待，是 GPU→CPU 的真实代价。
	if (f->prof_on) {
		f->prof_up += beauty_now_ms() - t_up;
		f->prof_frames++;
		if (f->prof_frames >= 180) {
			const double n = (double)f->prof_frames;
			const double dl = f->prof_dl / n;
			const double pr = f->prof_proc / n;
			const double up = f->prof_up / n;
			// 掩码↔帧对齐比率（3.1.10）：探针返回的是启动以来的全量值，
			// 取差值才是本窗口的。首个窗口（基线还是 0）显示的是从启动
			// 到现在的累计比率 —— 含义一样，只是窗口更长。
			uint64_t al_used = 0, al_total = 0;
			beautyCoreAlignStat(&al_used, &al_total);
			const uint64_t al_du = al_used - f->prof_align0_used;
			const uint64_t al_dt = al_total - f->prof_align0_total;
			f->prof_align0_used = al_used;
			f->prof_align0_total = al_total;
			// 3.1.40：无脸透传帧数同样取窗口差值。它是「跳过真的发生了」的唯一
			// 直接证据 —— 引擎耗时 0.00 也可能只是磨皮参数为 0。
			const uint64_t nf_all = beautyCoreNoFaceFrames();
			const uint64_t nf_du = nf_all - f->prof_noface0;
			f->prof_noface0 = nf_all;
			blog(LOG_INFO,
			     "[" PLUGIN_NAME "] 性能 %ux%u：下载 %.2f + 引擎 %.2f + 上传 %.2f"
			     " = %.2f ms/帧（%d 帧平均）对齐 %llu/%llu（%.0f%%）无脸跳过 %llu",
			     cx, cy, dl, pr, up, dl + pr + up, f->prof_frames,
			     (unsigned long long)al_du, (unsigned long long)al_dt,
			     al_dt ? (double)al_du * 100.0 / (double)al_dt : 100.0,
			     (unsigned long long)nf_du);
			// 1.0.9.0：引擎内部分段（同一窗口的均值）。0=检测+掩码 1=磨皮
			// 2=色调 3=细节 4=美形+A通道。四项相加不等于引擎总时 —— 差值
			// 是掩码/ROI 之外的公共开销，留在「引擎」那一项里由人均摊。
			int rw = 0, rh = 0, rpx = 0;
			beautyEngine().lastRoi(&rw, &rh, &rpx);
			blog(LOG_INFO,
			     "[" PLUGIN_NAME "] 分段：检测+掩码 %.2f | 磨皮 %.2f | 色调 %.2f"
			     " | 细节 %.2f | 美形+alpha %.2f | ROI %dx%d 掩码 %d"
			     " | 盒块 %d 阈值 %d par_copy=%d alpha=%s fuse=%d",
			     f->prof_st[0] / n, f->prof_st[1] / n, f->prof_st[2] / n,
			     f->prof_st[3] / n, f->prof_st[4] / n, rw, rh, rpx,
			     beautycore::boxBlockWidth(), beautycore::boxMinPixels(),
			     beautycore::parCopyOn(),
			     beautyCoreAlphaInEngine() ? "eng" : "plugin",
			     beautycore::boxFuseOn());
			f->prof_frames = 0;
			f->prof_dl = 0.0;
			f->prof_proc = 0.0;
			f->prof_up = 0.0;
			for (int i = 0; i < 6; i++)
				f->prof_st[i] = 0.0;
		}
	}

	// One-shot end-to-end self check.
	//
	//  1) copy the uploaded texture back through a stagesurface and measure its
	//     brightness. mean ~= 0 means the upload silently did nothing (e.g. a
	//     non-GS_DYNAMIC texture) and the picture would be black.
	//  2) compare the detail (mean |Laplacian|) of the frame we received with
	//     the frame the engine returned. A working skin smoother must lower it;
	//     if the two are equal the blur parameters had no effect at all.
	//
	// f->stage is free here - its contents already went to buf_in.
	if (!f->verified) {
		f->verified = true;
		gs_stage_texture(f->stage, f->out_tex);
		uint8_t *vp = NULL;
		uint32_t vls = 0;
		if (gs_stagesurface_map(f->stage, &vp, &vls) && vp) {
			uint64_t sum = 0;
			uint64_t n = 0;
			for (uint32_t y = 0; y < cy; y += 16) {
				const uint8_t *row = vp + (size_t)y * vls;
				for (uint32_t x = 0; x < cx; x += 16) {
					sum += row[(size_t)x * 4] + row[(size_t)x * 4 + 1] +
					       row[(size_t)x * 4 + 2];
					n += 3;
				}
			}
			gs_stagesurface_unmap(f->stage);
			IBeautyEngine &e = beautyEngine();
			blog(LOG_INFO,
			     "[" PLUGIN_NAME
			     "] self-check: out_tex mean=%.1f (0.0 = upload broken) | detail in=%.3f "
			     "out=%.3f (%+.1f%%) | blur_type=%d blur=%.0f skin_detect=%d faces=%d "
			     "engine=%s region=%s core=%.1fms",
			     n ? (double)sum / (double)n : 0.0, detail_in_check, detail_out_check,
			     detail_in_check > 0.0
				     ? (detail_out_check / detail_in_check - 1.0) * 100.0
				     : 0.0,
			     snap.blur_type, snap.v[BEAUTY_IDX_BLUR], snap.skin_detect, e.lastFaces(),
			     e.id(), region_state(e), e.lastCoreMs());
		} else {
			blog(LOG_WARNING, "[" PLUGIN_NAME "] self-check: could not map out_tex");
		}
	}

	if (f->frame_id <= 3) {
		IBeautyEngine &e = beautyEngine();
		blog(LOG_INFO,
		     "[" PLUGIN_NAME
		     "] frame#%d drawn %ux%u faces=%d engine=%s region=%s skip_sdk=%d",
		     f->frame_id, cx, cy, e.lastFaces(), e.id(), region_state(e),
		     skip_sdk ? 1 : 0);
	}
	f->frame_id++;

	//    Uses gs_technique_begin/begin_pass instead of gs_effect_loop():
	//    gs_effect_loop() bails out with "An effect is already active" when
	//    OBS has already begun a technique around our video_render call.
	gs_effect_t *draw_effect = obs_get_base_effect(OBS_EFFECT_DEFAULT);
	gs_technique_t *tech = gs_effect_get_technique(draw_effect, "Draw");
	gs_eparam_t *image = gs_effect_get_param_by_name(draw_effect, "image");
	if (!tech) {
		obs_source_skip_video_filter(f->context);
		return;
	}

	const bool linear_srgb = gs_get_linear_srgb();
	const bool prev_srgb = gs_framebuffer_srgb_enabled();
	gs_enable_framebuffer_srgb(linear_srgb);

	if (image) {
		if (linear_srgb)
			gs_effect_set_texture_srgb(image, f->out_tex);
		else
			gs_effect_set_texture(image, f->out_tex);
	}

	gs_blend_state_push();
	gs_blend_function(GS_BLEND_ONE, GS_BLEND_INVSRCALPHA);

	const size_t passes = gs_technique_begin(tech);
	for (size_t i = 0; i < passes; i++) {
		gs_technique_begin_pass(tech, i);
		gs_draw_sprite(f->out_tex, 0, cx, cy);
		gs_technique_end_pass(tech);
	}
	gs_technique_end(tech);

	gs_blend_state_pop();
	gs_enable_framebuffer_srgb(prev_srgb);
}

// ------------------------------------------------------------------
// Module
// ------------------------------------------------------------------
static struct obs_source_info beauty_filter_info = {};

OBS_DECLARE_MODULE()

static void obs_module_unload(void)
{
	// 释放引擎 / GL / 语义区域资源。滤镜实例此时已被 OBS 全部销毁
	// （source info 的 destroy 先于模块卸载），槽位都已归还。
	beautyEngine().release();
	blog(LOG_INFO, "[" PLUGIN_NAME "] engine released");
}

MODULE_EXPORT const char *obs_module_description(void);
const char *obs_module_description(void)
{
	return "OBS美颜滤镜 CPU 版 (OBS Beauty, standalone core) v" PLUGIN_VERSION;
}

bool obs_module_load(void)
{
	// 1.0.13.10（C-2/C-3）：先说清楚这一份 DLL 到底读不读 BEAUTY_* 环境变量。
	// 发布版加锁后所有覆盖一律失效，而“设了变量但没变化”是最难查的一类现象，
	// 所以这一行必须在所有其他日志之前打。台架（05_验证）也靠这两个不同字面串分辨加锁版。
#ifdef BEAUTY_ENV_LOCK
	blog(LOG_INFO, "[" PLUGIN_NAME "] env override: locked (release build)");
#else
	blog(LOG_INFO, "[" PLUGIN_NAME "] env override: open (dev build)");
#endif

	// 引擎日志接进 OBS 日志系统；不接的话引擎消息会写到 stderr（OBS 里看不到）。
	beauty_set_log_fn(beauty_obs_log);

	// 预热：不等第一个滤镜创建，让模块加载就完成那 ~2 秒的引擎初始化，
	// 与 1.x 行为一致（首帧不卡）。失败不阻塞 —— 滤镜会直通并每实例报一次错。
	std::string err;
	bool didInit = false;
	if (!beautyEngine().preheat(err, didInit)) {
		blog(LOG_ERROR,
		     "[" PLUGIN_NAME "] engine init failed (%s) - filter passes video through: %s",
		     beautyEngineId(), err.c_str());
	} else if (didInit) {
		IBeautyEngine &e = beautyEngine();
		// 刻意用字符串拼接而不是 printf 格式化：这一行有 6 个值要打，是全文件最
		// 容易被改的一行，而 blog() 不受编译器格式检查保护（见文件头的警告）。
		// 3.1.4 就是在这里多加了一个 %s 少配一个参数，把 OBS 崩了两次。
		std::string msg = "init OK (CPU v";
		msg += PLUGIN_VERSION;
		msg += ", engine=";
		msg += e.id() ? e.id() : "?";
		msg += "/";
		msg += e.version() ? e.version() : "?";
		msg += ", region=";
		msg += region_state(e);
		msg += ", item=";
		msg += std::to_string(e.itemId());
		msg += ", owner_thread=";
		msg += std::to_string(e.ownerThread());
		// 3.1.40：无脸透传开关状态。排查「无人画面还是卡」时，这一位能直接
		// 排除「被 BEAUTY_NOFACE_SKIP=0 回退掉了」这种可能。
		msg += ", noface_skip=";
		msg += beautyCoreNoFaceSkip() ? "on" : "off";
		// 2026-11-09：band 磨皮是否吃 ROI。这一位是「这一份二进制到底是不是
		// 带 ROI 裁剪的构建」的唯一日志证据——装机目录、自定义 OBS_PLUGINS_PATH
		// 目录可能同时存在两份同名 DLL，只有注册成功的那个会打这一行。
		msg += ", band_roi=";
		msg += "crop";
		// 2026-11-09（1.0.5.0）：头歪补偿在不在。与 band_roi 同理，是「手上这一份
		// 到底是不是 1.0.5.0」的证据；顺带把 ±45 探测的开关状态和阈值打出来，
		// 排查「歪头没效果」时不用再猜是不是被 BEAUTY_AUTO_ROLL=0 关掉了。
		msg += ", roll_probe=";
		msg += beautyCoreAutoRoll() ? "on" : "off";
		// 2026-11-09（1.0.7.0）：脖子通道有没有按立正方向重画。`dir` = 参数化到
		// (u,v) 的版本；`off` = 被 BEAUTY_NECK=0 关掉。旧版（≤1.0.5.0）打不出来，
		// 所以这一位同时是「装机的那份到底是不是 1.0.7.0」的证据。
		msg += ", neck=";
		msg += beautyCoreNeckOn() ? "dir" : "off";
		// 1.0.9.0：盒式的两个可调项。对照实验必须能证明「跑的是哪一档」，
		// 否则同一台机器上的两组数据可能根本不是同一份配置。
		msg += ", box_block=";
		msg += std::to_string(beautycore::boxBlockWidth());
		msg += ", box_minpx=";
		msg += std::to_string(beautycore::boxMinPixels());
		// 1.0.10.0：A2 / A4 两处 1.0.8.0 改动的开关状态。
		msg += ", par_copy=";
		msg += beautycore::parCopyOn() ? "on" : "off";
		msg += ", alpha=";
		msg += beautyCoreAlphaInEngine() ? "engine" : "plugin";
		// 1.0.11.0：下载零拷贝开关（默认 off）。真机对照要靠这一位确认跑的是哪条路。
		msg += ", zc=";
		msg += beauty_zero_copy() ? "on" : "off";
		msg += ", tone_lut=";
		msg += beautycore::toneIntLutOn() ? "int" : "float";
		// 1.0.13.0：磨皮低频层是否走三通道融合 + SSE 垂直趟。两条路径逐位等价，
		// 这一位只用来确认对照实验里跑的是哪一条。
		msg += ", fuse=";
		msg += beautycore::boxFuseOn() ? "on" : "off";
		msg += ")";
		blog(LOG_INFO, "[" PLUGIN_NAME "] %s", msg.c_str());
		// C20：皮肤判据快照。真机「磨皮没效果」的头号原因是肤色掩码被白平衡
		// 压低（实测真机帧掩码只剩 34%），而这一点光看画面看不出来。打一行
		// 让用户能自查自适应有没有开、椭圆中心在哪。
		blog(LOG_INFO, "[" PLUGIN_NAME "] %s", beautyCoreSkinInfo());

		// 但会静默退化成「全帧磨皮」—— CPU 约 2.5 倍，而且清晰 / 美白 / 红润 /
		// 五官五项 / 脸内锐化全部不执行。3.1.4 的用户看到的就是「CPU 22% + 个别
		// 功能能用」，查了一整轮才发现是模型没加载。所以这里必须留一条 WARN，
		// 不能让同样的事再悄悄发生一次。
		if (e.id() && strcmp(e.id(), "core") == 0 && !e.regionActive()) {
			blog(LOG_WARNING,
			     "[" PLUGIN_NAME "] core engine has NO face mask: %s. "
			     "Falling back to full-frame smoothing (higher CPU, most effects "
			     "disabled). 3.1.40 起「模型正常、但本帧确实没人」会直接透传，"
			     "只有模型不可用时才走全帧兜底。Check onnxruntime.dll + "
			     "models\\yunet.onnx next to the plugin dll.",
			     (e.lastErr() && e.lastErr()[0]) ? e.lastErr() : "(no detail)");
		}
	}

	beauty_filter_info.id = BEAUTY_FILTER_ID;
	beauty_filter_info.type = OBS_SOURCE_TYPE_FILTER;
	beauty_filter_info.output_flags = OBS_SOURCE_VIDEO;
	beauty_filter_info.get_name = beauty_filter_name;
	beauty_filter_info.create = beauty_filter_create;
	beauty_filter_info.destroy = beauty_filter_destroy;
	beauty_filter_info.get_defaults = beauty_filter_get_defaults;
	beauty_filter_info.get_properties = beauty_filter_properties;
	beauty_filter_info.update = beauty_filter_update;
	beauty_filter_info.video_render = beauty_filter_render;

	obs_register_source_s(&beauty_filter_info, sizeof(beauty_filter_info));

	blog(LOG_INFO, "[" PLUGIN_NAME "] filter registered as '%s' (v%s)",
	     BEAUTY_FILTER_ID, PLUGIN_VERSION);
	return true;
}
