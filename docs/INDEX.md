# docs/INDEX.md · 文档总表

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.0` |
| 最后更新 | 2026-11-06 |
| 适用代码版本 | CPU 线 `1.0.0.0`（提交 `5323856`） |
| 维护人 | 待人工确认 |
| 状态 | `Active`（**第 3 批已登记，§3 仍有 19 篇未治理**） |
| 替代文档 | 无（新建） |

> **本表是全库文档体系的唯一入口。** 查「哪篇是现状」先看 §1；查历史原件看 §2；
> §3 明确列出仍未治理的部分，**不要误以为全库已治理完成**。

---

## 0. 规则速览

| 规则 | 内容 |
|---|---|
| 固定分类 | `README`（1）· `design`（每模块 1）· `guides`（每场景 1）· `reference`（每主题 1）· `CHANGELOG`（全局 1）· `adr`（一事一篇）· `archive`（隔离存放，不限） |
| 份数 | 主目录每类只留**当前版**；同一主题不允许两份并存；旧版一律进 `docs/archive/` |
| 目录 | `docs/{design,guides,reference,adr}` + `docs/archive/`；新文档只能放规定位置；`04_文档\` 只减不增 |
| 命名 | 主目录 `类型-主题.md`；归档件 `主题-YYYYMMDD.md`；禁止 `final_v3_副本` 类命名 |
| 文档头 | 版本 · 最后更新 · 适用代码版本 · 维护人 · 状态（`Active` / `Deprecated`）· 替代文档 |
| 可信度 | 逐字源码 > 动态实测 > 推断 > 拟合 |
| 归档件 | 文首必须标「已废弃，见 xxx」+ 废弃原因；正文不改写、不删减；**不得据此施工** |

---

## 1. 当前版登记（Active）

| 主题 | 路径 | 类型 | 状态 | 适用版本 | 维护人 | 最后核对 | 替代/归档 |
|---|---|---|---|---|---|---|---|
| 项目总入口（唯一 README） | `README.md` | README | `Active` | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 替代 `docs/archive/readme-archive-20261106.md`、`docs/archive/readme-entry-20261106.md` |
| 变更日志（全局唯一） | `docs/CHANGELOG.md` | CHANGELOG | `Active` | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 替代 `docs/archive/changelog-raw-20261106.md` |
| CPU 性能优化设计依据 | `docs/design/design-cpu-performance.md` | design | `Active`（数字待重测） | CPU `1.0.0.0`；文内数字测于历史轴 `3.1.x` | 待人工确认 | 2026-11-06 | 原 `04_文档\C1_CPU性能优化.md`；§7 断链已于第 3 批纠正 |
| 安装包构建与打包 | `docs/guides/guide-build-installer.md` | guides | `Active`（偏差见 §6） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 原 `06_安装包\README_打包说明.md`；验收原件 `docs/archive/acceptance-installer-20261106.md` |
| 顶层菜单与参数面板（UI） | `docs/guides/guide-ui.md` | guides | `Active`（装机状态待人工确认） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 原 `04_文档\顶层菜单插件说明.md`；未采用的 HTML+websocket 方案见 `docs/archive/ui-html-websocket-proposal-20261106.md` |
| 许可与第三方组件口径 | `docs/reference/reference-licensing.md` | reference | `Active`（**口径冲突待人工确认，不含许可结论**） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 已合并 `docs/archive/opensource-boundary-20261106.md` 许可部分、`docs/archive/oss-survey-20261106.md` §4 |
| 文档总表 | `docs/INDEX.md` | INDEX | `Active`（第 3 批） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 无 |

**预留空类**：仅剩 `docs/adr/`（暂无一事一篇的决策记录），以 `.gitkeep` 占位，写入正式文档时删占位即可。
`docs/reference/` 已于第 3 批落地 `docs/reference/reference-licensing.md`，对应 `.gitkeep` 已删除。

---

## 2. 归档登记（Deprecated · 只读，不得据此施工）

| 主题 | 路径 | 类型 | 状态 | 适用版本 | 维护人 | 最后核对 | 替代/归档 |
|---|---|---|---|---|---|---|---|
| 结项归档版总文档（910 行全文保全） | `docs/archive/readme-archive-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.39 / 3.1.40 / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` |
| 旧仓库入口说明（差异点已合并） | `docs/archive/readme-entry-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.39 / 3.1.40 / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md`；其 §1 许可声明是 `docs/reference/reference-licensing.md` §2 的冲突口径 B |
| 工程 / UI 12 项验收（3.1.39） | `docs/archive/acceptance-engineering-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.39 / core 1.4.0` | 待人工确认 | 2026-11-06 | 见 `docs/CHANGELOG.md` |
| 安装包装/卸 40 项验收（3.1.39） | `docs/archive/acceptance-installer-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.39` | 待人工确认 | 2026-11-06 | 见 `docs/guides/guide-build-installer.md` |
| 逐提交流水账（2532 行全文保全） | `docs/archive/changelog-raw-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `docs/CHANGELOG.md` |
| GPU 移植开发计划（与纯 CPU 方向冲突） | `docs/archive/gpu-porting-plan-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.39 / core 1.4.0` | 待人工确认 | 2026-11-06 | 见 `README.md` §0、§1、§3；该计划从未开工 |
| 未采用的 HTML + obs-websocket 面板方案 | `docs/archive/ui-html-websocket-proposal-20261106.md` | archive | `Deprecated` | 历史轴（第三方 SDK 对接时期） | 待人工确认 | 2026-11-06 | 见 `docs/guides/guide-ui.md`；引用脚本与路径全部不存在 |
| 开源可商用方案边界（含被推翻结论） | `docs/archive/opensource-boundary-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §6；许可判据 / 选型表差异点**已于第 3 批并入** `docs/reference/reference-licensing.md` |
| 工程 / 画质 11 项验收（3.1.34） | `docs/archive/acceptance-quality-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.34 / core 1.4.0` | 待人工确认 | 2026-11-06 | 见 `docs/CHANGELOG.md`、`README.md` §8 第 3 项（数字待重测） |
| 复刻评分（3.1.39，79.0 / 70.2 分） | `docs/archive/scorecard-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.39 / core 1.4.0` | 待人工确认 | 2026-11-06 | 见 `README.md` §8 第 3 项；历史分数口径**不另立当前版**，原件只读保全 |
| 开源参考仓库对照与可复用清单 | `docs/archive/oss-survey-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `docs/reference/reference-licensing.md`（许可部分）；§7 / §8 差异点待第 4 批并入 `docs/design/design-*.md` |
| 自研技术线路 D1（含「不上 GPU」结论） | `docs/archive/tech-roadmap-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §0、§3；证伪结论待第 4 批引用；头内登记 `S1/S2/S3` 命名陷阱 |
| 掩码对拍结论（原 `S1`） | `docs/archive/ab-mask-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §8 第 3 项；口径差异点待第 4 批引用 |
| 磨皮核对拍结论（原 `S2`） | `docs/archive/ab-smooth-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §8 第 3 项；**证伪结论必须保留**，待第 4 批引用 |
| 对拍口径修正结论（原 `S3`） | `docs/archive/ab-metric-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §8 第 3 项；口径结论待第 4 批引用 |

> 归档件的**正文一字未改**，仅在文首追加废弃标注块。历史评分口径、版本演进史、20 条雷区、许可明细出处均可在此查证。
> 第 2 批 `opensource-boundary` 的许可差异点已在第 3 批并入 `docs/reference/reference-licensing.md`；
> `scorecard` 的评分公式与历史分数口径经 2026-11-06 裁定**不抽成当前版、不长期保留**。
> 第 3 批新增 5 篇全部为历史轴 `3.1.x / core 1.4.x` 口径：其中 `oss-survey` 头登记了待第 4 批引用的
> 算法差异点，`tech-roadmap` / `ab-mask` / `ab-smooth` / `ab-metric` 头登记了**证伪类结论**与
> `S1/S2/S3` 同名异义陷阱（对拍文档编号 ≠ 技术线路步骤编号），第 4 批归并 C 系列时须从这些头引用。

---

## 3. 待治理登记（Pending · 分批推进）

- **第 2 批已处理 6 篇**：`方案A_GPU移植开发计划.md`、`面板使用说明.md`、`方案边界调整_开源可商用.md`、
  `验收报告_v3.1.34.md`、`复刻评分_v3.1.39.md` → `docs/archive/`（5 篇 `Deprecated`）；
  `顶层菜单插件说明.md` → `docs/guides/guide-ui.md`（1 篇 `Active`）。
- **第 3 批已处理 5 篇 + 新建 1 篇**：`开源参考仓库_对照与可复用清单.md`、`D1_我们自己的技术线路.md`、
  `S1_掩码对拍结论.md`、`S2_磨皮核对拍结论.md`、`S3_对拍口径修正_结论.md` → `docs/archive/`
  （5 篇 `Deprecated`，按 B 方案**不另建 roadmap 当前版**，证伪结论留在归档头供第 4 批引用）；
  新建 `docs/reference/reference-licensing.md`（1 篇 `Active`），并联动修正
  `docs/design/design-cpu-performance.md` §7 的归档后断链。

`04_文档\` 现剩 **24 篇** `.md` = **19 篇 tracked（待治理）** + **5 篇 `.gitignore` §10 排除（不纳入治理）**。
tracked 部分全部为历史轴 `3.1.x / core 1.4.x` 口径，**不得当作当前结论**。
剩余分组的基底与合并差异点仍须**逐批列清单确认后再动**：

| 组 | 代表文件（篇数） | 初步方向 | 状态 / 批次 |
|---|---|---|---|
| 磨皮 / 画质技术细节 C 系列 | `C2`~`C12`、`C14`~`C21`（**19 篇**） | 按模块择基底归并为 `docs/design/design-*.md` 4~5 份，其余归档；**必须保留 `C7` / `C8` / `C17` 的证伪类结论**，并引用第 3 批 5 篇归档头登记的差异点 / 证伪结论；标「历史轴实测，CPU `1.0.0.0` 未复核」 | `Pending` · 第 4 批 |
| 仅本机保留 | `04_文档\` 下被 `.gitignore` §10 排除的 **5 篇**，文件名见 §4 | 不移动、不登记、不入库 | `Excluded` |

> **归类修正（2026-11-06）**：首批曾把 `一级入口说明.md` 误列为「旧入口 / `Pending`」。
> 核查 `.gitignore:184` 后确认它属于 §4 的 `Excluded`（含参考实现内部细节，仅本机查证），
> **不纳入治理、不归档、不移动**；原「归档并保留菜单链路差异点」的初步方向作废。

> 与 2026-11-06 诊断的「82 篇自研文档 / 8 个真实主题组」口径一致；本表只登记已落地项与剩余分组，
> 逐篇清单仍以当时输出的全量表为准。

---

## 4. 明确不纳入治理（法务 / 隐私红线）

以下内容**不移动、不登记、不入库**，`docs/` 体系对它们不成立：

- `.gitignore` §10 排除的 `04_文档\` 下 **5 篇**含参考实现内部细节的文档（`.gitignore:182–186`）：
  `01_第三方磨皮真值.md`、`C13_装机链路.md`、`C23_磨皮照抄施工图.md`、`一级入口说明.md`、`美颜子功能开发指南.md`；
  以及 `参考文件\README.md`——仅本机查证用，**不移动、不归档、不登记为 `Pending`**。
- `参考文件\` 全部子目录：闭源商业 SDK、参考分析、原始 `.raw` 帧数据、OBS 源码树（无再分发权 / 含真人面部数据）。
- `05_验证\` 下的真人面部位图、`.raw` 帧、加密 bundle、构建产物与可再生日志。
- `.gitignore` 是**唯一排除闸门**；新增文件默认会被上传，先加规则再 `git add`。提交前跑 `python 05_验证\check_upload.py --staged`。

---

## 5. 维护约定（简版）

1. **新增文档**：先在本表查同主题是否已有 `Active` 条目 → 有则改那一篇，不新建；无则按 `类型-主题.md` 落在规定目录，补统一文档头，并**同一次提交**里更新本表。
2. **版本变更**：改 `beauty_params.h` 后，同步根 `README.md` §0、`docs/CHANGELOG.md` §1，以及本表所有条目的「适用版本 / 最后核对」列。
3. **归档动作**：用 `git mv` 保留历史（可逆），按 `主题-YYYYMMDD.md` 命名，文首加废弃标注；**禁止直接删除原件**。
4. **状态变更**：`Active → Deprecated` 必须同时写清「见 xxx」，不允许出现无替代文档的孤儿归档。
5. **提交前**：`python 05_验证\check_upload.py --staged` 过闸门；确认没有把 §4 的文件加回索引。

> 完整的防腐化机制建议（模板文件、元数据规范、PR 联动检查、定期巡检规则）属治理输出第 6 项，
> **待 §3 全部分批完成后单独给出**，本表不代替。

---

## 6. 总表变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-06 | 建立 `docs/` 目录与 `docs/INDEX.md`；首批登记 5 篇 `Active`、5 篇 `Deprecated`；`04_文档\` 余 35 篇标 `Pending`；法务排除项标 `Excluded` |
| 2026-11-06 | 第 2 批：登记新增 1 篇 `Active`（`docs/guides/guide-ui.md`）、5 篇 `Deprecated`；`04_文档\` 35 → 29 篇（24 tracked + 5 Excluded）；修正 `一级入口说明.md` 的 `Pending` → `Excluded` 误归类；登记第 3 / 4 批方向与待合并差异点 |
| 2026-11-06 | 第 3 批（B 方案）：新增 `docs/reference/reference-licensing.md`（1 篇 `Active`）并删 `docs/reference/.gitkeep`；登记 5 篇 `Deprecated`（`oss-survey` / `tech-roadmap` / `ab-*`）；`04_文档\` 29 → 24 篇（19 tracked + 5 Excluded）；关闭第 3 批两个 `Pending` 组；联动修 `design-cpu-performance.md` §7 断链 |

---

*本表与 `README.md` 冲突时，以逐字源码 > 动态实测 > 本表 > 归档件为准；
任何「当前结论」类改动均须标注待人工确认项，不得臆造。*
