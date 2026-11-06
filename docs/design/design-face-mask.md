# design · 肤色掩码、人脸框与五官局部

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.2` |
| 最后更新 | 2026-11-06 |
| 适用代码版本 | CPU 线 `1.0.0.2`（实现与开关已在 `01_源码/beauty_core.cpp` 逐字复核；§12 为 1.0.0.2 新增） |
| 维护人 | 待人工确认 |
| 状态 | `Active`（机制 / 根因 / 开关有效；**历史轴实测数字未重测**） |
| 替代文档 | 归档 `docs/archive/c03-lumina-align-20261106.md`、`c05-robustness-20261106.md`、`c12-face-region-20261106.md`、`c20-whitebalance-rootcause-20261106.md`、`c21-adaptive-skin-center-20261106.md`；并引用 `ab-mask` / `c02` / `c19` |

> **本文只保留结论 / 开关 / 坑 / 证伪 / 失效说明。**
> 按 2026-11-06 裁定，**完全不搬历史轴的数字表格**：IoU、掩码占比、倍数、灰阶、
> 百分比一律只在归档件查。本文出现的数字**仅是源码中的开关取值 / 编译期常量**，不是验收数据。

---

## 1. 结论先行

掩码判据 = **肤色 ∩ YuNet 人脸框**，取代第三方分割模型（`ab-mask`）。当前最关键的结论是一条**证伪链的终点**：

> **「真机磨皮不足」的最终根因是肤色椭圆中心写死、不随摄像头白平衡自适应**（`c20`），
> 已由 `c21` 落地 `estimateSkinCenter()` 方案 A（中心逐帧自适应）+ 方案 B2（半径缩放兜底）。
> `c19` 曾归因于「核尺度不随脸宽缩放」，**该根因已被 `c20` 推翻，不得据此施工**。

当前源码（`beauty_core.cpp`）逐字复核：`g_skinAdapt = true` 默认开启；`estimateSkinCenter()` 存在并在
`process()` 中调用；`BEAUTY_SKIN_HARD=1` 可回旧矩形窗判据。

## 2. 掩码几何与保护区（`c03`、`ab-mask`）

- 肤色判据从矩形窗改为**椭圆软边**；暗部不算皮肤。
- YuNet 5 关键点生成**椭圆五官保护区**；`BEAUTY_MASK_SHAPE` 可切几何（0=矩形回旧行为，3=脸+脖子都用椭圆）。
- 掩码边界羽化 `BEAUTY_MASK_FEATHER`：`=0` 关闭（与旧行为逐字节相同，用于 A/B）；`>0` 固定像素；
  不设时按脸宽自适应。
- **已知弱点**（`ab-mask`）：肤色背景误判明显、侧脸 / 遮挡下人脸框会飘；`grow` 扫描峰值只是历史轴标定结果。
- **环境坑**（`ab-mask`）：`cv2.dnn` 读不了中文路径，离线验证脚本需 `_ascii_path()` 包装（该函数在 `05_验证/`，**不是插件源码符号**）。

## 3. 根因与落地（`c20` → `c21`）

- **`BEAUTY_SKIN_HARD=1` 旧硬判据在真机帧完全失效**；软判据方向正确，但中心固定时会整体偏掉。
  这解释了 `c17`「削过头」与 `c19`「削不够」为何方向翻转：不是强度问题，是掩码覆盖范围随白平衡漂移。
- `c20` 四条局限（去掉历史数字后仍成立）：单帧单摄像头样本、掩码占比是反推值、
  **掩码修好 ≠ 削对频段**、偏色并不极端。
- 当前实现开关：
  - `BEAUTY_SKIN_ADAPT=0`：回固定中心（默认开启自适应）。
  - `BEAUTY_SKIN_RADIUS`：半径缩放兜底。
  - `BEAUTY_SKIN_EMA`：肤色中心时域平滑，真机观察到强度逐帧闪时可压抖动。
  - `BEAUTY_BLUR_SAT`：档位饱和（应急只调这个）。
- ⚠️ **`BEAUTY_SKIN_EMA` 破坏逐字节确定性**（`c21` §3.1）：离线 golden A/B 必须关掉。
  另一处确定性要求是 `core_probe.cpp` 强制 `BEAUTY_ASYNC_DETECT=0`，见 `docs/design/design-cpu-performance.md` §8。
- **应急口径**：只调 `BEAUTY_BLUR_SAT`，**不要动核参数**去追观感。
- `c21` 三项遗留（均未在 CPU `1.0.0.0` 复核）：高档位细纹理矫枉过正、阴影频带双尺度缺口、高档位耗时。
  其中「阴影频带双尺度缺口」在 `c17` §6 也被登记为**新功能、未实施**。

## 4. 鲁棒性三项机制（`c05`）

- **丢帧保持**：检测失败不等于脸消失，沿用上一次掩码最多 `kMaskHold` 个检测周期
  （源码 `beauty_core.cpp` 中 `static const int kMaskHold = 6`）。
- **过曝保护**：高亮区域不按肤色判据处理。
- **关键点校验**：5 点异常时不生成五官保护区。
- 三者对应的开关与判定细节见归档件 `docs/archive/c05-robustness-20261106.md`。

## 5. 掩码↔帧对齐与异步配套（源码 `beauty_core.cpp` 初始化段）

- `BEAUTY_MASK_ALIGN=0`：回到「当前帧 + 旧掩码」（有拖影但零延迟，A/B 用）。
- `BEAUTY_MASK_EVERY`：异步检测提交周期；源码注释给出的老节奏回退值可用于真机当场对比，无需改代码重编译。
- `BEAUTY_ASYNC_DETECT` 的当前口径见 `docs/design/design-cpu-performance.md` §8；`BEAUTY_NOFACE_SKIP` 及无脸帧透传的历史判据见 `docs/archive/c1-cpu-performance-20261106.md` 附录 A（当前口径以 `01_源码/` 为准）。

## 6. 五官局部五项（`c12`）

- 五项几何参数**全部归一化到人脸框**，换分辨率 / 机位不应改变相对位置。
- **祛斑痘是「拉回局部均值」而不是模糊**；把它当磨皮调强度会越调越糊。
- **法令纹的旋转必须在像素空间算**，在归一化空间旋转会得到错误方向。
- `c12` §6 三个真 bug（椭圆整体左移、局部均值被放大、`rx` 退化）是历史轴修复记录，
  具体数值见归档件；修法已随源码进入当前轴，但**未在 CPU `1.0.0.0` 复核**。
- `beauty_region.cpp` 仍在当前源码。

## 7. 已证伪 / 明确不做

- **阈值软膝实测无效、默认关闭**（`c03`）；立体感差距靠 clarity 主动增强而非被动保护，
  见 `docs/design/design-tone-detail.md`。
- **「椭圆 mask 替代肤色 ∩ 人脸框」不可行**（`c02` §4），见 `docs/design/design-smoothing.md`。
- **「核尺度随脸宽自适应」落地方向未被采纳**（`c18` §4）；`c19` 的同一根因结论已被 `c20` 推翻。
- 取舍（`oss-survey` §8.4 / `tech-roadmap` §6）原有四项：**不做人脸框 EMA、不换贴脸椭圆、不做运动预测、不上 GPU**。
  2026-11-06 用户裁定**撤销其中「不做人脸框 EMA」一项**，落地见 §12；其余三项维持。
  ⚠️ 「人脸框 EMA」与 `c11` 亮度平面 EMA、`c21` 肤色中心 EMA **不是同一件事**，见
  `docs/design/design-tone-detail.md` §3.1。

## 8. 开关清单（均为 `01_源码/` 中实存名字）

`BEAUTY_SKIN_HARD` · `BEAUTY_SKIN_ADAPT` · `BEAUTY_SKIN_EMA` · `BEAUTY_SKIN_RADIUS` ·
`BEAUTY_BLUR_SAT` · `BEAUTY_MASK_SHAPE` · `BEAUTY_MASK_FEATHER` · `BEAUTY_MASK_ALIGN` ·
`BEAUTY_MASK_EVERY` · `BEAUTY_ASYNC_DETECT` · `BEAUTY_NOFACE_SKIP` ·
`BEAUTY_FACE_EMA` · `BEAUTY_FACE_HOLD` · `BEAUTY_FACE_AREA` · `BEAUTY_FACE_IOU`；
常量 `kMaskHold`。

## 9. 失效说明（不得据此施工）

- 归档件为历史轴 `3.1.x / CoreEngine 0.7 / 0.9 / 0.x` 口径，**非当前 CPU `1.0.0.0`**。
- 路径 `00_源码` → `01_源码`、`06_离线验证` → `05_验证`。
- **开关改名**：`LEGACY_ENGINE_IMPL` → `BEAUTY_ENGINE_IMPL`；`LEGACY_BUILD_STR` 已失效。
- `ref_golden.dll` 只是 `05_验证/ref_driver/` 的离线基准 DLL（条件编译 `BEAUTY_WITH_LEGACY_ENGINE`），
  `legacy_engine.h` 不在插件编译路径，**插件不编译**。
- `c20` §5「候选修法」已由 `c21` 落地、§7「下一步建议」属过程记录；`c19` 根因结论**已推翻**。
- 全部 IoU、掩码占比、倍数、灰阶、扫参表、DLL 大小 / md5、日志快照 **未在 CPU `1.0.0.0` 重测**，也不进本文。

## 10. 归档映射（第 4A 批归档、第 4B 批引用）

| 归档件 | 本文引用的内容 |
|---|---|
| `docs/archive/c03-lumina-align-20261106.md` | 椭圆软边、5 点五官保护区、暗部不算皮肤、软膝证伪、立体感靠 clarity |
| `docs/archive/c05-robustness-20261106.md` | 丢帧保持 / 过曝保护 / 关键点校验三项机制 |
| `docs/archive/c12-face-region-20261106.md` | 五项归一化、祛斑痘拉回局部均值、法令纹像素空间旋转、三个真 bug |
| `docs/archive/c20-whitebalance-rootcause-20261106.md` | **最终根因**、旧硬判据失效、四条局限 |
| `docs/archive/c21-adaptive-skin-center-20261106.md` | `estimateSkinCenter()` 落地、三个肤色开关、EMA 破坏确定性、应急口径、三项遗留 |
| `docs/archive/ab-mask-20261106.md` | 「肤色 ∩ 人脸框」判据、已知弱点、`_ascii_path()` 环境坑 |
| `docs/archive/c19-camera-scale-ab-20261106.md` | **仅取其方法论**；根因结论已推翻，不得据此施工 |
| `docs/archive/c02-edge-gate-20261106.md` | §4 椭圆 mask 替代方案证伪 |
| `docs/archive/oss-survey-20261106.md` / `tech-roadmap-20261106.md` | §8.4 / §6「不做清单」取舍（**不取 GPU 化论证**） |

## 11. 待人工确认

1. 本文结论来自归档头登记 + 当前源码逐字复核，**未在 CPU `1.0.0.0` 上重跑真机对拍 / golden A/B**。
2. `c21` 三项遗留、`c20` 四条局限，以及 `c12` 三个真 bug 的修复是否在当前轴仍成立，需逐项复核。
3. `README.md` §8 第 4 项「祛斑痘 / 亮眼素材信号在噪声级」需按当前代码复核。
4. 文档维护人待指定。
5. §12 的人脸框时序平滑**未做真机遮挡复现**；迟滞分支未单独触发验证，默认开启是否带来拖影或新抖动，需补含遮挡的连续帧后才能判定。

## 12. 人脸框时序平滑与遮挡迟滞（1.0.0.2 · 2026-11-06 用户裁定）

本节登记一次**决策变更**：§7 原「不做人脸框 EMA」被撤销。触发原因不是新实测，
而是用户反馈「遮住半边脸时脸部遮罩闪烁」，并说明 GPU 版同样存在。归档
`c21-adaptive-skin-center-20261106.md` §3.1 把闪烁归因于「检测 faces 坐标抖」，
但同文档 §6 自标为个人推测、未做消融验证；本仓库**没有含遮挡的连续帧素材**，
因此本节只登记实现与边界，**不登记「已修复」结论**。

- **落点**：`01_源码/beauty_core.cpp` 的 `smoothFaceBoxes()`，在 `buildMaskInto()`
  里 detect 之后、画掩码与交出 `fboxOut` 之前调用。同步与异步 worker 共用这一个入口，
  两条路径同时生效；肤色掩码、五官保护区、`estimateSkinCenter()` 与五官局部五项
  拿到的是同一组框。
- **EMA**：按中心距离最近匹配历史框，对 `x/y/w/h` 与 5 个关键点做指数平滑，
  默认 `faceEma=0.35`。首帧或人数变化直接采纳，不从旧值爬。
- **遮挡迟滞**：新框面积比低于 0.65（或高于其倒数）、或 IoU 低于 0.30 时，
  最多沿用历史框 6 帧，超时强制采信新框。它与 `kMaskHold=6` 互补：
  后者处理「检测整次失败」，前者处理「检测成功但框跳变」。
- **线程约束**：状态是文件级静态量，沿用 `g_skinCb / g_skinCr` 的先例。
  `buildMaskInto` 在异步模式整段跑在唯一 worker 上、同步模式跑在渲染线程上，
  由 `asyncOn_` 互斥，不存在并发写；仍不碰任何类成员。
- **回退**：`BEAUTY_FACE_EMA=0 BEAUTY_FACE_HOLD=0` 时整段空转，逐字节回到 `1.0.0.1`。
  本地自检 `05_验证/goldens/masks/face_ema_ab_1002_20261106.md`（被 `.gitignore` 忽略、不入库）
  报告 8/8 逐字节一致、
  默认开启 7/8 帧输出不同、首帧相同，三项判据全过。**该自检只证明实现按设计运行。**
- **代价**：默认开启引入帧间状态，破坏逐字节确定性。此前所有 golden A/B 与性能基线
  在 `1.0.0.2` 上复现都必须加上述两个关闭开关，口径见 `docs/CHANGELOG.md` §2。
- **另案**：采集器画面旋转 −90° 后「参数拉不动、美白失效」是另一条路径，
  按用户约定本版不处理。

---

*本文与 `README.md` / `docs/INDEX.md` 冲突时，以 `01_源码/` 逐字内容为准；
任何「当前结论」类改动均须标注待人工确认，不得臆造。*
