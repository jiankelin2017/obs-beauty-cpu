# docs/archive/ 重建：冷备核对结果与待确认清单 · 2026-11-10

| 字段 | 值 |
|---|---|
| 文档版本 | `1.0.0.0` |
| 核对日期 | 2026-11-10 07:57（GMT+8） |
| 适用代码版本 | CPU 线 `1.0.13.12`（`BEAUTY_BUILD_STR`，`01_源码/beauty_params.h:888`） |
| 基线提交 | `b92d0424428430f740f6bcb73994ef0dfc05f3f9`（`main`） |
| 冷备来源 | `D:\插件\_整理_20261110\before\`，清单 `MANIFEST.tsv` |
| 状态 | `Completed`（2026-11-10 已按用户裁定执行三批，见 §8 执行回执） |
| 维护人 | 待人工确认 |
| 替代文档 | 现行 `docs/INDEX.md` §2、`docs/reference/reference-conclusions.md` |
| 失效说明 | 本清单只对 2026-11-10 07:57 的冷备与仓库状态有效；冷备或仓库任一变动都须重新核对 MD5 |

> 本文属 `05_验证/` 取证与记录类文件，按 `05_验证/INDEX.md` 的裁定不纳入 `docs/` 文档体系，不登记 `docs/INDEX.md`。

---

## 0. 结论先行

**冷备完好，38 篇归档件已逐字恢复并入库：MD5 与字节数 38/38 全部一致，0 缺失、0 不一致，且 38 篇的文件名与文首废弃标注已满足用户统一规则。恢复后同步改写了 13 篇现役文档、1 份总表与 1 个巡检脚本；`check_docs.py` 九条断言与 `check_upload.py` 四道断言全部通过。完整执行回执见 §8；§1–§5 保留执行前的诊断与方案，属历史记录。**

---

## 1. 冷备核对结果（可复核事实）

| 检查项 | 结果 | 取得方式 |
|---|---|---|
| `MANIFEST.tsv` 总条目 | 121 | 逐行解析 TSV |
| 其中 `docs/archive/` 条目 | **38** | 路径前缀筛选 |
| `before/` 实际文件总数 | 121 | `find before -type f \| wc -l` |
| 38 篇 MD5 全等 | **38 / 38** | Python `hashlib.md5` 逐文件比对 |
| 38 篇字节数全等 | **38 / 38** | `os.path.getsize` 比对 |
| 缺失 / 不一致 | **0 / 0** | 同上 |
| 文首含「已废弃」 | **38 / 38** | `grep -l 已废弃` |
| 文首以 `> **ARCHIVED` 起始 | **38 / 38** | 抽样 + 逐篇首行提取 |
| 文件名符合 `主题-YYYYMMDD.md` | **38 / 38** | 逐篇目视核对 |

**命名结论**：38 篇原名（如 `c02-edge-gate-20261106.md`、`changelog-raw-20261106.md`）已经是「主题-YYYYMMDD.md」格式，**无需改名**。用户统一规则第 4 条不产生额外动作。

**文首结论**：38 篇首行形如 `> **ARCHIVED · 已废弃，见 docs/design/xxx.md**`，已含废弃原因与替代指向，符合统一规则第 2 条。按用户约束「正文不改写、不删减」，恢复时逐字复制，不润色、不补数字。

---

## 2. 全量清单（38 篇）

> MD5 列取前 12 位便于人工比对；完整 32 位值见 `D:\插件\_整理_20261110\MANIFEST.tsv` 第 70–107 行。所有目标路径均为 `docs/archive/<文件名>`。

| # | 文件 | 大小 | MD5(前12) | 主题 / 首行替代指向 | 需改名 | 建议动作 |
|---|---|---|---|---|---|---|
| 1 | `ab-mask-20261106.md` | 5467 | `ca25fdd1ffcc` | 掩码 AB → `README.md` §8 | 否 | 原样恢复 |
| 2 | `ab-metric-20261106.md` | 7959 | `86fdd4f16a3b` | 指标 AB → `README.md` §8 | 否 | 原样恢复 |
| 3 | `ab-smooth-20261106.md` | 10850 | `4aed93a55b1b` | 磨皮 AB → `README.md` §8 | 否 | 原样恢复 |
| 4 | `acceptance-engineering-20261106.md` | 11971 | `f65e74e8882b` | 工程验收 → `docs/CHANGELOG.md` | 否 | 原样恢复；**注意**：`reference-conclusions.md` §2 把本篇列为「完全未定位」，恢复后需人工决定是否补写承接小节 |
| 5 | `acceptance-installer-20261106.md` | 8060 | `8b539d237f25` | 装机验收 → `guide-build-installer.md` | 否 | 原样恢复 |
| 6 | `acceptance-quality-20261106.md` | 15007 | `d346825f1f2a` | 画质验收 → `CHANGELOG.md` / `README.md` §8 | 否 | 原样恢复 |
| 7 | `c02-edge-gate-20261106.md` | 7949 | `d12521407c51` | 边缘门控 → `design-smoothing.md` | 否 | 原样恢复 |
| 8 | `c03-lumina-align-20261106.md` | 9170 | `aa76a400bfc7` | 亮度对齐 → `design-face-mask.md` | 否 | 原样恢复 |
| 9 | `c04-highlow-freq-20261106.md` | 11599 | `a9d53efc0723` | 高低频 → `design-smoothing.md` | 否 | 原样恢复 |
| 10 | `c05-robustness-20261106.md` | 5414 | `5544fdef94d7` | 鲁棒性 → `design-face-mask.md` | 否 | 原样恢复 |
| 11 | `c06-whiten-ruddy-20261106.md` | 5216 | `fba8a2c70a70` | 美白红润 → `design-tone-detail.md` | 否 | 原样恢复 |
| 12 | `c07-guided-filter-20261106.md` | 5371 | `ab8f1205a253` | 导向滤波 → `design-smoothing.md` | 否 | 原样恢复 |
| 13 | `c08-lowfreq-compare-20261106.md` | 6943 | `596f4d02d618` | 低频对比 → `design-smoothing.md` | 否 | 原样恢复 |
| 14 | `c09-clarity-20261106.md` | 6487 | `6ea5905cd589` | clarity → `design-tone-detail.md` | 否 | 原样恢复 |
| 15 | `c1-cpu-performance-20261106.md` | 20748 | `46dd3178a143` | CPU 性能 → `design-cpu-performance.md` | 否 | 原样恢复 |
| 16 | `c10-async-detect-20261106.md` | 16106 | `16d491d49278` | 异步检测 → `design-cpu-performance.md` | 否 | 原样恢复 |
| 17 | `c11-sharpen-20261106.md` | 13135 | `8836da9fe379` | 锐化 → `design-tone-detail.md` | 否 | 原样恢复 |
| 18 | `c12-face-region-20261106.md` | 10816 | `528ef587a89c` | 人脸区域 → `design-face-mask.md` | 否 | 原样恢复 |
| 19 | `c14-quality-gap-20261106.md` | 8027 | `dee4af3d25b7` | 画质差距 → `design-quality-findings.md` | 否 | 原样恢复 |
| 20 | `c15-box-lowpass-20261106.md` | 9808 | `a6471d30c437` | 盒式低通 → `design-smoothing.md` | 否 | 原样恢复 |
| 21 | `c16-spot-samples-20261106.md` | 8655 | `da7038ed65a5` | 斑点样本 → `design-quality-findings.md` | 否 | 原样恢复 |
| 22 | `c17-param-sweep-falsify-20261106.md` | 10218 | `ebc8e4419488` | 参数扫描证伪 → `design-quality-findings.md` | 否 | 原样恢复 |
| 23 | `c18-scale-dependency-20261106.md` | 5204 | `837c035e4f7a` | 尺度依赖 → `design-quality-findings.md` | 否 | 原样恢复 |
| 24 | `c19-camera-scale-ab-20261106.md` | 5317 | `a8ecbaf80362` | 相机尺度 AB → `design-quality-findings.md` | 否 | 原样恢复 |
| 25 | `c20-whitebalance-rootcause-20261106.md` | 9644 | `b43536a79ac2` | 白平衡根因 → `design-face-mask.md` | 否 | 原样恢复 |
| 26 | `c21-adaptive-skin-center-20261106.md` | 10209 | `90e08b2a4ef8` | 自适应肤色中心 → `design-face-mask.md` | 否 | 原样恢复 |
| 27 | `changelog-history-20261109.md` | 85179 | `e94adcc5b06e` | CHANGELOG 历史轴 → `docs/CHANGELOG.md` | 否 | 原样恢复（85 KB，最大件之一） |
| 28 | `changelog-perf-20261109.md` | 15514 | `26b37e8d048c` | 性能变更流水 → `docs/CHANGELOG.md` | 否 | 原样恢复 |
| 29 | `changelog-raw-20261106.md` | 155932 | `68b118e8cdb2` | 逐提交流水账 → `docs/CHANGELOG.md` | 否 | 原样恢复（155 KB，最大件） |
| 30 | `gpu-porting-plan-20261106.md` | 11480 | `b6dfa447df17` | GPU 移植计划 → 根 `README.md` | 否 | 原样恢复 |
| 31 | `index-batchlog-20261109.md` | 19860 | `bba532c7ceef` | 分批治理记录 → `docs/INDEX.md` | 否 | 原样恢复 |
| 32 | `opensource-boundary-20261106.md` | 5603 | `0f4c8f461359` | 开源边界 → `reference-licensing.md` | 否 | 原样恢复 |
| 33 | `oss-survey-20261106.md` | 23620 | `18c25d449aa1` | 开源调研 → `reference-licensing.md` | 否 | 原样恢复 |
| 34 | `readme-archive-20261106.md` | 59418 | `a03cac96828a` | 结项归档版 README → 根 `README.md` | 否 | 原样恢复 |
| 35 | `readme-entry-20261106.md` | 13033 | `3dae2f6e25aa` | 入口说明 → 根 `README.md` | 否 | 原样恢复 |
| 36 | `scorecard-20261106.md` | 9732 | `4e91ccf76de3` | 评分卡 → `README.md` §8 | 否 | 原样恢复 |
| 37 | `tech-roadmap-20261106.md` | 11752 | `9cea105c759b` | 技术路线 → 根 `README.md` | 否 | 原样恢复 |
| 38 | `ui-html-websocket-proposal-20261106.md` | 5421 | `2a1490164db0` | UI 方案提案 → `guide-ui.md` | 否 | 原样恢复 |

**合计**：38 篇，约 0.66 MB（按上表字节数求和）。

---

## 3. 恢复后必须处理的影响面（本轮未执行）

### 3.1 巡检脚本

`05_验证/check_docs.py` 当前 9 条断言全部通过（本轮实测：`Active 文档：13 · 归档件：0 · 全部通过`）。恢复后预期变化：

| 断言 | 恢复后预期 | 依据 |
|---|---|---|
| [2] 归档件 ARCHIVED 头与替代指向 | **通过** | 38 篇首行均为 `> **ARCHIVED`，含「已废弃」，替代指向的 `docs/*.md` 与 `README.md` 均存在 (Jian, `05_验证/check_docs.py`, ll. 255–284) |
| [3] INDEX 双向登记一致 | **失败（38 个 `miss_arch`）** | 脚本从 `docs/INDEX.md` §2 读取归档登记行；当前 §2 是「历史原件处置」说明表，无 38 行登记 (Jian, `05_验证/check_docs.py`, ll. 286–296) |
| [5] 命名规范 | **通过** | 归档命名规则为 `主题-YYYYMMDD.md`，38 篇原名已符合 |
| 文件头注释第 2、3、8 条 | 描述与现状矛盾 | 注释写「归档目录应不存在」「归档目录为空，历史断链例外随之清零」 |

### 3.2 现役文档（13 篇）

下列文件的正文含「（已删除）」「不再保留 `docs/archive/`」等表述。恢复归档件后，这些表述会从事实变成**误导内容**，与用户判断标准里的「无效/误导」直接冲突：

`README.md`（2 处）、`docs/CHANGELOG.md`（1）、`docs/INDEX.md`（4，另加 §0 的「archive 分类已移除」）、`docs/design/design-cpu-performance.md`（1）、`design-face-mask.md`（1）、`design-quality-findings.md`（1）、`design-smoothing.md`（1）、`design-tone-detail.md`（1）、`docs/guides/guide-build-installer.md`（1）、`guide-ui.md`（1）、`docs/reference/reference-conclusions.md`（5）、`reference-licensing.md`（1）、`05_验证/INDEX.md`（1）。

其中 `docs/reference/reference-conclusions.md` 的**核心结论**（§0「本仓库不再保留历史原件的逐字全文，也不再保留 `docs/archive/` 目录」）整段失效，需要重写而非打补丁；该文还记载 `acceptance-engineering-20261106.md` 的 12 项 UI 工程验收结论「完全未定位、仅存于冷备」，恢复后这条的定位说明也要改。

### 3.3 版本库边界

`.gitignore` 当前没有排除 `docs/archive/`。38 篇在被删除前本是版本库成员（`git status --short` 显示大量 `D` / `MD` 可证），所以恢复后它们会重新成为待提交文件。用户需裁定：**归档件入库**（随仓库分发）还是**加入 `.gitignore`**（仅本机留存）。这与 `docs/INDEX.md` §2 现行「逐字冷备于仓库外，不随仓库分发」的口径相反，是方向性决策。

---

## 4. 建议执行顺序（待确认后才动手）

| 批次 | 动作 | 产出 | 风险 |
|---|---|---|---|
| 批 1 | 从 `before/docs/archive/` 逐字复制 38 篇到 `docs/archive/`，复制后立即复算 MD5 并比对 | 38 个文件 + 校验回执 | 低；纯新增，不覆盖现有文件 |
| 批 2 | 重建 `docs/INDEX.md` §2 的 38 行登记表（状态列必须为 `Deprecated`），把 §0 的「archive 分类已移除」改回「archive（隔离存放，不限）」 | 巡检断言 [3] 恢复通过 | 中；总表措辞需逐条核对 |
| 批 3 | 按主题分批改写 3.2 节列出的 13 篇文档：把「已删除」改为「见 `docs/archive/xxx.md`」，重写 `reference-conclusions.md` §0，同步 `check_docs.py` 的注释与版本号 | 文档体系与事实重新一致 | 高；属于用户执行顺序中的「第 5 项逐篇改写」，须逐篇给 diff 并标人工确认项 |

按用户「分批处理，按主题投喂」的约束，批 3 建议拆成 4 组：① README + CHANGELOG、② 6 篇 design、③ 2 篇 guides + 2 篇 reference、④ 05_验证/INDEX.md + check_docs.py。

---

## 5. 待人工确认项（本轮全部未执行）

1. 38 篇是否**全部**恢复？还是只恢复 `reference-conclusions.md` 标记为「完全未定位」的 `acceptance-engineering-20261106.md` 等少数篇？
2. `docs/archive/` 恢复后是否纳入版本库？这会翻转现行「不随仓库分发」的口径。
3. 批 3 的 13 篇现役文档是否同步改写？若不同步改写，仓库会同时存在「已删除」表述与真实归档件，构成误导。
4. `docs/reference/reference-conclusions.md` 的核心结论是否整篇重写？该文件现有 §2–§4 的「唯一留存索引」定位在归档件回归后是否仍有存在必要？
5. `check_docs.py` 的版本号与断言注释如何调整？按项目四段式规则，若只改注释不影响行为，构建位 +1；若断言逻辑变化，修订位 +1。**待人工确认**：本次是否属于行为变更。
6. 恢复动作是否需要先做一次 `git stash` 或分支保护？当前工作区有 236 条未提交变更，批 2/批 3 会修改其中已被 `git add` 的文档。

---

## 6. 可验证事实与个人推测的分界

- **可验证事实**：第 1 节的 MD5 / 字节数 / 文件计数、第 2 节的 38 行清单、第 3.1 节的脚本代码行、第 3.2 节的文件与引用次数、第 3.3 节的 `.gitignore` 与 git 状态，均来自本轮命令输出与文件原文，可复核。
- **个人推测（显式标记）**：第 3.1 节「断言 [3] 会失败」与第 4 节的风险分级是执行前的静态推断；执行后已实测验证，结果见 §8。
- **执行回执**：用户已于 2026-11-10 确认「全部恢复并入库 + 三批一起做」，三批已执行完毕。本文 §1–§5 保留的是执行前的诊断与方案，属历史记录，不再代表当前状态。

---

## 7. 引用来源（MLA 格式）

Jian. *05_验证/check_docs.py*, 文件头与 ll. 195–300, 2026-11-10. ———. *docs/INDEX.md*, §0–§4, 2026-11-10. ———. *docs/reference/reference-conclusions.md*, §0–§4, 2026-11-10. ———. *05_验证/INDEX.md*, 「适用范围与时效」, 2026-11-09. ———. *README.md*, 文首与 §8, 2026-11-10. ———. *D:\插件\_整理_20261110\MANIFEST.tsv*, ll. 70–107, 2026-11-10. ———. *D:\插件\_整理_20261110\before\docs\archive\*.md*, 文首标注, 2026-11-06–2026-11-09.

---

## 8. 执行回执（2026-11-10）

用户裁定：**38 篇全部恢复并入库** + **三批一起做**。执行结果如下，全部为实测值。

| 批次 | 动作 | 实测结果 |
|---|---|---|
| 批 1 | 逐字复制 38 篇到 `docs/archive/`，复算 MD5 | 38/38 一致、0 缺失、0 不一致；文首 `> **ARCHIVED` 标注 38/38；`git ls-files docs/archive` = 38，工作区 = 38，未入索引 0 |
| 批 2 | 重写 `docs/INDEX.md`：文首声明、§0 规则、治理范围、§1 归档指向、§2 重建 38 行登记、§3 边界、§4 维护约定 | `check_docs.py` 断言 [2] 38/38、[3] Active 13 = 13 / 归档 38 = 38、[5] 归档命名 38/38 全部通过 |
| 批 3 | 改写 13 篇现役文档 + `check_docs.py` 注释与版本 | 10 篇文首「整理批时效声明」→「归档重建声明」；80 处 `` `xxx.md`（已删除） `` → `` `docs/archive/xxx.md`（`Deprecated`） ``；13 处短语改写；`reference-conclusions.md` §0–§4 重写；`05_验证/INDEX.md` 两条偏差记录更新 |

**双闸门终检**：`check_docs.py` 九条断言全部通过（0 断链；1 条已登记历史断链例外 `05_验证/ab20261109_band_roi_obs.md`，附登记日期与复核期限）；`check_upload.py` 四道断言全部通过（索引一致性 / 法务 / 隐私 / 体积）。

**同步改动清单**（用户「文档同步」规则要求列出）：

| 类型 | 文件 |
|---|---|
| 新建 | `05_验证/code_review_20261110.md`、`05_验证/archive_restore_manifest_20261110.md`（本文） |
| 恢复 | `docs/archive/` 38 篇（逐字，正文未改写） |
| 重写 | `docs/INDEX.md`（§2 重建 38 行登记） |
| 改写 | `README.md`、`docs/CHANGELOG.md`、`docs/design/design-cpu-performance.md`、`design-face-mask.md`、`design-quality-findings.md`、`design-smoothing.md`、`design-tone-detail.md`、`docs/guides/guide-build-installer.md`、`guide-ui.md`、`docs/reference/reference-licensing.md`、`docs/reference/reference-conclusions.md`、`05_验证/INDEX.md` |
| 脚本 | `05_验证/check_docs.py`：`0.3.1` → `0.3.1.1`（四段式，构建位 +1；只改注释与 `VERIFY_ARCHIVE_EXEMPT` 登记，九条断言逻辑未变） |
| 备份 | `D:\插件\_整理_20261110\before_restore_20261110\`（13 篇现役文档改前副本） |

**待人工确认（执行后仍未关闭 3 项）**：

1. `check_docs.py` 的 `0.3.1` → `0.3.1.1` 是从三段式规范化为四段式的口径变更；若你认为应按「功能/修订位」计，请裁定。
2. `05_验证/INDEX.md` 的三条偏差记录在归档件恢复后是否重新启用，本文保守写「未随归档件恢复而自动恢复（待人工确认）」，没有替你下结论。
3. `acceptance-engineering-20261106.md` 的 12 项 UI 工程验收结论仍无 Active 承接小节；原文已可查，但按「不补写未经核实结论」的裁定未并入当前版。

**已关闭**：原第 4 项「提交状态」已于 2026-11-10 08:47 提交为 `0d1405b` 后关闭；提交前 `--staged` 双闸门 `0/0`，提交后 `git status --short` = 0（工作区干净）、全量双闸门全部通过。本仓库无远端，该提交未推送。

