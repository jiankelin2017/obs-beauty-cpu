# docs/INDEX.md · 文档总表

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.1` |
| 最后更新 | 2026-11-06 |
| 适用代码版本 | CPU 线 `1.0.0.1`（立轴提交 `5323856`） |
| 维护人 | 待人工确认 |
| 状态 | `Active`（**第 4 批已完成；`04_文档/` tracked 待治理清零；第 6 项防腐化哨兵已落地；单独清理批已收口历史数字**） |
| 替代文档 | 无（新建） |

> **本表是全库文档体系的唯一入口。** 查「哪篇是现状」看 §1；查历史原件看 §2；
> §3 记录分批治理结果；§4 是法务 / 隐私红线，**不属于待治理项**。

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
| 当前版数字 | 第 4 批起只保留结论 / 开关 / 坑 / 证伪 / 失效说明；**历史轴数字表格不进当前版**，只在归档件查 |
| 自动校验 | 提交前**双闸门**：`05_验证/check_docs.py --staged`（文档一致性六条断言）+ `05_验证/check_upload.py --staged`（合规四道断言）；两条都要过 |

**统一文档头模板**（新建当前版时复制；字段缺失会被 `check_docs.py` 的 [1] 拦下）：

```markdown
| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.0` |
| 最后更新 | YYYY-MM-DD |
| 适用代码版本 | CPU 线 `1.0.0.1` |
| 维护人 | 待人工确认 |
| 状态 | `Active` |
| 替代文档 | 无（新建）／按 `主题-YYYYMMDD.md` 归档后填归档件路径 |
```

模板只管文档头。正文结构按类型约定：design 需有「结论先行 / 开关 / 坑 / 证伪 / 失效说明 / 归档映射 / 待人工确认」；
guides 需有可执行步骤与已知偏差；reference 只登记逐字可核对事实，不裁定许可。

---

## 1. 当前版登记（Active）

| 主题 | 路径 | 类型 | 状态 | 适用版本 | 维护人 | 最后核对 | 替代/归档 |
|---|---|---|---|---|---|---|---|
| 项目总入口（唯一 README） | `README.md` | README | `Active` | CPU `1.0.0.1` | 待人工确认 | 2026-11-06 | 替代 `docs/archive/readme-archive-20261106.md`、`docs/archive/readme-entry-20261106.md` |
| 变更日志（全局唯一） | `docs/CHANGELOG.md` | CHANGELOG | `Active` | CPU `1.0.0.1` | 待人工确认 | 2026-11-06 | 替代 `docs/archive/changelog-raw-20261106.md` |
| CPU 性能优化设计依据 | `docs/design/design-cpu-performance.md` | design | `Active`（架构 / 开关有效；历史轴数字未重测） | CPU `1.0.0.0`（当前版零历史实测数字） | 待人工确认 | 2026-11-06 | 重写前全文见 `docs/archive/c1-cpu-performance-20261106.md`；第 4B 批并入 `docs/archive/c10-async-detect-20261106.md`（§8）；单独清理批整篇重写、§8 编号不变 |
| 磨皮：高低频分离与低频层路线 | `docs/design/design-smoothing.md` | design | `Active`（数字未重测） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 第 4B 批新建；归并且替代 `c02` / `c04` / `c07` / `c08` / `c15` 五篇归档件 |
| 色调、clarity 与锐化 | `docs/design/design-tone-detail.md` | design | `Active`（数字未重测） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 第 4B 批新建；归并 `c06` / `c09` / `c11`，引用 `c03` 与 `oss-survey` §8.4 |
| 肤色掩码、人脸框与五官局部 | `docs/design/design-face-mask.md` | design | `Active`（数字未重测） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 第 4B 批新建；归并 `c03` / `c05` / `c12` / `c20` / `c21`，引用 `ab-mask` / `c02` / `c19` |
| 画质对拍结论与证伪链 | `docs/design/design-quality-findings.md` | design | `Active`（**全部为历史轴结论，当前轴未重测**） | CPU `1.0.0.1` | 待人工确认 | 2026-11-06 | 第 4B 批新建；归并 `c14` / `c16` / `c17` / `c18` / `c19`，引用 `ab-metric` / `ab-smooth` / `c20` / `c21` |
| 安装包构建与打包 | `docs/guides/guide-build-installer.md` | guides | `Active`（偏差见 §6） | CPU `1.0.0.1` | 待人工确认 | 2026-11-06 | 原 `06_安装包\README_打包说明.md`；验收原件 `docs/archive/acceptance-installer-20261106.md` |
| 顶层菜单与参数面板（UI） | `docs/guides/guide-ui.md` | guides | `Active`（装机状态待人工确认） | CPU `1.0.0.1` | 待人工确认 | 2026-11-06 | 原 `04_文档\顶层菜单插件说明.md`；未采用的 HTML+websocket 方案见 `docs/archive/ui-html-websocket-proposal-20261106.md` |
| 许可与第三方组件口径 | `docs/reference/reference-licensing.md` | reference | `Active`（**口径冲突待人工确认，不含许可结论**） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 已合并 `docs/archive/opensource-boundary-20261106.md` 许可部分、`docs/archive/oss-survey-20261106.md` §4 |
| 文档总表 | `docs/INDEX.md` | INDEX | `Active`（第 4 批） | CPU `1.0.0.0` | 待人工确认 | 2026-11-06 | 无 |

**当前版合计 11 篇**（README 1 · CHANGELOG 1 · design 5 · guides 2 · reference 1 · INDEX 1）。
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
| 开源参考仓库对照与可复用清单 | `docs/archive/oss-survey-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `docs/reference/reference-licensing.md`（许可部分）；**§7.7 / §8.4 差异点已于第 4B 批并入** `docs/design/design-*.md`（GPU 化论证未带入） |
| 自研技术线路 D1（含「不上 GPU」结论） | `docs/archive/tech-roadmap-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §0、§3；证伪结论**已于第 4B 批引用**；头内登记 `S1/S2/S3` 命名陷阱 |
| 掩码对拍结论（原 `S1`） | `docs/archive/ab-mask-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §8 第 3 项；口径差异点**已于第 4B 批引用** |
| 磨皮核对拍结论（原 `S2`） | `docs/archive/ab-smooth-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §8 第 3 项；**证伪结论必须保留，已于第 4B 批引用** |
| 对拍口径修正结论（原 `S3`） | `docs/archive/ab-metric-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / core 1.4.x` | 待人工确认 | 2026-11-06 | 见 `README.md` §8 第 3 项；口径结论**已于第 4B 批引用** |
| 边缘门控（原 `C2`） | `docs/archive/c02-edge-gate-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-smoothing.md` |
| 对齐 lumina（原 `C3`） | `docs/archive/c03-lumina-align-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-face-mask.md`（并被引用于 `design-tone-detail.md`） |
| 高低频磨皮（原 `C4`） | `docs/archive/c04-highlow-freq-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-smoothing.md` |
| 鲁棒性（原 `C5`） | `docs/archive/c05-robustness-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-face-mask.md` |
| 美白红润（原 `C6`） | `docs/archive/c06-whiten-ruddy-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-tone-detail.md` |
| 引导滤波（原 `C7`） | `docs/archive/c07-guided-filter-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-smoothing.md`（证伪类，必须保留） |
| 低频层对照（原 `C8`） | `docs/archive/c08-lowfreq-compare-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-smoothing.md`（证伪类，必须保留） |
| 清晰 clarity（原 `C9`） | `docs/archive/c09-clarity-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-tone-detail.md` |
| 异步检测（原 `C10`） | `docs/archive/c10-async-detect-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | **已于第 4B 批并入** `docs/design/design-cpu-performance.md` §8（不新建 design 文件） |
| 锐化与全局锐化（原 `C11`） | `docs/archive/c11-sharpen-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-tone-detail.md` |
| 人脸局部五项（原 `C12`） | `docs/archive/c12-face-region-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-face-mask.md` |
| 与第三方画质差距定量分解（原 `C14`） | `docs/archive/c14-quality-gap-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-quality-findings.md` |
| C 方案盒式低通（原 `C15`） | `docs/archive/c15-box-lowpass-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-smoothing.md` |
| 合成阳性样本 / 痘印定量（原 `C16`） | `docs/archive/c16-spot-samples-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-quality-findings.md` |
| 扫参 / 方案 A 证伪与门控（原 `C17`） | `docs/archive/c17-param-sweep-falsify-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-quality-findings.md`（证伪类，必须保留） |
| 分辨率与脸大小依赖（原 `C18`） | `docs/archive/c18-scale-dependency-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-quality-findings.md` |
| 真机尺度对拍（原 `C19`） | `docs/archive/c19-camera-scale-ab-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-quality-findings.md`；⚠️ **根因结论已被 `c20` 推翻，不得据此施工** |
| 皮肤掩码白平衡依赖（原 `C20`） | `docs/archive/c20-whitebalance-rootcause-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-face-mask.md`（最终根因）；结论仍有效 |
| 自适应肤色中心落地（原 `C21`） | `docs/archive/c21-adaptive-skin-center-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 0.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-face-mask.md`；当前仍有效的实现 |
| CPU 性能优化重写前全文（原 `C1`，含附录 A / B） | `docs/archive/c1-cpu-performance-20261106.md` | archive | `Deprecated` | 历史轴 `3.1.x / CoreEngine 1.4.x` | 待人工确认 | 2026-11-06 | 见 `docs/design/design-cpu-performance.md`；单独清理批逐字保全，历史实测数字只在此查 |

> **归档件合计 35 篇**，正文一字未改，仅在文首追加废弃标注块；历史评分口径、版本演进史、
> 20 条雷区、许可明细出处、全部历史轴数字表格均可在此查证。
> 第 2 批 `opensource-boundary` 的许可差异点已在第 3 批并入 `docs/reference/reference-licensing.md`；
> `scorecard` 的评分公式与历史分数口径经 2026-11-06 裁定**不抽成当前版、不长期保留**。
> 第 3 批 5 篇头注的「待第 4 批引用 / 并入」与第 4A 批 19 篇头注的「第 4B 提交创建」，
> **均已在第 4B 批闭合**；归档头属当时状态标注，**不回改归档件**。
> 第 4 批归档件全部为历史轴 `3.1.x / CoreEngine 0.x` 口径，其证伪结论、`S1/S2/S3` 同名异义陷阱、
> 证伪链（`c19` 根因被 `c20` 推翻、`c21` 落地）已在 4 份 design 当前版中逐条引用。
> **单独清理批新增 `c1-cpu-performance-20261106.md`**：逐字保全 `design-cpu-performance.md`
> 重写前全文（含 `3.1.40` 修补附录 A），是当前版删去的历史加速比 / 耗时 / SHA256 /
> 离线 A/B 表的唯一查证处；`docs/design/` 5 份当前版至此**全部为零历史数字表格**。

---

## 3. 分批治理记录（已完成）

**结论：`04_文档/` 的 tracked 历史文档待治理数已清零。**
现只剩 **5 篇 `.gitignore` §10 排除件**（见 §4），不移动、不归档、不登记为 `Pending`。

| 批次 | 处理 | 结果 | 提交 |
|---|---|---|---|
| 首批 | 归档 5 篇、重写 / 增量更新 3 篇，建立 `docs/` 骨架 | 35 篇 `Pending` | `7ab8fc4` |
| 第 2 批 | 归档 5 篇、新建 `guide-ui.md` | 35 → 29 篇（24 tracked + 5 Excluded） | `220ba0d` |
| 第 3 批（B 方案） | 归档 5 篇、新建 `reference-licensing.md`、修 §7 断链 | 29 → 24 篇（19 tracked + 5 Excluded） | `84360b1` |
| **第 4A 批** | 19 篇 C 系列 `git mv` 到 `docs/archive/cNN-*-20261106.md` 并加 `ARCHIVED` 头 | 归档总数 **15 → 34**；正文 CRLF 归一化后 **19/19 MATCH**；`04_文档/` 只剩 5 篇 Excluded | `bca2d6f` |
| **第 4B 批** | 新建 4 份 `design-*.md`；`c10` 并入 `design-cpu-performance.md` §8；同步本表与根 `README.md` | **tracked 待治理清零**；4A 头的临时断链闭合；当前版不搬任何历史轴数字表格 | 本次提交 |
| **单独清理批（第 5 批）** | 新建 `c1-cpu-performance-20261106.md` 逐字保全重写前全文；整篇重写 `design-cpu-performance.md`；清空 `check_docs.py` 数字表格白名单 | **当前版历史数字全部清零**；归档件 34 → 35；§8 异步检测编号不变，既有引用无需改 | 本次提交 |

- 第 4 批方案经用户确认：`1.A`（19 篇全归档但必须新建当前版）、`2.照上表`、
  `3.C10 并入 design-cpu-performance.md`、`4.完全不搬数字表格`、`5.两次提交`。
- 4 份当前版只保留「结论 / 开关 / 坑 / 证伪 / 失效说明」；开关名与默认值已按 `01_源码/` 逐字复核
  （例如 `freqMagHi` 是配置字段、环境变量为 `BEAUTY_FREQ_MAG`；不存在 `BEAUTY_FREQ_MAG_HI`）。
- **归类修正（2026-11-06）**：首批曾把 `一级入口说明.md` 误列为「旧入口 / `Pending`」。
  核查 `.gitignore:184` 后确认它属 §4 的 `Excluded`，**不纳入治理、不归档、不移动**。
- 与 2026-11-06 诊断的「82 篇自研文档 / 8 个真实主题组」口径一致；本表只登记已落地项。

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
6. **当前版不搬数字**：历史轴实测数据只在 `docs/archive/` 查；当前版出现的数字只能是源码里的开关取值 / 编译期常量。
7. **提交前双闸门**：先跑 `python 05_验证\check_docs.py --staged`（文档一致性），
   再跑 `python 05_验证\check_upload.py --staged`（合规）。前者管文档头六字段、INDEX 双向登记、
   `docs/` 断链、命名规范、归档头替代指向、当前版数字表格告警；后者管索引残留 / 法务 / 隐私 / 体积。
   **两条都要过，缺一不提交**；`check_docs.py` 只读、纯标准库、失败退出码 1。

> 治理输出第 6 项「防腐化机制」已落地为 `05_验证/check_docs.py`（`0.1.0`）与本节第 7 条双闸门，
> 模板与规则固化在 §0。**未引入 git hook / CI**（不改变提交行为）；
> 若以后公开仓库或多人协作需要强制拦截，再单独确认后升级为 `pre-commit` / GitHub Actions。
> 新增脚本的 `0.1.0` 是脚本自身起始版本，**该批时 CPU 产品版本轴仍 `1.0.0.0`**（现已递增至 `1.0.0.1`），两者互不牵动。

---

## 6. 总表变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-06 | 建立 `docs/` 目录与 `docs/INDEX.md`；首批登记 5 篇 `Active`、5 篇 `Deprecated`；`04_文档\` 余 35 篇标 `Pending`；法务排除项标 `Excluded` |
| 2026-11-06 | 第 2 批：登记新增 1 篇 `Active`（`docs/guides/guide-ui.md`）、5 篇 `Deprecated`；`04_文档\` 35 → 29 篇（24 tracked + 5 Excluded）；修正 `一级入口说明.md` 的 `Pending` → `Excluded` 误归类；登记第 3 / 4 批方向与待合并差异点 |
| 2026-11-06 | 第 3 批（B 方案）：新增 `docs/reference/reference-licensing.md`（1 篇 `Active`）并删 `docs/reference/.gitkeep`；登记 5 篇 `Deprecated`（`oss-survey` / `tech-roadmap` / `ab-*`）；`04_文档\` 29 → 24 篇（19 tracked + 5 Excluded）；关闭第 3 批两个 `Pending` 组；联动修 `design-cpu-performance.md` §7 断链 |
| 2026-11-06 | 第 4A 批：登记 19 篇 `Deprecated`（`c02`~`c21`）；归档总数 15 → 34；`04_文档\` tracked 清零，仅剩 5 篇 Excluded；单独提交 `bca2d6f` |
| 2026-11-06 | 第 4B 批：登记新增 4 篇 `Active`（`design-smoothing` / `design-tone-detail` / `design-face-mask` / `design-quality-findings`）；`design-cpu-performance.md` 登记「并入 `c10`」；闭合第 3 批 5 篇与第 4A 批 19 篇归档头的「待第 4 批」标注；§3 改为已完成记录；§0 补「当前版数字」规则、§5 补第 6 条维护约定 |
| 2026-11-06 | 治理输出第 6 项（方案 B）：新增 `05_验证/check_docs.py`（六条断言、纯标准库、只读、负向测试通过）；§0 补「自动校验」规则与统一文档头模板，§5 补第 7 条提交前双闸门；根 `README.md` §2.4 / §5 / §9 同步 |
| 2026-11-06 | 单独清理批（第 5 批，方案 B）：新增 `docs/archive/c1-cpu-performance-20261106.md`（逐字保全重写前全文）；整篇重写 `docs/design/design-cpu-performance.md` 为零历史数字口径（§8 编号保留）；`05_验证/check_docs.py` 清空数字表格白名单并升 `0.1.1`；本表 §1 / §2 / §3 同步，归档件 34 → 35；根 `README.md` §5 / §8 / §9 与 `docs/design/design-face-mask.md` 引用同步 |

---

*本表与 `README.md` 冲突时，以逐字源码 > 动态实测 > 本表 > 归档件为准；
任何「当前结论」类改动均须标注待人工确认项，不得臆造。*
