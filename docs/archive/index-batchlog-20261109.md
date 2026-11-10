> **ARCHIVED（Deprecated）—— 2026-11-09 归档，见 `docs/INDEX.md`。**
>
> 已废弃：本文件是 `docs/INDEX.md` §6「总表变更记录」的原文，属 2026-11-06～11-09 的
> 逐批过程记录（流水账：按时间叙事、结论少、无可执行信息）。§6 已改为「批次简表 +
> 指向本文件」，过程叙述不再留在主目录。
> 2026-11-09 精简批：INDEX §3「分批治理记录」与 §6「总表变更记录」**整节移出**，
> 原文逐字追加在本文件末尾（见「附 · 原 INDEX §3 / §6」），INDEX 现只留 §1 当前版与 §2 归档登记。
> 保留原因：批次与提交号的溯源需要。**不得据此施工**；当前结论以
> `docs/INDEX.md` §1（当前版）/ §2（归档登记）为准。

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
| 2026-11-07 | `1.0.0.3` 交付链路对齐批（方案 A + B）：打包链路三份脚本版本串 `1.0.0.2` → `1.0.0.3`，生成 `OBS美颜_CPU_v1.0.0.3.exe`；本表头 / §0 模板 / §1 四条 `Active` 条目、根 `README.md`（§0 / §2 / §4 / §5 / §8 / §9）、`docs/CHANGELOG.md` §1 / §2、`docs/guides/guide-build-installer.md` 同步；根 `README.md` §8 新增第 8 项登记 `CoreEngine::version()` 版本串残留。归档件仍 35，未新增文档 |
| 2026-11-07 | `1.0.0.3` 装机脚本补齐批（方案 C 前半）：新增 `03_装机\install_1.0.0.3.bat`（纯 ASCII + CRLF，未运行）；`e2e_test.ps1` 因非提权、路径口径冲突与 Phase A 递归删除三重阻断而**未执行**，判定写入根 `README.md` §8 第 9 项、`docs/CHANGELOG.md` §2、`docs/guides/guide-build-installer.md` §4 / §6 第 4 / 8 项；同步根 `README.md` §2.3 / §4 / §9 与本表。归档件仍 35，未新增文档 |
| 2026-11-07 | `1.0.0.3` 装机口径统一批（用户裁定 **C-1**）：`obs-beauty.nsi` / `e2e_test.ps1` / `build_setup.ps1` / `install_1.0.0.3.bat` 的插件目标路径统一到 `%ProgramData%\obs-studio\plugins\<插件目录名>\bin\64bit`；重新打包同号 exe（3,638,687 B / `1c31531db60eee19130efc1fcc71ccf4`），旧同号包作废；静态核对四件 MD5 与判据自洽。**40 项装/卸断言在该批时点因提权通道被拦、OBS 正在运行、safe-delete 包装器而未执行**（同日 16:56 由用户手动补跑通过，见下一行）；根 `README.md` §0 / §2 / §8 第 2 / 9 / 10 项 / §9、`docs/CHANGELOG.md` §1 / §2、`docs/guides/guide-build-installer.md` §0 / §4 / §5 / §6 第 1 / 4 / 8 / 9 项同步。归档件仍 35，未新增文档 |
| 2026-11-07 | `1.0.0.3` 装卸回归验收批：用户关闭 OBS 后以管理员 PowerShell 独立进程执行 `06_安装包\e2e_test.ps1`，Phase A 25/25 + Phase B 15/15 = **40/40 PASS、0 FAIL**，`%TEMP%\obsbeauty_test\log.txt` 的 `0 failure(s)` 结束行、`done.flag` 已写，终态四件 MD5 与测试前一致；根 `README.md` §2.3 / §8 第 2 / 9 项 / §9、`docs\CHANGELOG.md` §1 / §2、`docs\guides\guide-build-installer.md` §5 / §6 第 4 / 8 / 10 项同步。**本批只做验收与文档同步，未改代码、未升版本号**。验收日志逐字归档到 `05_验证/e2e_install_20261107.md`（非 Active 文档，本表不登记）。归档件仍 35，未新增文档 |
| 2026-11-07 | `1.0.1.0` 修订位升版批（用户裁定 **A**）：`beauty_params.h` / `beauty_core.cpp` / `obs-beauty-ui.cpp` 根治版本串并升到 `1.0.1.0`；原生 PowerShell 调 `cl.exe` 重编两件 DLL 到 `02_构建\build_1.0.1.0\`；打包链三份脚本与新增 `03_装机\install_1.0.1.0.bat` 同步；重打包 `OBS美颜_CPU_v1.0.1.0.exe`（3,637,954 B / `e0684330f8f3b79a98c6752d1b365793`）。根 `README.md`、`docs\CHANGELOG.md`（新增 `1.0.1.0` 独立章节）、本表 §0 / §1 / §5 / §6、`docs\guides\guide-build-installer.md` 同步。**新包装卸回归未跑**，登记为根 `README.md` §8 第 2 / 11 项。归档件仍 35，未新增文档 |
| 2026-11-08 | 复跑前置核查批（用户裁定 **甲**）：只读核对电量 99% / OBS 未运行 / 机上四件仍 `1.0.0.3` / 回滚源 `02_构建\build_1.0.0.3\` 两件 MD5 与机上一致；会话内尝试覆盖两件 DLL 时因**文件级 ACL**（`BUILTIN\Users` 仅 `ReadAndExecute`）报 `UnauthorizedAccessException`，覆盖未成功、本机零改动，判定前置覆盖须与 `e2e_test.ps1` 同在管理员进程执行。新坑写入根 `README.md` §8 第 11 项、`docs\CHANGELOG.md` §2、`docs\guides\guide-build-installer.md` §6 第 11 项。当时 40 项回归未跑；归档件仍 35，未新增文档 |
| 2026-11-08 | 首次复跑判读批（用户裁定 **方案一**）：00:09 的 `e2e_test.ps1` 结果 **28 PASS / 12 FAIL**，因 `safety` 基准仍是 `1.0.0.3` 旧四件（前置覆盖未生效）且 `A0` 删除失败，判定为**前置不满足的无效回归**，不得当作 `1.0.1.0` 验收结论；安装器 exit 0、版本资源 `1.0.1.0`、卸载清理干净、终态四件完整还原。新坑「脚本无提权自检 + `ErrorActionPreference=Continue` 静默带过覆盖失败」写入根 `README.md` §8 第 11 项、`docs\CHANGELOG.md` §2、`docs\guides\guide-build-installer.md` §6 第 11 项。**方案一待用户在管理员进程复跑**，失败日志未归档；归档件仍 35，未新增文档 |
| 2026-11-08 | `1.0.1.0` 装卸回归验收批（方案一执行）：提权封装 `%TEMP%\wb_rerun_e2e_1010.ps1` 在同一 High 完整性进程内完成「覆盖两件 DLL → 校验 MD5 → `&` 调用 `e2e_test.ps1`」（判据与断言未改），结果 **40 PASS / 0 FAIL**（Phase A 25/25、Phase B 15/15，`%TEMP%\obsbeauty_test\log.txt` 开头 00:58:46、结束行 00:58:55）。`safety` 四件已为 `1.0.1.0` 值（`e34117…` / `ea79c0…`），`A0` 两条删除断言转 PASS，判定为**有效验收**；终态四件与测试前逐位一致，安装目录与两个 HKLM 键清空。日志逐字归档 `05_验证/e2e_install_20261108.md`（非 Active 文档，§1 / §2 不登记）。新坑「agent 会话无法自动提权启动解释器（工具安全策略拒绝）且本机 UAC `ConsentPromptBehaviorAdmin=0`，提权需用户一次右键授权」写入 `docs\CHANGELOG.md` §2。归档件仍 35，未新增 docs 文档 |
| 2026-11-08 | `1.0.2.0` 修订位升版批：修「手遮脸时美白遮罩叠到手部」——`01_源码/beauty_freq.cpp` 的 `toneColor()` 改为**整帧施加**（`BEAUTY_TONE_GLOBAL` 默认 1，对齐 GPU 版口径），17 锚点表预展开 256 项；`01_源码/beauty_freq.h` 接口注释与 `beauty_params.h` 版本串（`1.0.2.0`）同步；原生 PowerShell 调 `cl.exe` 重编两件 DLL 到 `02_构建\build_1.0.2.0\`（449,024 B / `af4d38b06b05509e8311e9170b476d21`、218,624 B / `5e70aadf42eccd737a7ff0c338158259`）并重打包 `OBS美颜_CPU_v1.0.2.0.exe`（3,639,501 B / `696142dd54346b24cd75cd1519a53e3d`），`build_setup.ps1` / `obs-beauty.nsi` / `e2e_test.ps1` 三份脚本版本串同步；根 `README.md`（§0 / §1 / §3）、`docs\CHANGELOG.md`（新增 `1.0.2.0` 独立章节）、`docs\design\design-tone-detail.md`（新增 §1.1、开关清单补 `BEAUTY_TONE_GLOBAL`）、本表 §1 色调条目同步；取证归档 `05_验证/tone_global_20261108.md`（非 Active 文档，不登记）。**真机出图已于 2026-11-08 16:51–17:22 实测**（当前装机 `1.0.3.0`，取证 `05_验证/ab_perf_20261108.md`）；**物理手遮脸观感与 40 项装卸回归仍未做**，已在 `docs\CHANGELOG.md` §2 该节末段登记。归档件仍 35，未新增 docs 文档 |
| 2026-11-08 | `1.0.3.0` 修订位升版批（同日第二次）：从 GPU 版 3.2.0 移植**输入方向自动补偿**，修「竖屏摄像头美颜完全没效果」——`beauty_face.h/.cpp` 增加 `rotateDeg` 与 `letterboxRgbRot()`；`beauty_core.cpp` 增加方向状态机、`invRotatePoint/invRotateFace`、探测后按分数选方向、几何反变换、方向一变即清人脸框 EMA；`beauty_params.h` → `1.0.3.0`。重编两件 DLL 到 `02_构建\build_1.0.3.0\`（456,704 B / `470d636c650f70fc6752e1f8d9644cca`、218,624 B / `b3d09761922c1e6fd4fda0524756b8fc`），重打包 `OBS美颜_CPU_v1.0.3.0.exe`（3,641,958 B / `185927d8b6533f79a5de6a89e189aa5f`），打包链三份脚本版本串同步，新增 `03_装机\install_1.0.3.0.bat`；根 `README.md`（§0 / §1 / §3 / §9）、`docs\CHANGELOG.md`（新增 `1.0.3.0` 章节）、`docs\design\design-face-mask.md`（§13 + 头部）、`docs\guides\guide-build-installer.md`、本表 §1 肤色掩码条目同步；取证归档 `05_验证/rot_input_20261108.md`（非 Active 文档，不登记）。**真机加载、出图、自动方向补偿与片内 A/B 性能对照已于 2026-11-08 16:51–17:22 实测**（"2026-11-08 16-51-40.txt" l. 107, l. 274；取证 `05_验证/ab_perf_20261108.md`）；**物理机位观感与 40 项装卸回归仍未做**。归档件仍 35，未新增 docs 文档 |
| 2026-11-09 | `1.0.4.0` + `1.0.5.0` 两批（同夜）+ 装机与真机验证：①`1.0.4.0` 修订位（优化速度）——`beauty_smooth.cpp` 的 `surface3RgbBand` 真的按 ROI 裁剪（原实现拿到 `roi` 只判空，整帧照算），真机引擎 25.0 → 9.4 ms、合计 28.0 → 12.2 ms，输出**逐字节不变**（3 档分辨率 × 3 种模式，差异像素 0）；`obs-beauty.cpp` init 日志加 `band_roi=crop`。②`1.0.5.0` 功能位（头歪 45° 自动补偿）——`detect()` 与 `letterboxRgbRot()` 支持任意角度，`FaceBox` 增加 `roll` / `rw` / `rh`，新增 `rotCanvasSize()`、`rollBoxPlausible()` 假框门槛、`BEAUTY_AUTO_ROLL` / `BEAUTY_AUTO_ROLL_MISS`，掩码改按倾斜矩形/椭圆绘制，`obs-beauty.cpp` 加 `roll_probe=on`。③装机：`ProgramData` 两件 DLL 换成 `1.0.5.0`（465,920 B / `91949c86…`；218,624 B / `a7587afb…`），旧 `1.0.3.0` 已备份。④真机验证：录像 150 s 零丢帧，录制第 17.6 s `倾斜探测命中 +45°（score=0.871）`，逐帧复核 270° `faces=0` / 315° `score 0.876~0.891`。⑤**新发现未修**：源被转 90/270° 时脖子通道仍按源坐标 `+y` 画，正立帧 27.9% 掩码落到脸框外，写入 `design-face-mask.md` §15。取证 `05_验证/ab20261109_band_roi_obs.md` / `ab20261109_head_roll.md` / `ab20261109_install_and_live.md`（均非 Active，本表不登记）；工具新增 `05_验证/obs_ctl.py` / `mask_dump.cpp` / `det_bench.cpp`。归档件仍 35，未新增 docs 文档 |
| 2026-11-09 | **真机口径纠偏 + `1.0.13.0` 真机确认**：装 `1.0.13.0` 后同一份 `fuse=off` 代码（= `1.0.12.0` 盒式）在 13:44 只测到磨皮 3.1，而 13:13 测到 6.12 —— 逐段比值显示所有多线程段齐降 1.8 倍、单线程的人脸检测不变（后台抢核）。**`13.25` / `12.07` / `−1.40` 三个跨会话绝对数作废**，`README.md` 性能口径改以同会话配对为准（新基线 8.34 ms / ROI≈147k）；`live_matrix.py` 固定 S/F 两组并新增三项日志校验（`init OK` 只一次、窗口 ≤8、`fuse` 与预期一致） |
| 2026-11-09 | **重打 `1.0.13.0` 装机包（正式发布）**：`06_安装包\OBS美颜_CPU_v1.0.13.0.exe`（3,652,694 B / MD5 `409721014032b3e95f611ed8bc0e0269`，PE 版本资源四段 `1.0.13.0`），包内两件 DLL 与 `02_构建\build_1.0.13.0\` 逐位相同；`1.0.4.0` 起装机包停在 `1.0.3.0` 的历史结束。同时把版本号收成单一来源：`build_setup.ps1` 读 `beauty_params.h` 的 `BEAUTY_BUILD_STR`、`obs-beauty.nsi` 缺 `/DPKGVER` 直接 `!error`、`e2e_test.ps1` 按版本推导被测 exe（原先三处都写死 `1.0.3.0`，会静默打/测旧包）。README / CHANGELOG / guide-build-installer 的历史口径同步；40 项装卸回归本轮未跑（需管理员进程且会改 ProgramData 与 HKLM） |

---

## 附 · 原 INDEX §3「分批治理记录」（2026-11-09 从 INDEX 移出）

> 内容与移出时逐字一致；INDEX 只保留 §1 当前版与 §2 归档登记。
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
| **流水账清理批** | 归档 `INDEX.md` §6 逐批记录与 `CHANGELOG.md` 五版性能条目；README §8/§9 由过程叙述改为结论表 | 归档件 35 → 37；主文档树 3 篇合计减 21 KB，6 条断言仍全过 | 本次（未提交） |

- 第 4 批方案经用户确认：`1.A`（19 篇全归档但必须新建当前版）、`2.照上表`、
  `3.C10 并入 design-cpu-performance.md`、`4.完全不搬数字表格`、`5.两次提交`。
- 4 份当前版只保留「结论 / 开关 / 坑 / 证伪 / 失效说明」；开关名与默认值已按 `01_源码/` 逐字复核
  （例如 `freqMagHi` 是配置字段、环境变量为 `BEAUTY_FREQ_MAG`；不存在 `BEAUTY_FREQ_MAG_HI`）。
- **归类修正（2026-11-06）**：首批曾把 `一级入口说明.md` 误列为「旧入口 / `Pending`」。
  核查 `.gitignore:184` 后确认它属 §4 的 `Excluded`，**不纳入治理、不归档、不移动**。
- 与 2026-11-06 诊断的「82 篇自研文档 / 8 个真实主题组」口径一致；本表只登记已落地项。

---


---

## 附 · 原 INDEX §6「总表变更记录」（2026-11-09 从 INDEX 移出）

> 内容与移出时逐字一致。
## 6. 总表变更记录

**只留批次结论。** 2026-11-06～11-09 的逐批过程叙述（原 20 条，含每批改了哪些文件、
哪次脚本没跑、哪个 ACL 拦了覆盖）已整体归档：`docs/archive/index-batchlog-20261109.md`。
批次明细与提交号见 §3，版本事实见 `docs/CHANGELOG.md`；本表不再重复。

| 日期 | 批次 | 结果 |
|---|---|---|
| 2026-11-06 | 首批 / 2 / 3 / 4A / 4B / 单独清理（第 5） | 建 `docs/` 骨架；归档 35 篇；当前版 11 篇 |
| 2026-11-07 | `1.0.0.3` 交付链路 + 装机口径 C-1 | 打包链统一到 `ProgramData`；40 项装卸 PASS |
| 2026-11-08 | `1.0.1.0`～`1.0.3.0` | 版本轴根治；装卸 40 项 PASS；输入方向补偿 |
| 2026-11-09 | `1.0.4.0`～`1.0.13.2` | 性能三轮；头歪 / 脖子修复；审查修复 C1 / C2；C2 返工（检测态按 slot 切开） |
| 2026-11-09 | `1.0.13.3` | 时序 EMA / 人脸框 EMA / 分段耗时也按 slot 存；新增 `ema_cmp` 判据（16/16 → 0/16）；单实例输出逐字节不变 |
| 2026-11-09 | `1.0.13.4` | 共用的人脸检测器加锁（detect/load/release/setInputSize 串行）、置信度按 slot 回传；新增 `mt_cmp` 判据（无锁对照件 4/40、9/40 → 0/40）；单实例输出逐字节不变 |
| 2026-11-09 | `1.0.13.9` | roll 锁死：歪头过 45° 再回正后 `effRoll` 仍停在 −45（位置正常只因 `phi` +42.6° 与 `roll` 抵消，掩码 23097 px vs 正常 17805 px）；加周期性 0° 对照（45 帧一次，只有 0° 的框 score 高出 0.05 才释放），回正后第 24 帧释放、6 帧逐帧收到 0，最大相邻 meanD 跳变 0.10；正立静止逐字节不变 |
| 2026-11-09 | `1.0.13.8` | 歪头 45° 仍闪：真因是掩码对齐在异步链路里断续（到货帧输出上一帧画面、未到货帧输出当前帧，worker 一忙一闲画面来回跳，57→57° meanD 7.09→1.67）；对齐加「画面几乎没动」门控（`frameNearlySame`，默认 4 灰阶），运动时宁可掩码晚一帧也不重复画面；全程 meanD 1.29…1.68 无跳变，正立静止逐字节不变 |
| 2026-11-09 | `1.0.13.7` | 歪头 45° 仍闪：1.0.13.6 只缩了丢检窗口，没动「几何一帧内整个换掉」；新增 6 帧几何过渡（`geoLast` + `startGeoFade` + `applyGeoFade`，中心/rw-rh/roll/关键点一起插值）；锁定段 meanD 1.16→1.61（+0.46）变为 0.93→1.63 六步；正立 8/8 逐字节不变 |
| 2026-11-09 | `1.0.13.6` | 歪头 45° 时闪/卡：`fw/fh` 互换改用离散标记 `srcRot`（原 `\|cos\|>=\|sin\|` 在 45° 只差 0.4%）；`rollMiss` 8→4、`kMaskHold` 6→8、丢检保留 EMA 历史；丢检窗口 8→4 帧，正立 8/8 逐字节不变 |
| 2026-11-09 | `1.0.13.5` | 美形位移场改建在脸坐标系（瘦脸/下巴在 90/270 源上落错位置）；新增 `_warp_seam.py` 判据 + `beauty_core_test_norot.dll` 对照件（下巴落点 `y[-105.9,111.8]` → `y[39.7,69.4]`，与正立同形）；正立 8/8 面板组合逐字节不变 |
| 2026-11-09 | 流水账清理批 | 归档 2 篇（INDEX §6 逐批记录、CHANGELOG 性能批逐版原文）；README §8/§9 压成结论表；归档件 35 → 37 |
