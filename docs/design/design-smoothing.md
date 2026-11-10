# design · 磨皮：高低频分离与低频层路线

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.0` |
| 最后更新 | 2026-11-06 |
| 适用代码版本 | CPU 线 `1.0.0.0`（结论已在 `01_源码/` 逐字复核） |
| 维护人 | Jian |
| 状态 | `Active`（架构 / 开关有效；**历史轴实测数字未重测**） |
| 替代文档 | 归档 `docs/archive/c02-edge-gate-20261106.md`（`Deprecated`）、`c04-highlow-freq-20261106.md`、`c07-guided-filter-20261106.md`、`c08-lowfreq-compare-20261106.md`、`c15-box-lowpass-20261106.md` |

> **归档说明（2026-11-10）**：`docs/archive/` 下 38 篇历史原件保留并标注 `Deprecated`，
> 按同日清理裁定已移除来源段落；有效结论只在 Active 文档留存一份。

> **本文只保留结论 / 开关 / 坑 / 证伪 / 失效说明。**
> 按 2026-11-06 裁定，**完全不搬历史轴的数字表格**：扫参表、保留率、耗时、加速比、SHA256
> 一律不进当前版，仓库内无逐字出处。本文出现的数字**仅是源码中的开关取值 / 编译期默认值**，不是验收数据。
> 原归档件标 `Deprecated` 且「不得据此施工」；2026-11-10 重建于 `docs/archive/`，正文只在归档件留存。

---

## 1. 结论先行

当前 CPU `1.0.0.0` 的磨皮 = **全分辨率高低频分离 + 幅度门控 + 盒式迭代低通**，不上 GPU。

- `低 = lowpass(源)`、`高 = 源 − 低`；**幅度门控只压小幅度的高频**（毛孔 / 痘印），低频从不动。
  旧的「双边 + 线性混合」会把所有频段一起削弱 `t` 倍，强度一大就糊；源码 `freqMode=1` 已取代它。
- 低频层运行默认 `lowPath=3`（`beauty_core.cpp`），即**盒式迭代低通、不保边**；
  **保边只由幅度门控负责一次**。`BEAUTY_LOW_PATH` 可切回 0 / 1 / 2 三条双边路线做对照。
  ⚠️ `beauty_freq.h` 里的结构体字段 `lowPath` 默认是 0，与运行时配置默认值不是同一口径，不要混用。
- 幅度门控上限是配置字段 `freqMagHi`；对应的环境变量是 **`BEAUTY_FREQ_MAG`**（格式 `lo,hi`）。
  ⚠️ **不存在 `BEAUTY_FREQ_MAG_HI` 这个开关**——历史文档写 `freqMagHi` 时指的是变量/字段，不是环境变量名。
- **分离与合成必须留在全分辨率**（`c04` §7 的架构红线）；降采样方案已证伪，见 §3。
- 不上 GPU：`docs/archive/tech-roadmap-20261106.md`（`Deprecated`） §6「不做清单」第 1 条与当前纯 CPU 方向一致。
  该件头注的 `S1/S2/S3` 是技术线路的**步骤编号**，不是 `ab-*` 对拍文档编号，引用时勿混。

## 2. 架构不变量（`c04` §7，改动前必读）

- `低=lowpass` / `高=源−低` / 幅度门控只压小幅度，三条同时成立才叫「频率分离」。
- 分离与合成留在全分辨率是红线；一旦改成半分辨率，合成时的坐标与幅度都会变味。
- `c04` §7 登记了三处「悄悄变味」：换分辨率、换 ROI 边界、换低频实现都会让门控阈值失效，
  **每次改动必须重新标定**，不能沿用旧参数。
- `c04` §2 的三个实现选择（迭代代替放大半径、门控放在高频层、颗粒回填独立可关）仍在当前源码。

## 3. 已证伪路线与回退开关（别重试）

| 路线 | 结论 | 当前状态 |
|---|---|---|
| 引导滤波（`c07`） | 技术上消除了阶梯效应，但 **CPU 上不划算** | 默认关闭 `freqLowMode=0`（环境变量 `BEAUTY_LOW_MODE`）；`BEAUTY_GUIDE_R` / `BEAUTY_GUIDE_EPS` / `BeautyCoreSetGuide()` 保留可回退 |
| 盒式之外的路线 | 两条保留不删的理由见 `c08`：换更大半径核时可能才起作用；也是 ROI 局部浮点平面基础设施的唯一使用者 | — |
| 降采样 / 半分辨率磨皮（`ab-smooth`） | 曲线对不上，失败 | 不采纳；与 §2 全分辨率红线一致 |
| 引导滤波赢过双边（`ab-smooth`） | 未赢过 | 与 `c07` 结论一致 |
| 椭圆 mask 替代「肤色 ∩ 人脸框」（`c02` §4） | 不可行 | 见 `docs/design/design-face-mask.md` |

**指标口径的坑（`c08`）**：「小幅度高频保留%」这个指标本身不可靠，应用「脸颊台阶像素占比」替代；
`ab-smooth` 的曲线 RMSE 只是**曲线拟合**，不是结构同一性；`ab-metric` 的「ROI 全区域」读数受块均值稀释，
只能回答整体观感、不能回答核够不够强。详见 `docs/design/design-quality-findings.md`。

## 4. 边缘门控的三个坑（`c02` §2）

- **Sobel 标的是边缘线、不是区域**：拿它当「哪里该磨」的区域判据会把整片脸颊放过。
- **用 `|Laplacian|` 评价边缘保护会得到相反结论**：它是二阶差分，与「台阶被抹平」不是同一件事。

## 5. 盒式低通的调参顺序与坑（`c15`）

- 调强度的顺序：**先 `BEAUTY_BLUR_SAT`（档位饱和）、再 `BEAUTY_BOX_R`**；
  **`BEAUTY_BOX_R` 调大是「减弱」不是增强**——低通越糊、`|src−low|` 幅度越大，越容易被 `magHi` 门控拦住。
- **不要动 `freqMagHi` 去追强度**，那是把真边缘也一起放开。
- `c15` §3 三条反直觉结论与 §9 调参顺序、§6「ROI 版与全帧版差 1 灰阶」的对齐 bug 仍适用；
  具体数值见归档件 `docs/archive/c15-box-lowpass-20261106.md`（`Deprecated`）。
- 落地函数是 `boxRgbRoi()`（`beauty_smooth.cpp` / `beauty_smooth.h`），当前源码仍在。

## 6. 开关清单（均为 `01_源码/` 中实存名字）

- `BEAUTY_LOW_PATH`：低频路线切换（0/1/2/3，运行默认 3）。
- `BEAUTY_LOW_MODE`：引导滤波低频提取（默认 0=关）；配套 `BEAUTY_GUIDE_R`、`BEAUTY_GUIDE_EPS`。
- `BEAUTY_FREQ`：频率分离总开关；`BEAUTY_FREQ_ITERS`、`BEAUTY_FREQ_GRAIN`、`BEAUTY_FREQ_MAG`（`lo,hi`）。
- `BEAUTY_BOX_R`、`BEAUTY_BOX_ITERS`：盒式低通尺度。
- `BEAUTY_BLUR_SAT`：档位饱和（0=退回线性）。
- `BEAUTY_EDGE_K`：Sobel 边缘门控灵敏度。
- `BeautyCoreSetGuide()`：离线探针导出的引导滤波参数入口（在 `core_probe.cpp`，插件不调用）。

## 7. 失效说明（不得据此施工）

- 归档件全部是历史轴 `3.1.x / CoreEngine 0.x` 口径，**非当前 CPU `1.0.0.0`**。
- 全部毫秒数、加速比、百分比、保留率表、扫参表、SHA256、DLL 大小 **未在 CPU `1.0.0.0` 重测**，也不进本文。
- `c15` 头注的「真机未验收」状态已失效；`c09` / `c10` / `c12` 引用的 `D1` 步骤编号与 `ab-*` 文档编号同名异义。
- `ref_golden.dll` 只是 `05_验证/ref_driver/` 的离线基准 DLL（条件编译 `BEAUTY_WITH_LEGACY_ENGINE`），插件不编译。

## 8. 归档映射（第 4A 批归档、第 4B 批引用）

| 归档件 | 本文引用的内容 |
|---|---|
| `docs/archive/c02-edge-gate-20261106.md`（`Deprecated`） | §2 三个坑、§4 椭圆 mask 证伪、`BEAUTY_EDGE_K` |
| `docs/archive/c04-highlow-freq-20261106.md`（`Deprecated`） | §7 架构不变量与红线、§2 三个实现选择、低频/门控开关 |
| `docs/archive/c07-guided-filter-20261106.md`（`Deprecated`） | 引导滤波在 CPU 上不划算、默认关闭、回退开关 |
| `docs/archive/c08-lowfreq-compare-20261106.md`（`Deprecated`） | 两条低频路线证伪、指标口径坑、代码保留理由 |
| `docs/archive/c15-box-lowpass-20261106.md`（`Deprecated`） | 盒式低通落地、调参顺序、反直觉结论、ROI 对齐 bug |
| `docs/archive/ab-smooth-20261106.md`（`Deprecated`） | 降采样失败、引导滤波未赢过双边、曲线拟合 ≠ 结构同一性 |
| `docs/archive/tech-roadmap-20261106.md`（`Deprecated`） | §6「不上 GPU」结论；`S1/S2/S3` 命名陷阱 |

## 9. 待人工确认

1. 本文结论来自归档头登记 + 当前源码逐字复核，**未在 CPU `1.0.0.0` 上重跑 golden A/B 与性能 A/B**。
2. `c15` 的三条反直觉结论、`c02` 门控灵敏度是否在新轴上仍成立，需逐项复核。
3. `c21` 登记的高档位细纹理矫枉过正、阴影频带双尺度缺口是否仍存在，见 `docs/design/design-face-mask.md`。
4. ~~文档维护人待指定~~ ✅ 已指定：`Jian`（2026-11-09）。

---

*本文与 `README.md` / `docs/INDEX.md` 冲突时，以 `01_源码/` 逐字内容为准；
任何「当前结论」类改动均须标注待人工确认，不得臆造。*
