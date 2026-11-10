# 历史结论唯一留存索引

| 字段 | 值 |
|---|---|
| 版本 | `1.0.14.0` |
| 最后更新 | 2026-11-10（二次复核：升级为小节级定位） |
| 适用代码版本 | CPU 线 `1.0.14.0`（`BEAUTY_BUILD_STR` 唯一出处） |
| 维护人 | Jian |
| 状态 | `Active`（本表是索引，不是结论正文） |
| 替代文档 | `docs/archive/` 下 38 篇历史原件（2026-11-10 重建，逐字恢复并入库；登记见 `docs/INDEX.md` §2） |

---

## 0. 结论先行

**`docs/archive/` 已于 2026-11-10 重建，38 篇历史原件逐字恢复并纳入版本库；本表仍是「每条有效结论的唯一存放位置」索引。** 有效结论（含正向结论与负向／证伪结论）此前已逐条并入
`docs/design/`、`docs/guides/`、`docs/reference/`、`README.md` 与 `docs/CHANGELOG.md`。
归档件全部标 `Deprecated`、**不得据此施工**，它们只承担溯源职能，不构成第二份当前结论。
本表**不复制结论正文**，只登记每条结论的**唯一存放位置（小节级）**，使每份「当前有效结论」在 Active 文档里只存在一份。

> **二次复核（2026-11-10）**：本表原「唯一存放位置」为文档级去向，取自原 `docs/INDEX.md` §2 登记的
> 替代指向。本批对 38 条逐条核验，改填承接该结论的 `§编号 + 小节标题`，并在备注列补记证据行号。

> **不改写正文**，已登记为 `05_验证/check_upload.py` 第 5 条断言的例外；
> 具体文件与行号见 `docs/INDEX.md` 文首声明，不得据此施工或外传。
> 复核更正了 6 处原文档级指向错误，标出 1 条完全未定位与若干条部分未定位；方法与局限见 §4。

> **时效**：下表指向的 Active 文档才是当前有效口径；归档件路径现已恢复，但全部标 `Deprecated`、不得据此施工。
> 历史原件逐字全文现存于 `docs/archive/`（38 篇，已入库）；仓库外 `D:\插件\_整理_20261110\before\` 另留一份冷备。

## 1. 正向有效结论 → 唯一存放位置（小节级）

| 归档件（`docs/archive/`） | 主题 | 唯一存放位置（§小节） | 补充定位与核验依据 |
|---|---|---|---|
| `acceptance-engineering-20261106.md` | 工程 / UI 12 项验收（3.1.39） | **未定位**（Active 文档无承接小节） | 原登记 `docs/CHANGELOG.md` 只有 §4 失效说明（CHANGELOG:510–511）；12 项判定表与 UI 控件验收结论未并入，仅存于冷备 |
| `acceptance-installer-20261106.md` | 安装包装/卸 40 项验收（3.1.39） | `docs/guides/guide-build-installer.md` §3 三个编译期硬约束 | 另见 §5 卸载、§7.3 / §7.4；依据 :115–117, :157, :203–205 |
| `acceptance-quality-20261106.md` | 工程 / 画质 11 项验收（3.1.34） | `README.md` §8 待人工确认项（第 3、4 项）· **部分定位** | 11 项判定表、corr 修正与两处方法硬伤未承接；另见 `design-quality-findings.md` §2、`design-tone-detail.md` §1 / §4；依据 README:323–324 |
| `scorecard-20261106.md` | 复刻评分（3.1.39，79.0 / 70.2 分） | `docs/CHANGELOG.md` §4 失效内容说明（务必读）· **已更正** | 原登记 `README.md` 无分数逐字承接；分数见 CHANGELOG:513，不抽成当前版的裁定见 README:333（§8）；「86 是纹理保留率」易混点未定位 |
| `ab-mask-20261106.md` | 掩码对拍结论（原 `S1`） | `docs/design/design-face-mask.md` §2 掩码几何与保护区（`c03`、`ab-mask`）· **已更正** | 原登记 `README.md` 无承接；另见 §1 / §10、`design-quality-findings.md` §2；依据 :26, :41–42, :122 |
| `ab-metric-20261106.md` | 对拍口径修正结论（原 `S3`） | `docs/design/design-quality-findings.md` §2 口径纪律（读任何历史数字之前先看）· **已更正** | 原登记 `README.md` 无承接；另见 §6 / §7、`design-smoothing.md` §3；依据 :37–41, :136 |
| `c02-edge-gate-20261106.md` | 边缘门控（原 `C2`） | `docs/design/design-smoothing.md` §4 边缘门控的三个坑（`c02` §2） | 另见 §3 / §6 / §8、`design-face-mask.md` §7；依据 :58, :65–69, :87, :102 |
| `c04-highlow-freq-20261106.md` | 高低频磨皮（原 `C4`） | `docs/design/design-smoothing.md` §2 架构不变量（`c04` §7，改动前必读） | 另见 §1 / §3 / §6 / §8；依据 :27, :36, :40–44, :103 |
| `c05-robustness-20261106.md` | 鲁棒性（原 `C5`） | `docs/design/design-face-mask.md` §4 鲁棒性三项机制（`c05`） | 另见 §8 开关清单 / §10 归档映射 / §12；依据 :61–66, :118 |
| `c06-whiten-ruddy-20261106.md` | 美白红润（原 `C6`） | `docs/design/design-tone-detail.md` §1 结论先行 | 另见 §1.1 色调三段的施加范围 / §6 / §7；依据 :28–29, :44, :50, :112 |
| `c09-clarity-20261106.md` | 清晰 clarity（原 `C9`） | `docs/design/design-tone-detail.md` §2 clarity（`c09`） | 另见 §1 / §4 / §6 / §7；依据 :30–31, :57–61, :113 |
| `c10-async-detect-20261106.md` | 异步检测（原 `C10`） | `docs/design/design-cpu-performance.md` §8 异步检测（第 4B 批并入，本批保留原文口径） | 另见 §8.2 / §8.3 / §5 / §7、`design-face-mask.md` §5；依据 :327, :335, :348, :356–357；原件 §7.1–§7.4 细则非逐字承接 |
| `c11-sharpen-20261106.md` | 锐化与全局锐化（原 `C11`） | `docs/design/design-tone-detail.md` §3 锐化与运动自适应 EMA（`c11`） | 另见 §1 / §3.1 三处「EMA」同名异义 / §4 / §7；依据 :32–33, :66–71, :81, :114 |
| `c12-face-region-20261106.md` | 人脸局部五项（原 `C12`） | `docs/design/design-face-mask.md` §6 五官局部五项（`c12`）· **部分定位** | §1.1「五官立体 = 大尺度 unsharp 证伪 / dodge & burn」子结论未定位；依据 :75–80, :119 |
| `c15-box-lowpass-20261106.md` | C 方案盒式低通（原 `C15`） | `docs/design/design-smoothing.md` §5 盒式低通的调参顺序与坑（`c15`） | 另见 §1 / §7 / §8、`design-cpu-performance.md` §2.11；依据 :31, :71–76, :106；§6 对齐 bug 的具体修法未逐字复现 |
| `c16-spot-samples-20261106.md` | 合成阳性样本 / 痘印定量（原 `C16`） | `docs/design/design-quality-findings.md` §3 证伪链第 2 条 | 另见 §4 / §6 / §7 / §8 第 3 项；依据 :78–80, :122, :131 |
| `c18-scale-dependency-20261106.md` | 分辨率与脸大小依赖（原 `C18`） | `docs/design/design-quality-findings.md` §3 证伪链第 4 条 | 另见 `design-face-mask.md` §7 / §1、本文 §7 / §8 第 2 项；依据 :84–86, :94, :133 |
| `c20-whitebalance-rootcause-20261106.md` | 皮肤掩码白平衡依赖（原 `C20`） | `docs/design/design-face-mask.md` §3 根因与落地（`c20` → `c21`） | 另见 §1 / §9 / §10、`design-quality-findings.md` §3 第 6 条；依据 :28, :44–49, :120 |
| `c21-adaptive-skin-center-20261106.md` | 自适应肤色中心落地（原 `C21`） | `docs/design/design-face-mask.md` §3 根因与落地（`c20` → `c21`）· **部分定位** | §3.2 LNK2019 局部工程坑未单独留存；另见 §1 / §8 / §10、`design-tone-detail.md` §3.1；依据 :29, :51, :55–58, :121 |

## 2. 负向 / 证伪结论 → 唯一存放位置（小节级）

| 归档件（`docs/archive/`） | 主题 | 唯一存放位置（§小节） | 补充定位与核验依据 |
|---|---|---|---|
| `readme-entry-20261106.md` | 旧仓库入口说明（差异点已合并） | `README.md` §3 架构与帧管线 · **部分定位** | §9.2 / §9.3 三条「拒绝 / 弃用」结论未定位；另见 §2.3 / §5 / §8 第 4 项、`docs/INDEX.md` §1；依据 README:132, :108, :324 |
| `gpu-porting-plan-20261106.md` | GPU 移植开发计划（与纯 CPU 方向冲突） | `README.md` §8 待人工确认项（不得当作已确认结论使用）第 5 项 | 另见 §0 / §3、`design-cpu-performance.md` §4；依据 README:25, :325, design-cpu:289 |
| `ui-html-websocket-proposal-20261106.md` | 未采用的 HTML + obs-websocket 面板方案 | `docs/guides/guide-ui.md` 附录 B · 失效内容说明与合并记录（2026-11-06） | 该文档无 §数字编号小节承接，结论落在附录与文首「替代文档」行；另见 `docs/INDEX.md` §1；依据 guide-ui:10, :186 |
| `tech-roadmap-20261106.md` | 自研技术线路 D1（含「不上 GPU」结论） | `docs/design/design-smoothing.md` §1 结论先行 · **已更正** | 原登记 `README.md` 无逐字承接；§4「调参省」证伪未严格承接；另见 §3 / §8、`design-face-mask.md` §7；依据 :37, :52–59, :109 |
| `ab-smooth-20261106.md` | 磨皮核对拍结论（原 `S2`） | `docs/design/design-smoothing.md` §3 已证伪路线与回退开关（别重试）· **已更正** | 原登记 `README.md` 无承接；`T=8.3` 落地与三个回退开关未定位；另见 `design-quality-findings.md` §2 / §2.1 / §7；依据 :56–57, :62, :108 |
| `c07-guided-filter-20261106.md` | 引导滤波（原 `C7`） | `docs/design/design-smoothing.md` §3 已证伪路线与回退开关（别重试） | 另见 §6 开关清单 / §8；依据 :52, :83, :104 |
| `c08-lowfreq-compare-20261106.md` | 低频层对照（原 `C8`） | `docs/design/design-smoothing.md` §3 已证伪路线与回退开关（别重试） | 另见 §1 / §8、`design-quality-findings.md` §2；依据 :53–55, :61, :105 |
| `c17-param-sweep-falsify-20261106.md` | 扫参 / 方案 A 证伪与门控（原 `C17`） | `docs/design/design-quality-findings.md` §3 证伪链第 3 条 | 另见 §1 / §4 / §7、`design-face-mask.md` §3；依据 :27–28, :81–83, :132 |
| `c19-camera-scale-ab-20261106.md` | 真机尺度对拍（原 `C19`） | `docs/design/design-quality-findings.md` §3 证伪链第 5 条 | 只取方法论，根因已被 `c20` 推翻；另见 §1 / §3 第 6 条 / §7、`design-face-mask.md` §1 / §7；依据 :29–30, :87–90, :134 |

## 3. 历史原件（无独立有效结论，按过时 / 流水账归档）

| 归档件（`docs/archive/`） | 原主题 | 独立有效结论 | 有效内容实际去向（§小节） |
|---|---|---|---|
| `changelog-raw-20261106.md` | 逐提交流水账（2532 行原文） | 无 | 里程碑 → `docs/CHANGELOG.md` §1 / §2；C20 / C21 结论 → `design-face-mask.md` §1 / §3；三条反直觉结论 → `design-smoothing.md` §3（依据 CHANGELOG:520、face-mask:28、smoothing:76） |
| `c1-cpu-performance-20261106.md` | CPU 性能优化重写前全文（原 `C1`，含附录 A / B） | 无 | `design-cpu-performance.md` §2.1–§2.4 / §3.1 / §3.2 / §4 / §5 / §8；该文附录 A / B **只留指针**，不逐节承接（依据 :38–59, :269–300, :327, :371–397） |
| `index-batchlog-20261109.md` | 总表逐批变更记录（流水账原文） | 无 | `docs/INDEX.md` §1 当前版登记（Active） / §2 历史原件处置（依据 :66–108） |
| `changelog-perf-20261109.md` | 性能批 `1.0.8.0`–`1.0.12.0` 逐版原文（流水账） | 无 | `design-cpu-performance.md` §2.5–§2.11 / §3 / §4；`docs/CHANGELOG.md` §2 / §4 **只留摘要、指针与失效说明**（依据 design-cpu:61–291、CHANGELOG:490–493 / :506–516） |
| `changelog-history-20261109.md` | `1.0.13.7` 及更早版本逐版原文（含历史轴 `3.1.x`） | 无 | `docs/design/design-head-roll.md` §§3–7 / §9 / §11；当前五版在 `docs/CHANGELOG.md` §2（依据 head-roll:55 / :82 / :147 / :185 / :217 / :246 / :274–282） |
| `changelog-fix-20261110.md` | `1.0.13.8`–`1.0.13.12` 逐版原文（流水账） | 无 | `docs/CHANGELOG.md` §2 速查表（五版一行一版 + 产物指纹表）与 §1 当前有效结论（依据 CHANGELOG:41–42, :47–60） |

## 4. 归档清单、复核方法与恢复方式

- 归档范围：`docs/archive/` 下 **39 篇** `.md` 已于 2026-11-10 按用户裁定逐字恢复并纳入版本库，
  `docs/INDEX.md` §2 登记 39 行；根目录 `_audit_20261109.md`（诊断对象为 CPU `1.0.13.9` /
  HEAD `e5c1a1f`，已被后续正式报告取代）仍按 2026-11-10 整理批的裁定不恢复。
- 归类口径：按 `docs/INDEX.md` §2 登记文本的关键词机械归类，不引入新判断；
  归类只用于检索，不改变「唯一存放位置」列的事实内容。
- 恢复与校验：恢复源为 `D:\插件\_整理_20261110\before\docs\archive\`，`MANIFEST.tsv`
  记录路径 / 大小 / MD5；本批逐篇复算，MD5 与字节数 **38/38 一致、0 缺失**，
  文首 `ARCHIVED` 标注 **38/38 齐全**。仓库外冷备保留，作为第二份逐字副本。
- 本表行数：正向 22 条、负向 10 条、历史原件 6 条，合计 38 条，与 `docs/INDEX.md` §2 的 38 行登记一一对应。

**二次复核方法（2026-11-10）**：4 个只读审读代理分批通读 38 篇冷备原件与现行 Active 文档，
逐条给出承接结论的 `§编号 + 逐字小节标题`、真实行号与不超过 80 字的逐字原文片段；
主会话从代理报告中抽取 20 处证据行号回读核对，全部属实。**本表不复制结论正文，只记定位。**

**复核更正与局限（如实登记，不做补写）**：

| 项 | 数量 / 内容 |
|---|---|
| 完全未定位 | 1 条：`acceptance-engineering-20261106.md`（12 项 UI 工程验收结论在 Active 文档中无承接小节；原文现可在 `docs/archive/` 查到，但按「不补写未经核实结论」的裁定仍未并入当前版） |
| 部分未定位 | 表中逐条标「部分定位」的条目，以及备注列写明「未定位 / 未逐字承接 / 只留指针」的子结论 |
| 按裁定不搬的数字 | 历史轴耗时、加速比、SHA256、IoU、保留率等按 2026-11-06 裁定不进当前版，**属明确处置而非遗漏**；本表不将其登记为缺失 |
| 未做补写 | 未定位项一律不擅自写入 Active 文档，以免引入未经核实的结论；需要时查 `docs/archive/` 归档件 |

- 行号口径：备注列形如 `:61–66` 指该行「唯一存放位置」列所指文档的行号；跨文档引用另标文件名。
- 定位精度：本表是**结论级**的小节定位，不承诺逐句或逐数字定位；需要逐字出处时以 Active 文档正文、
  逐字源码与 `docs/archive/` 归档件为准。
- 唯一性边界：这里说的「唯一」指**当前有效结论在 Active 文档树里只留一份**；`docs/archive/` 38 篇
  是历史逐字副本，全部标 `Deprecated`、不得据此施工，不构成第二份当前结论。

## 5. 未纳入本次整理（保留，均为唯一留存的数据或有效文档）

- `05_验证/` 顶层 23 篇取证／记录类文件：每篇对应一次独立实测，按 2026-11-09 裁定的 A 口径保持体例。
- 12 篇 Active 文档（含本表共 13 篇）：结论正文的唯一存放位置。
- `_run_e2e_1412.bat`：按用户 2026-11-10 裁定**不入库**，由 `.gitignore:223` 的 `/_run_e2e_*.bat` 排除，
  仅作本机临时验收入口；`05_验证/e2e_install_20261109_1312.md` 与 `docs/CHANGELOG.md` §2 对其引用属历史取证说明。

---

*本表与 `README.md` 冲突时，以逐字源码 > 动态实测 > `docs/INDEX.md` > 本表为准。*
