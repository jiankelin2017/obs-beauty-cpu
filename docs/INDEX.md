# docs/INDEX.md · 文档总表

| 字段 | 值 |
|---|---|
| 版本 | `1.0.13.12` |
| 最后更新 | 2026-11-10 |
| 适用代码版本 | CPU 线 `1.0.13.12`（提交见 git log） |
| 维护人 | Jian |
| 状态 | `Active`（1.0.13.12 修 D1/D2 源码缺陷（参数线程数据竞争 + ORT 返回值判空）、已重新编译打包；2026-11-09 精简批删分批记录与变更记录；同日治理批新建 `design-head-roll.md`、CHANGELOG §2 压至最近五版、补 `05_验证/INDEX.md`；**2026-11-10 按用户裁定重建 `docs/archive/`，38 篇历史原件逐字恢复并入库**） |
| 替代文档 | 无（新建） |

> **归档重建声明（2026-11-10）**：`docs/archive/` 下 38 篇历史原件已按 `MANIFEST.tsv` 逐字恢复，
> MD5 与字节数 38/38 一致，文首均保留「ARCHIVED · 已废弃，见 xxx」标注。它们全部标 `Deprecated`、
> **不得据此施工**；本仓库的当前有效结论只在 §1 的 Active 文档留存一份。
> 文中以 `docs/archive/` 开头的路径现在指向真实存在的归档件，读者可据此溯源，
> 但不得把归档件的路径、命名、参数当作现状引用。结论唯一去向索引见
> `docs/reference/reference-conclusions.md`；仓库外冷备保留于 `D:\插件\_整理_20261110\before\`。

> **本表是全库文档体系的唯一入口。** 查「哪篇是现状」看 §1；查历史原件的登记与替代指向看 §2；
> §3 是法务 / 隐私红线，**不属于待治理项**；§4 是维护约定与双闸门。

---

## 0. 规则速览

| 规则 | 内容 |
|---|---|
| 固定分类 | `README`（1）· `design`（每模块 1）· `guides`（每场景 1）· `reference`（每主题 1）· `CHANGELOG`（全局 1）· `adr`（一事一篇）· `archive`（隔离存放，不限；2026-11-10 重建） |
| 份数 | 主目录每类只留**当前版**；同一主题不允许两份并存；旧版一律进 `docs/archive/` |
| 目录 | `docs/{design,guides,reference,adr}` + `docs/archive/`；新文档只能放规定位置；`_quarantine\` 只收已废弃件且 `.gitignore` 排除 |
| 命名 | 主目录 `类型-主题.md`；归档 `主题-YYYYMMDD.md`；禁止 `final_v3_副本` 类命名 |
| 文档头 | 版本 · 最后更新 · 适用代码版本 · 维护人 · 状态（`Active` / `Deprecated`）· 替代文档 |
| 可信度 | 逐字源码 > 动态实测 > 推断 > 拟合 |
| 历史原件 | **隔离归档**（2026-11-10 裁定）：旧版移入 `docs/archive/`，按 `主题-YYYYMMDD.md` 命名，文首标「已废弃，见 xxx」并写清废弃原因；有效结论只留 §1 Active 文档一份 |
| 当前版数字 | **历史轴数字表格不进当前版**；允许源码开关取值 / 编译期常量与注明时效的当前轴内部取证数字，后者不得作为验收依据；历史轴逐字表格见 `docs/archive/` |
| 自动校验 | 提交前**双闸门**：`05_验证/check_docs.py --staged`（文档一致性九条断言）+ `05_验证/check_upload.py --staged`（合规四道断言）；两条都要过 |

**治理范围（结构化清单，2026-11-10 实测）**：

```text
ACTIVE  = README.md + docs/CHANGELOG.md + docs/INDEX.md + docs/{design,guides,reference,adr}/*.md   # 13 篇：受文档头 / INDEX 双向 / 断链 / 命名 / 版本轴等断言约束
ARCHIVE = docs/archive/*.md（38 篇，全部 Deprecated，文首有 ARCHIVED 标注）                       # 受第 2 / 3 / 5 条断言约束
VERIFY  = 05_验证/*.md（顶层 23 篇；递归共 88 篇）                                                      # 其路径引用受第 8 条零断链校验
OUTSIDE = 05_验证/goldens/ · 参考文件/ · _quarantine/ · 仓库外报告                                       # 不受 Active 头表约束
```
本清单只固化边界，本轮未接入断言（第 3 条只查 `docs/` 目录，第 8 条只查 `05_验证/` 引用）。

**统一文档头模板**（新建当前版时复制；字段缺失会被 `check_docs.py` 的 [1] 拦下）：

```markdown
| 字段 | 值 |
|---|---|
| 版本 | `1.0.3.0` |
| 最后更新 | YYYY-MM-DD |
| 适用代码版本 | CPU 线 `1.0.1.0` |
| 维护人 | 待人工确认 |
| 状态 | `Active` |
| 替代文档 | 无（新建）／本文被取代时，结论并入唯一 Active 文档，原件移入 `docs/archive/` |
```

模板只管文档头。正文结构按类型约定：design 需有「结论先行 / 开关 / 坑 / 证伪 / 失效说明 / 唯一去向 / 待人工确认」；
guides 需有可执行步骤与已知偏差；reference 只登记逐字可核对事实，不裁定许可。

---

## 1. 当前版登记（Active）

| 主题 | 路径 | 类型 | 状态 | 适用版本 | 维护人 | 最后核对 | 替代/归档 |
|---|---|---|---|---|---|---|---|
| 项目总入口（唯一 README） | `README.md` | README | `Active` | CPU `1.0.13.12` | Jian | 2026-11-10 | 替代 `docs/archive/readme-archive-20261106.md`、`docs/archive/readme-entry-20261106.md`（均 `Deprecated`） |
| 变更日志（全局唯一） | `docs/CHANGELOG.md` | CHANGELOG | `Active`（**§2 只留最近五版**） | CPU `1.0.13.12` | Jian | 2026-11-10 | 替代 `docs/archive/changelog-raw-20261106.md`；`1.0.13.7` 及更早原文 → `docs/archive/changelog-history-20261109.md`（均 `Deprecated`） |
| CPU 性能优化设计依据 | `docs/design/design-cpu-performance.md` | design | `Active`（架构 / 开关有效；历史轴数字未重测） | CPU `1.0.13.0` | Jian | 2026-11-09 | 重写前全文见 `docs/archive/c1-cpu-performance-20261106.md`；第 4B 批并入 `docs/archive/c10-async-detect-20261106.md`（§8）；单独清理批整篇重写、§8 编号不变 |
| 磨皮：高低频分离与低频层路线 | `docs/design/design-smoothing.md` | design | `Active`（数字未重测） | CPU `1.0.0.0` | Jian | 2026-11-06 | 第 4B 批新建；归并且替代 `c02` / `c04` / `c07` / `c08` / `c15` 五篇归档件（见 §2） |
| 色调、clarity 与锐化 | `docs/design/design-tone-detail.md` | design | `Active`（数字未重测） | CPU `1.0.2.0` | Jian | 2026-11-08 | 第 4B 批新建；归并 `c06` / `c09` / `c11`，引用 `c03` 与 `oss-survey` §8.4；`1.0.2.0` 补 §1.1「色调三段整帧施加」 |
| 肤色掩码、人脸框与五官局部 | `docs/design/design-face-mask.md` | design | `Active`（数字未重测） | CPU `1.0.3.0` | Jian | 2026-11-09 | 第 4B 批新建；归并 `c03` / `c05` / `c12` / `c20` / `c21`，引用 `ab-mask` / `c02` / `c19`；**2026-11-09 把原 §13–§15（旋转源 / 头歪 / 脖子方向）拆至 `docs/design/design-head-roll.md`**，本文只留肤色掩码与五官局部 |
| 画质对拍结论与证伪链 | `docs/design/design-quality-findings.md` | design | `Active`（**全部为历史轴结论，当前轴未重测**） | CPU `1.0.0.2` | Jian | 2026-11-06 | 第 4B 批新建；归并 `c14` / `c16` / `c17` / `c18` / `c19`，引用 `ab-metric` / `ab-smooth` / `c20` / `c21`（见 §2） |
| 头歪与旋转源：方向 / 倾斜 / 脖子 / roll 锁定 | `docs/design/design-head-roll.md` | design | `Active`（判据有效；定量只在取证文件） | CPU `1.0.13.10` | Jian | 2026-11-09 | **2026-11-09 新建**：吸收 `design-face-mask.md` 原 §13–§15，并补 `1.0.13.7`–`1.0.13.9` 的 roll 释放链（原只在 `docs/CHANGELOG.md` §2）；取证见 `05_验证/ab20261109_head_roll.md` 等 |
| 安装包构建与打包 | `docs/guides/guide-build-installer.md` | guides | `Active`（偏差见 §6） | CPU `1.0.13.12` | Jian | 2026-11-10 | 原 `06_安装包\README_打包说明.md`；验收原件 `docs/archive/acceptance-installer-20261106.md`（`Deprecated`） |
| 顶层菜单与参数面板（UI） | `docs/guides/guide-ui.md` | guides | `Active` | CPU `1.0.13.12` | Jian | 2026-11-10 | 原 `04_文档\顶层菜单插件说明.md`（已隔离）；未采用的 HTML+websocket 方案见 `docs/archive/ui-html-websocket-proposal-20261106.md`（`Deprecated`） |
| 许可与第三方组件口径 | `docs/reference/reference-licensing.md` | reference | `Active`（**口径冲突待人工确认，不含许可结论**） | CPU `1.0.13.12` | Jian | 2026-11-10 | 已合并 `docs/archive/opensource-boundary-20261106.md` 许可部分、`docs/archive/oss-survey-20261106.md` §4（均 `Deprecated`） |
| 文档总表 | `docs/INDEX.md` | INDEX | `Active`（2026-11-10：重建 `docs/archive/` 38 行归档登记） | CPU `1.0.13.12` | Jian | 2026-11-10 | 分批过程 → `docs/archive/index-batchlog-20261109.md`（`Deprecated`） |
| 历史结论唯一留存索引 | `docs/reference/reference-conclusions.md` | reference | `Active` | CPU `1.0.13.12` | Jian | 2026-11-10 | 索引 `docs/archive/` 38 篇的有效结论去向；归档件本体见 §2 |

**当前版合计 13 篇**（README 1 · CHANGELOG 1 · design 6 · guides 2 · reference 2 · INDEX 1）。
> 「适用版本」列记录的是**该文档最后一次内容复核时**的 CPU 轴版本，不是本表头的版本。
> 2026-11-09 精简批复核并改动了 5 篇：`README`、`CHANGELOG`、`guide-ui`、`reference-licensing`、`INDEX`；
> 同日「文档治理」批新建 `design-head-roll.md`（内容取自 `design-face-mask.md` 原 §13–§15 与 CHANGELOG 的 roll 链，
> **逐条对照源码复核过开关名与常量**），并把 `CHANGELOG` §2 压到最近五版（`1.0.13.8` ~ `1.0.13.12`）。
> 2026-11-10 归档重建批只改「替代/归档」列的归档指向，**未改任何技术结论、适用版本与最后核对日期**。
> 现状：§1 共 6 篇 `design` 取证快照登记在 `INDEX_AXIS_EXEMPT`，按上行定义记「最后一次内容复核版本」；
> 这 6 行不得读作「已按当前版复核」，差异由第 9 条例外表承载。
**预留空类**：仅剩 `docs/adr/`（暂无一事一篇的决策记录），以 `.gitkeep` 占位，写入正式文档时删占位即可。
`docs/reference/` 已于第 3 批落地 `docs/reference/reference-licensing.md`，对应 `.gitkeep` 已删除。

---

## 2. 归档登记（Deprecated · 38 篇）

**结论先行**：`docs/archive/` 已于 2026-11-10 按用户裁定重建，38 篇历史原件逐字恢复并纳入版本库。
恢复源为仓库外冷备 `D:\插件\_整理_20261110\before\docs\archive\`，`MANIFEST.tsv` 记录的 MD5 与字节数
经复算 **38/38 一致、0 缺失**。每篇文首保留「ARCHIVED · 已废弃，见 xxx」标注，状态一律 `Deprecated`、
**不得据此施工**；有效结论（含正向与负向／证伪结论）只在 §1 的 Active 文档留存一份，
小节级去向索引见 `docs/reference/reference-conclusions.md`。

| 主题 | 路径 | 类型 | 状态 | 适用版本 | 维护人 | 最后核对 | 替代/归档 |
|---|---|---|---|---|---|---|---|
| 掩码 AB 取证 | `docs/archive/ab-mask-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `README.md` §8、`docs/design/design-face-mask.md` |
| 指标 AB 取证 | `docs/archive/ab-metric-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `README.md` §8、`docs/design/design-quality-findings.md` |
| 磨皮 AB 取证 | `docs/archive/ab-smooth-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-quality-findings.md` |
| 工程 / UI 12 项验收 | `docs/archive/acceptance-engineering-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.39` | Jian | 2026-11-10 | `docs/CHANGELOG.md`；**12 项判定表未在 Active 文档定位，待人工确认** |
| 装机验收 | `docs/archive/acceptance-installer-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/guides/guide-build-installer.md` |
| 画质验收 | `docs/archive/acceptance-quality-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/CHANGELOG.md`、`README.md` §8 |
| 边缘门控 | `docs/archive/c02-edge-gate-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-smoothing.md` |
| 亮度对齐 | `docs/archive/c03-lumina-align-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-face-mask.md` |
| 高低频分离 | `docs/archive/c04-highlow-freq-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-smoothing.md` |
| 鲁棒性三项 | `docs/archive/c05-robustness-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-face-mask.md` |
| 美白与红润 | `docs/archive/c06-whiten-ruddy-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-tone-detail.md` |
| 导向滤波 | `docs/archive/c07-guided-filter-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-smoothing.md` |
| 低频对比 | `docs/archive/c08-lowfreq-compare-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-smoothing.md` |
| clarity | `docs/archive/c09-clarity-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-tone-detail.md` |
| CPU 性能设计（历史轴） | `docs/archive/c1-cpu-performance-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-cpu-performance.md` |
| 异步检测 | `docs/archive/c10-async-detect-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-cpu-performance.md` §8 |
| 锐化 | `docs/archive/c11-sharpen-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-tone-detail.md` |
| 人脸区域 | `docs/archive/c12-face-region-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-face-mask.md` |
| 画质差距 | `docs/archive/c14-quality-gap-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-quality-findings.md` |
| 盒式低通 | `docs/archive/c15-box-lowpass-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-smoothing.md` |
| 斑点样本 | `docs/archive/c16-spot-samples-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-quality-findings.md` |
| 参数扫描证伪 | `docs/archive/c17-param-sweep-falsify-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-quality-findings.md` |
| 尺度依赖 | `docs/archive/c18-scale-dependency-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-quality-findings.md` |
| 相机尺度 AB | `docs/archive/c19-camera-scale-ab-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-quality-findings.md`（只取方法论） |
| 白平衡根因 | `docs/archive/c20-whitebalance-rootcause-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-face-mask.md` |
| 自适应肤色中心 | `docs/archive/c21-adaptive-skin-center-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/design/design-face-mask.md` |
| CHANGELOG 历史轴全文 | `docs/archive/changelog-history-20261109.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/CHANGELOG.md` |
| 性能变更流水 | `docs/archive/changelog-perf-20261109.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/CHANGELOG.md` |
| 逐提交流水账 | `docs/archive/changelog-raw-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/CHANGELOG.md` |
| GPU 移植计划（未采用） | `docs/archive/gpu-porting-plan-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `README.md` §1、§3 |
| 分批治理过程记录 | `docs/archive/index-batchlog-20261109.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/INDEX.md` |
| 开源边界 | `docs/archive/opensource-boundary-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/reference/reference-licensing.md` |
| 开源调研 | `docs/archive/oss-survey-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/reference/reference-licensing.md` §4 |
| 结项归档版 README | `docs/archive/readme-archive-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `README.md` |
| 旧仓库入口说明 | `docs/archive/readme-entry-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `README.md` |
| 评分卡 | `docs/archive/scorecard-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `README.md` §8 |
| 技术路线图 | `docs/archive/tech-roadmap-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `README.md` §0、§3 |
| HTML+websocket UI 提案（未采用） | `docs/archive/ui-html-websocket-proposal-20261106.md` | archive | `Deprecated` | 历史轴 | Jian | 2026-11-10 | `docs/guides/guide-ui.md` |

**本节登记 38 行**，与 `docs/archive/` 实际文件一一对应；`check_docs.py` 第 3 条断言据此做双向登记校验。

---

## 3. 明确不纳入治理（法务 / 隐私红线）

以下内容**不移动、不登记、不入库**，`docs/` 体系对它们不成立：

- `.gitignore` §10 排除的 `04_文档\` 下 **5 篇**含参考实现内部细节的文档（`.gitignore:182–186`）：
  `01_第三方磨皮真值.md`、`C13_装机链路.md`、`C23_磨皮照抄施工图.md`、`一级入口说明.md`、`美颜子功能开发指南.md`；
  以及 `参考文件\README.md`——仅本机查证用，**不移动、不归档、不登记为 `Pending`**。
- `参考文件\` 全部子目录：闭源商业 SDK、参考分析、原始 `.raw` 帧数据、OBS 源码树（无再分发权 / 含真人面部数据）。
- `05_验证\` 下的真人面部位图、`.raw` 帧、加密 bundle、构建产物与可再生日志。
- `.gitignore` 是**唯一排除闸门**；新增文件默认会被上传，先加规则再 `git add`。提交前跑 `python 05_验证\check_upload.py --staged`。

> **与 §2 的边界（2026-11-10 裁定）**：`docs/archive/` 38 篇**不在**本节排除清单内，已按用户裁定纳入版本库。
> 它们与 `04_文档\` 5 篇的区别是：前者是本仓库自产的历史文档，后者含第三方商业 SDK 的参考实现内部细节。
> 若后续要把归档件改为「仅本机留存」，须先改 `.gitignore` 并同步本表，不能只删文件。

---

## 4. 维护约定（简版）

1. **新增文档**：先在本表查同主题是否已有 `Active` 条目 → 有则改那一篇，不新建；无则按 `类型-主题.md` 落在规定目录，补统一文档头，并**同一次提交**里更新本表。
2. **版本变更**：改 `beauty_params.h` 后，同步根 `README.md` §0、`docs/CHANGELOG.md` §1，以及本表所有条目的「适用版本 / 最后核对」列。
3. **历史原件处置**：`Active` 文档被取代时，结论并入新的唯一 Active 文档，原件按 `主题-YYYYMMDD.md` 移入 `docs/archive/`，文首补「已废弃，见 xxx」与废弃原因，并在 §2 增加一行登记；移入前逐字冷备到仓库外、登记 MD5。删除原件前须跑双闸门确认 0 断链。
4. **状态变更**：§1 条目被取代时状态改 `Deprecated` 并移入 §2；§2 归档件不回退为 `Active`，也不在主目录留副本。
5. **提交前**：`python 05_验证\check_upload.py --staged` 过闸门；确认没有把 §3 的文件加回索引。
6. **当前版不搬历史轴数字**：当前版允许出现源码开关取值 / 编译期常量，以及注明时效的当前轴内部取证数字（见 `docs/design/design-cpu-performance.md` §2.5–§2.11），后者不得用于对外宣称或作为当前验收依据；历史轴逐字表格只留在 `docs/archive/`。
7. **提交前双闸门**：先跑 `python 05_验证\check_docs.py --staged`（文档一致性），
   再跑 `python 05_验证\check_upload.py --staged`（合规）。前者管文档头六字段、INDEX 双向登记、
   `docs/` 断链、命名规范、当前版数字表格告警，`0.2.0` 新增的版本轴一致性
   与 `05_验证/` 引用零断链，以及 `0.3.0` 新增的总表「适用版本」列一致性；后者管索引残留 / 法务 / 隐私 / 体积。
   **两条都要过，缺一不提交**；`check_docs.py` 只读、纯标准库、失败退出码 1。
8. **提交前三步**（`0.3.0` 起）：① 跑全量 `python 05_验证\check_docs.py`；② 确认工作区与暂存区
   一致（`git diff --name-only` 为空，或对所有改动文件重新 `git add`）；③ 再跑 `--staged` 双闸门。
   理由：`check_docs.py --staged` 的断言读工作区磁盘，`check_upload.py --staged` 读 git 索引；
   两者分叉时合规闸门验的是改前内容。`check_docs.py --staged` 会打印分叉清单，只告警、不阻断。
9. **例外登记模板**（`0.3.0` 起）：新增 `VERSION_AXIS_EXEMPT` / `VERIFY_ARCHIVE_EXEMPT` /
   `INDEX_AXIS_EXEMPT` 条目时，理由须写明「登记日期 / 复核期限」以及为何不能当场修复；
   `[待跟进]` 不得无限期挂账，版本变更时逐条复核能否关闭。现有 6 条历史条目（版本轴 6；
   总表例外由版本轴子集派生）未记录原始登记日期，本轮不臆造回填。

> 治理输出第 6 项「防腐化机制」初版为 `05_验证/check_docs.py`（`0.1.0`，现为 `0.3.1.1`）与本节第 7 条双闸门，
> 模板与规则固化在 §0。**未引入 git hook / CI**（不改变提交行为）；
> 若以后公开仓库或多人协作需要强制拦截，再单独确认后升级为 `pre-commit` / GitHub Actions。
> 新增脚本的 `0.1.0` 是脚本自身起始版本，**该批时 CPU 产品版本轴仍 `1.0.0.0`**（现已递增至 `1.0.13.12`），两者互不牵动。
> `0.3.1.1`（2026-11-10）只改注释与文档描述以适配归档目录回归，**断言逻辑未变**，按四段式规则升构建位。

---

*本表与 `README.md` 冲突时，以逐字源码 > 动态实测 > 本表 > 归档件 > 唯一留存索引为准；
任何「当前结论」类改动均须标注待人工确认项，不得臆造。*
