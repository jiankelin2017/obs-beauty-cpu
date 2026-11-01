# 引擎抽象层 beauty_core —— 第 1 步（骨架 + A/B 开关）

> 日期 2026-10-27 · 对应源码 3.0.19 · 与 `05_文档/自研美颜引擎替换方案_v1.md` 配套
>
> 本步**不改任何现有行为**。默认实现仍是 NamaAdapter，转发到 `NamaEngine`。

## 1. 做了什么

| 文件 | 动作 | 说明 |
|---|---|---|
| `00_源码/beauty_core.h` | 新增 | `IBeautyEngine` 接口 + `beautyEngine()` 工厂 |
| `00_源码/beauty_core.cpp` | 新增 | `NamaAdapter`（转发）/ `PassthroughEngine`（直通）/ 工厂选实现 |
| `00_源码/obs-nama-beauty.cpp` | 改 | 11 处 `NamaEngine::inst()` → `beautyEngine()`；加 include |
| `01_构建/build_manual.bat` | 改 | 源文件列表加 `beauty_core.cpp` |
| `00_源码/beauty_core_abtest.cpp` | 新增 | 脱离 OBS 的行为验证程序 |
| `06_离线验证/build_beauty_core_abtest.bat` | 新增 | 编译上述测试程序（纯 ASCII，通配符定位源码目录） |

抽层之后 OBS 胶水层只认 `IBeautyEngine`，不再直接依赖 `NamaEngine`。

## 2. 开关

环境变量 `NAMA_ENGINE_IMPL`，进程内只解析一次：

| 值 | 实现 | 用途 |
|---|---|---|
| （未设置）/ `nama` | NamaAdapter | 默认，与抽层前行为一致 |
| `passthrough` | PassthroughEngine | 证明开关接上了；也是新引擎出错时的安全降级目标 |
| `core` | 尚未实现，**明确退回 nama** | 宁可退回去，也不给一个「看着能跑、实际没效果」的引擎 |

## 3. 验证结果（本机实测）

| 项 | 结果 |
|---|---|
| `01_构建/build_manual.bat` 编译 | OK，`/W3` 无警告 |
| `NAMA_ENGINE_IMPL=passthrough` | 6/6 PASS：输出与输入逐字节相同、支持 `src==dst`、诊断值保守 |
| `NAMA_ENGINE_IMPL=core` | 按设计退回 `nama` |
| **转发等价性**（640×394 真实帧，磨皮50/美白30/锐化20） | `beautyEngine().process()` 与 `NamaEngine::inst().process()` 输出**逐字节相同**；相对输入改动 295964 字节（证明不是空跑） |
| `advanceFrame=false` | 接口新增该参数，供同帧双路径对拍时消除帧序号差异 |

复现命令（在 `06_离线验证` 下）：

```
build_beauty_core_abtest.bat
beauty_core_abtest.exe passthrough
beauty_core_abtest.exe nama <引擎数据目录> probe_in.raw 640 394
```

## 4. 与《自研美颜引擎替换方案 v1》的关系

方案 v1 规划的目标结构是 `beauty/{core,gpu,vision,color,warp,diag}` 自研静态库。
本步的 `beauty_core` **不是**那个库，而是它前面的**切换层**：

```
obs-nama-beauty.cpp ──> IBeautyEngine ──> NamaAdapter        （现状）
                                      └─> PassthroughEngine  （降级）
                                      └─> CoreEngine ──> beauty/ 自研核心（M1 之后）
```

将来 `beauty/` 落地时，只需在 `beauty_core.cpp` 里加一个 `CoreEngine` 类和一行分支，
OBS 侧零改动。

**⚠️ 前置阻塞**：方案 v1 第 9 节的三件事（推理跑 CPU 还是 GPU / 训练工具算不算第三方 /
老观感要不要保）尚未拍板，M1 之后的方向会因此分叉，建议先拍板再动 M1。

**⚠️ 时效性**：方案 v1 的 M0「基线冻结」是唯一有时效性的一步 —— 趁 SDK 还在手上把
输出固化成回归集（`06_离线验证/goldens/`），否则后续所有对齐只能靠肉眼。

## 5. 本步没做的事

- 未升版本号：对外行为零变化，`NAMA_BUILD_*` 仍为 3.0.19。
- 未在真实 OBS 里跑：插件 DLL 依赖 `obs.dll`，无法脱离 OBS 加载；已用「同进程双路径
  逐字节对比」替代验证转发等价性。真机验收仍需装一次 OBS。
- 未接任何新算法：S1（换掩码）/ S2（换磨皮核）/ S3（换人脸检测）都还没开始。
