# OBS 美颜滤镜 · CPU 版

| 字段 | 值 |
|---|---|
| 版本 | `1.0.1.0` |
| 最后更新 | 2026-11-07 |
| 适用代码版本 | CPU 线 `1.0.1.0`（提交见 git log） |
| 维护人 | 待人工确认 |
| 状态 | `Active` |
| 替代文档 | `docs/archive/readme-archive-20261106.md`（910 行结项归档版全文）、`docs/archive/readme-entry-20261106.md`（旧仓库入口） |

> **本文是全库唯一 README。** 所有「当前有效结论」以 `docs/INDEX.md` 登记的路径为准；
> 同一主题不允许两份当前版并存，旧版一律进 `docs/archive/`。

---

## 0. 一句话结论

**这是一个纯 CPU 实现的 OBS 美颜滤镜插件，独立产品线版本 `1.0.1.0`；不引入自定义 shader / GPU 计算管线，美颜算法全部在 CPU buffer 上完成。**

| 关键事实 | 值 |
|---|---|
| 宿主 | OBS Studio 32.1.1（Windows 10/11 x64，64 位） |
| 滤镜 ID | `obs_beauty_filter`（**不得更改**，改了老场景里的滤镜会变成「缺失滤镜」） |
| 版本轴 | CPU 线 `1.0.1.0`（四段）／ GPU 版 `3.0.1`（三段，**另一仓库、另一条轴、不可互比**） |
| 版本号唯一出处 | `01_源码/beauty_params.h` 的 `BEAUTY_BUILD_STR` |
| UI 显式标识 | 编译期宏 `BEAUTY_UI_CPU_EDITION=1` 时，菜单「美颜·CPU(&A)」、窗口标题、蓝色 `CPU 版` 徽章、版本角标 `CPU v1.0.1.0`；默认 `0` 时行为零变化 |
| 当前构建产物 | `02_构建/build_1.0.1.0/`；`build_1.0.0.2/`、`build_1.0.0.1/` 与 `build_1.0.0.0/` 为前版 |
| 当前安装包 | `06_安装包/OBS美颜_CPU_v1.0.1.0.exe`（**2026-11-07 第三次打包**，3,637,954 B，MD5 `e0684330f8f3b79a98c6752d1b365793`，`ProductVersion` / `FileVersion` 均为四段 `1.0.1.0`）；本次由用户裁定 **A** 升到修订位，重编两件 DLL 后打包。`1.0.0.3` 包（3,638,687 B / `1c31531db60eee19130efc1fcc71ccf4`）与更旧的 `v1.0.0.0.exe` 均保留为历史产物 |
| 许可 | 根 `LICENSE` 逐字为 **GPL-2.0**；但仓库内三处口径互斥、**尚未裁定**，见 `docs/reference/reference-licensing.md` §2 与 §8 第 1 项 |

---

## 1. 版本轴（先读，避免用错口径）

**CPU 线自 `1.0.0.0` 起另立，不是把 `3.1.40` 回退，也不是 `3.1.41`。**
历史 `3.1.x / core 1.4.x` 整条轴及其版本演进史、验收报告、产物 md5 已整体归档，不再作为现状口径。

| 线 | 版本 | 段数 | 仓库 | 说明 |
|---|---|---|---|---|
| **CPU（本仓库）** | `1.0.1.0` | 四段 | `D:\插件\OBS美颜源码` | 纯 CPU，本 README 适用 |
| GPU | `3.0.1` | 三段 | `D:\插件\OBS美颜GPU版` | 正式版，**只读参照，本轮所有改动均未触碰该库** |

递增规则（CPU 线，四段式 主.功能.修订.构建）：构建位 +1 = 注释/文档/重新打包等不影响行为的改动；修订位 +1、后两位归零 = 修 bug / 调默认值 / 优化速度但没加新东西；功能位 +1、后两位归零 = 用户可见的新功能；主版位 +1、后三位归零 = 不兼容变更。低位不进位，跨档取高。本次 `1.0.0.3` → `1.0.1.0` 属「修 bug → 修订位 +1」（装机路径口径修正 + 引擎版本串失同步根治）。
`CoreEngine::version()` 已并入单轴，不再维护独立 `core 1.4.x` 号。
版本号同步位置：`beauty_params.h` → `obs-beauty.cpp` / `obs-beauty-ui.cpp` → `build_setup.ps1` / `obs-beauty.nsi` / `e2e_test.ps1` → `docs/CHANGELOG.md`。

> 历史口径入口：`docs/archive/readme-archive-20261106.md` §2、§7；`docs/archive/changelog-raw-20261106.md`。
> **根 README / 04_文档 中出现的 `3.1.39 / 3.1.40 / core 1.4.x` 结论一律只代表当时状态，不代表当前实现。**

---

## 2. 快速开始（可执行）

### 2.1 构建

```bat
:: 在 02_构建\ 下，默认仍输出到 build_output\
build_manual.bat        :: 编译 obs-beauty.dll（滤镜 / CoreEngine）
build-ui_320.bat        :: 编译 obs-beauty-ui.dll（面板，脚本内定义 /DBEAUTY_UI_CPU_EDITION=1）
```

**CPU `1.0.1.0` 请用独立产物目录，不要覆盖 `build_output\` 里的 3.1.39 / 3.1.40 定稿 DLL：**

```bat
set BEAUTY_OUTDIR=D:\插件\OBS美颜源码\02_构建\build_1.0.1.0
build_manual.bat
build-ui_320.bat
```

工具链：MSVC 14.51.36231 + Windows SDK 10.0.26100.0 + `C:\Qt` + NSIS 3。
`vcvars64.bat` 在受限环境里因 `reg.exe` 被拦不可直接使用，需手工设置 `INCLUDE` / `LIB` / `PATH`（构建脚本内已硬编码探测逻辑）。
构建脚本按**内容探测**定位依赖目录（源码看 `obs-beauty.cpp`、SDK 看 `obs-studio-32.1.1\libobs`、验证目录看 `deps\runtime\include`），目录编号改动不会失效。

构建后自检：

```powershell
& python '02_构建\verify-ui-imports.py' '02_构建\build_1.0.1.0\obs-beauty-ui.dll'
```

### 2.2 打包

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "06_安装包\build_setup.ps1"
```

脚本默认从 `02_构建\build_1.0.1.0\` 取件（可用 `BEAUTY_BUILD_OUT` 覆盖），做版本串自检 `1.0.1.0` + `obs_beauty_filter`，暂存到纯 ASCII 临时目录，确保 `obs-beauty.nsi` 为 UTF-8 with BOM 后调 `makensis`，产物落到 `06_安装包\OBS美颜_CPU_v1.0.1.0.exe`。

**2026-11-07 实测（1.0.1.0 升版重打包）**：`build_setup.ps1` 版本串自检 `1.0.1.0` 通过，`makensis` 编译成功，产物 3,637,954 B、MD5 `e0684330f8f3b79a98c6752d1b365793`；Windows 版本资源 `ProductVersion` / `FileVersion` 均为四段 `1.0.1.0`。包内四件：`obs-beauty.dll` 447,488 B / `e34117c88501956963c6c6f9370682d7`、`obs-beauty-ui.dll` 218,624 B / `ea79c0dca53d1e8e5ea08b958ad3fe40`、`onnxruntime.dll` / `cd5e3b3eedbe6774b28d8fff9d0a3243`、`yunet.onnx` / `4ae92eeb150c82ce15ac80738b3b8167`。两件新 DLL 内**只剩 `1.0.1.0` 一个版本串**，`verify-ui-imports.py` 五项导入全过。受工具安全策略限制，本轮用原生 PowerShell 直接调 `cl.exe` 编译（参数与 `build_manual.bat` / `build-ui_320.bat` 一致），未走 `cmd.exe`。

### 2.3 装机

> ✅ **2026-11-07 16:56 装卸回归已实测通过**：用户关闭 OBS 后，以管理员 PowerShell 独立进程运行 `e2e_test.ps1`，Phase A 25 项 + Phase B 15 项，**40/40 PASS、0 FAIL**，`done.flag` 已写、日志 `0 failure(s)` 结束行；终态四件 MD5 与测试前逐一相同（"log.txt" l. 68–73）。
> 装机口径按用户裁定 C-1 统一到 ProgramData（`obs-beauty.nsi` / `e2e_test.ps1` / `build_setup.ps1` / `install_1.0.1.0.bat` 四处一致），见 §8 第 9 项。
> 复跑方式：先完全关闭 OBS（含托盘），再以管理员身份打开 PowerShell 执行
> `powershell -NoProfile -ExecutionPolicy Bypass -File "D:\插件\OBS美颜源码\06_安装包\e2e_test.ps1"`，结果写在 `%TEMP%\obsbeauty_test\log.txt`。
> `install_1.0.1.0.bat` 部署到 `C:\ProgramData\obs-studio\plugins\` 且拒绝覆盖已有文件；**当前该位置仍是 `1.0.0.3` 四件套**，直接运行会按要求退出而不改动文件。

装机通用约束（历史实测，仍适用于路径规则）：必须**手动提权**（受限进程写不进 `C:\Program Files`）；先关 OBS；`C:\ProgramData` 可写。
面板插件目录名必须与 DLL 名一致（`<目录名>\bin\64bit\<目录名>.dll`），名字对不上 OBS 会**静默跳过且不写日志**。

### 2.4 上传前自检（法务/隐私红线，务必执行）

```powershell
python 05_验证\check_upload.py            # 合规：检查当前索引
python 05_验证\check_upload.py --staged   # 合规：提交前检查暂存区
python 05_验证\check_upload.py --fix      # 合规：移除「已跟踪但工作区已删」的残留条目
python 05_验证\check_docs.py              # 文档：全量一致性自检
python 05_验证\check_docs.py --staged     # 文档：提交前模式，附列本次涉及的文档
```

**提交前是双闸门，两条都要过**：
`check_upload.py` 四道断言 = 索引一致性 · 法务红线（闭源商业资产）· 隐私红线（真人面部位图 / `.raw` 帧）· 体积红线（单文件 > 1 MB 应走 Release 附件）；
`check_docs.py` 六条断言 = Active 文档头六字段 · 归档件 `ARCHIVED` 头与替代指向 · `docs/INDEX.md` 双向登记 · `docs/` 路径零断链 · 命名规范 · 当前版数字表格（**只告警不阻断**）。
后者只读、纯标准库、失败退出码 1；历史归档头里的「待第 N 批」措辞按已知历史标注放行，不会误报。

---

## 3. 架构与帧管线

> 本节合并自 `docs/archive/readme-entry-20261106.md` §3、§7（旧仓库入口说明）。

```
OBS Studio 32.1.1
└─ 视频源 → 滤镜链 → obs-beauty.dll · obs_beauty_filter
   └─ CoreEngine（纯 CPU，运行时不加载任何第三方美颜 SDK）
      ├─ YuNet 人脸检测（ONNX Runtime）
      ├─ 肤色掩码 / 区域椭圆 / 5 关键点
      ├─ 保边平滑 + 高低频分离 + 细节回填
      ├─ 色调（美白 / 红润 / 清晰 / 全局锐化 / 脸内锐化）
      ├─ 五官局部（去法令纹 / 去黑眼圈 / 亮眼 / 祛斑痘 / 五官立体）
      └─ 位移场（瘦脸 / 大眼 / 下巴）

obs-beauty-ui.dll · 顶层菜单「美颜·CPU(&A)」（仅 CPU 宏开启时）
└─ 参数面板：遍历滤镜 obs_properties 动态生成，不持有参数副本 → 读写全走滤镜属性
```

帧管线：检测 → 肤色掩码 → 磨皮 → 色调 → 锐化 → 五官局部 → 美形（管线最末端）→ 输出。
全 0 参数时逐字节透传，不进引擎。14 项功能分五页：美颜 / 锐化 / 五官 / 美形 / 高级。

**「纯 CPU」的准确口径（2026-11-06 确认）**：
`obs-beauty.cpp` 中的 `gs_texrender` / `gs_texture_*` / `gs_draw_sprite` 是 **OBS 滤镜框架唯一的帧 I/O 通道**
（源帧 → map 到 CPU `buf_in` → CPU 计算 → 回写 `buf_out` → 画回），不是 GPU 计算。
验收标准是「**不引入自定义 shader / hlsl / GPU 计算管线，美颜算法全部在 CPU buffer 上完成**」，
而非字面上的「无任何图形 API 调用」。`01_源码` 中无 `gs_effect_create*`、无 hlsl / effect 资产，
唯一相关的是 OBS 内置 `OBS_EFFECT_DEFAULT`。

---

## 4. 目录地图

| 目录 | 内容 |
|---|---|
| `01_源码\` | 自研引擎全部实现（`.cpp/.h`） |
| `02_构建\` | 编译脚本、`build_output\`（历史定稿，**勿覆盖**）、`build_1.0.1.0\`（当前 CPU 产物）、`build_1.0.0.2\` / `build_1.0.0.1\` / `build_1.0.0.0\`（前版）、`build_3.1.40\`（历史） |
| `03_装机\` | 装机/卸载与回滚脚本（**最新为 `install_1.0.1.0.bat`，2026-11-07 补齐；装机路径已按 C-1 与 NSIS 安装包统一到 ProgramData，见 §2.3**） |
| `04_文档\` | tracked 历史文档已全部归档；仅剩 5 篇 `.gitignore` §10 排除件（仅本机查证）；**新文档不再放这里** |
| `05_验证\` | 离线验证脚本、goldens 真值、上传自检 |
| `06_安装包\` | NSIS 脚本 `obs-beauty.nsi`、打包脚本、装卸实测脚本、`OBS美颜_CPU_v1.0.1.0.exe`（当前）与 `v1.0.0.0.exe`（前版） |
| `07_开源参考\` | MIT 许可原文与 effect 源文件 |
| `参考文件\` | 第三方依赖 SDK / 对照资产 / 原始帧数据，**仅本机保留，不入库** |
| `docs\` | **当前版文档体系**（见 §5） |

---

## 5. 文档体系

**总表：`docs/INDEX.md`**（主题｜路径｜类型｜状态｜适用版本｜维护人｜最后核对｜替代/归档）。

统一规则：固定分类 `README` / `design` / `guides` / `reference` / `CHANGELOG` / `adr` / `archive`；
主目录每类只留当前版，同一主题不允许两份并存；新文档只能放规定位置，命名 `类型-主题.md`；
归档件按 `主题-YYYYMMDD.md` 命名，文首标注「已废弃，见 xxx」及原因。

| 当前版 | 位置 |
|---|---|
| 本 README（唯一） | `README.md` |
| 变更日志（全局唯一） | `docs/CHANGELOG.md` |
| CPU 性能设计（含异步检测 §8；零历史实测数字） | `docs/design/design-cpu-performance.md` |
| 磨皮：高低频分离与低频层路线 | `docs/design/design-smoothing.md` |
| 色调、clarity 与锐化 | `docs/design/design-tone-detail.md` |
| 肤色掩码、人脸框与五官局部 | `docs/design/design-face-mask.md` |
| 画质对拍结论与证伪链 | `docs/design/design-quality-findings.md` |
| 安装包构建指南 | `docs/guides/guide-build-installer.md` |
| 顶层菜单与参数面板（UI） | `docs/guides/guide-ui.md` |
| 许可与第三方组件口径 | `docs/reference/reference-licensing.md` |
| 历史原件（只读） | `docs/archive/` |

**可信度顺序**：逐字源码 > 动态实测 > 推断 > 拟合（`01_源码\` > 本 README > `04_文档\`）。

> **当前版文档的数字口径（第 4 批起）**：`docs/design/` 的当前版只保留结论 / 开关 / 坑 / 证伪 /
> 失效说明，**不搬历史轴数字表格**；文中出现的数字仅是 `01_源码\` 里的开关取值 / 编译期默认值。
> 扫参表、保留率、耗时、IoU 等历史实测数据只在 `docs/archive/` 查（2026-11-06 裁定）。
> 开关名与默认值已按当前源码逐字复核，例如幅度门控上限是配置字段 `freqMagHi`、
> 环境变量为 `BEAUTY_FREQ_MAG`，**不存在 `BEAUTY_FREQ_MAG_HI`**。
> **单独清理批（第 5 批）已把最后一篇含历史数字表格的 `docs/design/design-cpu-performance.md`
> 整篇重写**，重写前全文（含 `3.1.40` 修补附录）逐字保全于
> `docs/archive/c1-cpu-performance-20261106.md`；至此 `docs/design/` 5 份当前版**全部零历史实测数字**，
> `05_验证/check_docs.py` 的数字表格白名单也已清空。

**防腐化**：`docs/INDEX.md` §0 有统一文档头模板与自动校验规则，§5 有 7 条维护约定；
`05_验证/check_docs.py`（`0.1.1`）把「新增文档漏登记 INDEX / 归档件没写替代指向 / 改路径留断链 /
命名跑偏」变成提交前可拦截的断言。该脚本自身版本与 CPU 产品版本轴互不相干，产品轴仍 `1.0.1.0`。

---

## 6. 合规与红线

**`.gitignore` 是唯一的排除闸门。** 任何未在其中列出的文件**默认会被上传**——新增文件前必须先确认它不该公开，或先加规则再 `git add`。

| 绝不入库 | 位置 | 理由 |
|---|---|---|
| 闭源商业 SDK 二进制、对照提取物 | `参考文件\01_参考分析\`、`参考文件\03_依赖与SDK_OBS\` | 无再分发权（法务红线） |
| 含可识别真人面部的位图 / `.raw` 帧 | `05_验证\` | 隐私红线 |
| 构建中间产物 / `*.exe` / `*.obj` | `02_构建\*` | 可再生；正式产物走 Release 附件 |
| 含参考实现内部细节的 5 份文档 | `04_文档\01_第三方磨皮真值.md` 等（`.gitignore` §10） | 仅本机查证用 |

> ✅ **闸门已补（2026-11-06，提交 `e14f3f2`）**：规则已由 `02_构建/build_output/` 改为 `02_构建/build_*/`，
> 覆盖 `build_output\` / `build_1.0.0.0\` / `build_1.0.0.1\` / `build_1.0.0.2\` / `build_3.1.40\` 等全部版本化产物目录；带尾斜杠只匹配目录，
> 不影响 `build_manual.bat` / `build-ui_320.bat` / `build_log.txt` / `verify-ui-imports.py`。
> 已用 `git check-ignore -v` 与 `check_upload.py`（325 文件四道断言）复核通过。
> 新产物目录不再需要靠显式 `git add` 规避，但提交前仍应跑 `--staged` 闸门。

第三方组件：ONNX Runtime / YuNet（MIT，随包分发）、OBS Studio libobs（GPL-2.0，宿主，不随仓库分发）、
`07_开源参考\` 内 MIT 许可原文。GPL-2.0 参考仓库只读思路、未抄代码。
**当前版的许可事实、三处口径冲突与可执行约束见 `docs/reference/reference-licensing.md`**；
历史出处与组件明细（历史轴 `3.1.x`，未在 CPU `1.0.0.0` 复核）只读见
`docs/archive/readme-archive-20261106.md` §16。

---

## 7. 变更记录（当前版）

见 `docs/CHANGELOG.md`。历史逐提交流水账见 `docs/archive/changelog-raw-20261106.md`。

---

## 8. 待人工确认项（不得当作已确认结论使用）

| # | 项 | 说明 |
|---|---|---|
| 1 | **许可口径冲突** | 三处互斥：根 README / 历史 README §16.1 的「动态链接 libobs → GPL-2.0，源码须以 GPLv2 提供」；旧入口 §1 的「不得商用或再分发」；开源清单 §4 / 方案边界 §1 的「闭源分发且按可商用再分发选型」。详见 `docs/reference/reference-licensing.md` §2、§5，**确定对外口径后再统一，不得据任一处对外宣称**。 |
| 2 | **1.0.1.0 装卸回归待复跑** | `1.0.0.3` 的 40 项断言已于 2026-11-07 16:56 全过（见 §9 与 `05_验证\e2e_install_20261107.md`），但那是**旧包**。`1.0.1.0` 重编了两件 DLL，**尚未跑过装卸回归**；且 `e2e_test.ps1` 以「测试前机上已装文件 MD5」（`$safetyMap`）为 A2 / B1 判据，本机现装 `1.0.0.3` 四件，直接复跑会有多条 FAIL。复跑前置方案见 §8 第 11 项。 |
| 3 | 性能与画质数字 | 历史轴引擎层实测数字（耗时 / 加速比 / SHA256 / 评分口径，含 `79.0 / 70.2 分`、`14/14`）均未在 CPU `1.0.0.2` 上重测，口径互不通用、勿混用；**当前版 `docs/design/` 5 份已全部清零，一律只在 `docs/archive/` 查**（`C1` 原件见 `docs/archive/c1-cpu-performance-20261106.md`）。第 4 批 4 份 `docs/design/design-*.md` 的结论同样来自历史轴归档头登记。2026-11-06 已在本轴重跑**引擎层性能 A/B 前后对比**（同批配对、24/24 自检通过）与**画质 golden A/B 复测**（8 帧 × 六档、硬判据 `6/6`；建议项两类比值仍未通过，不等于画质验收通过），判定见 `docs/CHANGELOG.md` §1.1 与 §2；**真机端到端帧率对拍已做（2026-11-06/07，无滤镜基线 + 滤镜开关 A/B + 遮挡序列链路验证，产物在 `05_验证/goldens/masks/e2e_*_20261106.*`），少核机器与多人脸场景仍未重跑**，本项因此不关闭。另：`1.0.0.2` 起默认开启人脸框时序 EMA，引入帧间状态、破坏逐字节确定性；复现上述画质 A/B 必须显式设 `BEAUTY_FACE_EMA=0 BEAUTY_FACE_HOLD=0`，回退自检见 `05_验证/goldens/masks/face_ema_ab_1002_20261106.md`。 |
| 4 | 已知遗留 | 旧入口记录的「磨皮=0 时锐化滑块无效」「浅色主题未复核」「美白补 6.5%」「祛斑痘/亮眼素材信号在噪声级」均属历史轴，需在当前代码上逐项复核是否仍存在。 |
| 5 | ~~旧版 GPU 移植计划~~ | ✅ **已关闭（第 2 批）**：`04_文档\方案A_GPU移植开发计划.md` 已归档为 `docs/archive/gpu-porting-plan-20261106.md`，文首标「与纯 CPU 方向冲突、从未开工、不得据此施工」。 |
| 6 | ~~`.gitignore` 构建产物规则~~ | ✅ **已关闭（提交 `e14f3f2`）**：已补 `02_构建/build_*/` 并回归 `check_upload.py`，详见 §6。 |
| 7 | 文档维护人 | 统一文档头的「维护人」暂缺，需指定。 |
| 8 | ~~引擎版本串未随版本轴递增~~ | ✅ **已根治（1.0.1.0）**：`beauty_core.cpp` 的 `CoreEngine::version()` 改为直接返回 `BEAUTY_BUILD_STR`，`obs-beauty-ui.cpp` 的 `BEAUTY_UI_VERSION` 也改为引用同一宏，两处硬编码消除；实测两件 DLL 内只剩 `1.0.1.0` 一个四段串。 |
| 9 | ~~路径口径冲突与执行环境阻断~~ | ✅ **全部关闭（C-1 + 2026-11-07 16:56 复跑）**：`obs-beauty.nsi` / `e2e_test.ps1` / `build_setup.ps1` / `install_1.0.0.3.bat` 已统一到 `C:\ProgramData\obs-studio\plugins\<插件目录名>\bin\64bit`，历史 `C:\Program Files\obs-studio\obs-plugins\64bit` 扁平布局废弃；用户关闭 OBS 并在管理员 `-NoProfile` 独立进程运行后，提权、OBS 占用、safe-delete 包装三项阻断均不复现，40 项断言全过。⚠️ **遗留**：历史扁平路径下仍有一个 `models\yunet.onnx` 残留（2026-11-07 16:57 实测），不属于本次判据、未清理，见 `docs\guides\guide-build-installer.md` §6 第 10 项。详见 `docs\CHANGELOG.md` §2。 |
| 10 | ~~同版本二次打包，是否递增版本待裁定~~ | ✅ **已裁定（用户选 A）**：按四段式「修 bug → 修订位 +1」升到 `1.0.1.0`，后两位归零；`BEAUTY_BUILD_STR`、UI、打包链、装机脚本、文档全链路同步，旧 `1.0.0.3` 产物保留为历史。 |
| 11 | **1.0.1.0 装卸回归的复跑前提** | `e2e_test.ps1` 的 A2 / B1 以 `$safetyMap`（测试前机上已装四件 MD5）为判据。本机现装 `1.0.0.3` 四件，而 `1.0.1.0` 包内两件 DLL 已重编，直接跑会出现多条 FAIL。**裁定（2026-11-08，用户选甲）**：不改任何断言，复跑前把 `02_构建\build_1.0.1.0\` 的两件 DLL 覆盖到 `C:\ProgramData\obs-studio\plugins\` 对应位置，使本机与包一致再跑；方案乙（改判据为「包内四件 MD5」）已否决。⚠️ **2026-11-08 实测新坑（文件级 ACL）**：两件已装 DLL 的 ACL 只给 `NT AUTHORITY\SYSTEM` / `BUILTIN\<user>s` = `FullControl`，`BUILTIN\Users` 仅 `ReadAndExecute, Synchronize`；父目录 ACL 另给 `BUILTIN\Users` 一个 `Write`，所以「新建探测文件成功」不等于「能覆盖已有 DLL」——会话内 `Copy-Item -Force` 实测报 `UnauthorizedAccessException`，**本机零改动**。WorkBuddy 会话 `IsElevated=False`，前置覆盖必须与 `e2e_test.ps1` 在同一管理员进程连续执行（NSIS `/S` 本身也要求 admin）。详见 `docs\CHANGELOG.md` §2 与 `docs\guides\guide-build-installer.md` §6 第 11 项。**2026-11-08 00:09 首次复跑实测（前置不满足的无效回归）**：用户运行 `e2e_test.ps1`，结果 **28 PASS / 12 FAIL**（Phase A 14/11、Phase B 14/1，`%TEMP%\obsbeauty_test\log.txt` 开头 00:09:28、结束行 00:09:38）。`safety` 备份的四件仍是 `1.0.0.3` 旧值（`88c54ecd…` / `cd5e3b3e…` / `4ae92eeb…` / `62076bfa…`），证明**前置覆盖未生效**；`A0 filter removed` / `A0 models dir removed` 也 FAIL，说明 Phase A 的删除动作没成功。12 条 FAIL 分三类：① 判据基准失配 3 条（A2 filter / A2 panel / B1 filter）；② `A0` 删除失败 2 条；③ 连带语义失效 7 条（`A2 ModelsCreated=1` 与 A3 六条删除断言）——models 目录没删掉，安装器判为「预先存在」并写 `ModelsCreated=0`，卸载器遂把旧四件当既有文件还原。**安装器本身表现正常**：两次 `setup exit code: 0`、`DisplayName` / `DisplayVersion` 均为 `1.0.1.0`，卸载后安装目录与两个 HKLM 键清空；终态四件与测试前逐位相同，无残留。**判定**：Phase A 已不再是「新机模拟」，本轮不得作为 `1.0.1.0` 的装卸验收结论。**裁定（2026-11-08，用户选方案一）**：不改任何仓库文件与断言，在管理员进程内依次做「提权自检 → 覆盖两件 DLL → 校验新 MD5 → 同进程调用 `e2e_test.ps1`」，复跑结果待回收。该次失败日志只留在 `%TEMP%`，因其为无效回归，不归档进 `05_验证\`。**2026-11-08 00:58 第二次复跑（方案一执行，有效验收）**：以提权封装在同一 High 完整性进程内完成「管理员自检 → OBS 进程自检 → 覆盖两件 DLL → 校验 MD5 → 同进程调用 `e2e_test.ps1`」，结果 **40 PASS / 0 FAIL**（Phase A 25/25、Phase B 15/15，`%TEMP%\obsbeauty_test\log.txt` 开头 00:58:46、结束行 00:58:55）。`safety` 备份的 filter 已为 `e34117…`、panel 已为 `ea79c0…`，证明**前置覆盖生效**；`A0 filter removed` / `A0 models dir removed` 由 FAIL 转 PASS，Phase A 恢复「新机模拟」语义。安装器两次 `setup exit code: 0`、`DisplayVersion` = `1.0.1.0`，卸载后安装目录与两个 HKLM 键清空；终态四件与本次测试前逐位相同。**判定**：本轮可作为 `1.0.1.0` 的装卸验收结论；日志逐字归档到 `05_验证/e2e_install_20261108.md`。注意装卸通过不等于功能可用——`1.0.1.0` 能否在 OBS 内加载出图仍未验证。 |

> 2026-11-06 裁定：评分公式与 `79.0 / 70.2 分` 等历史分数口径**不抽成当前版、不长期保留**；
> `qtmin.bat` / `build/qtmin.cpp` 全库检索无结果，不再列为待确认项。两者若需查证，只读历史原件见 `docs/archive/`。

---

## 9. 合并与归档记录（2026-11-06）

| 来源 | 处置 |
|---|---|
| 根 `README.md`（910 行结项归档版） | 全文保全到 `docs/archive/readme-archive-20261106.md`；本文按模板重写为结论先行的当前版 |
| `04_文档/README.md` | **已合并自**（2026-11-06）：架构一图流、帧管线、两个入口与面板动态控件、目录名坑、开源借鉴清单、已知遗留；原件归档为 `docs/archive/readme-entry-20261106.md` |
| `04_文档/验收报告_v3.1.39.md`、`验收报告_安装包v3.1.39.md` | 归档为历史版本验收记录（`docs/archive/`） |
| `04_文档/CHANGELOG_提交记录.md` | 2532 行流水账整体归档；里程碑提炼进 `docs/CHANGELOG.md` |
| `06_安装包/README_打包说明.md` | 按 CPU `1.0.0.0` 重写为 `docs/guides/guide-build-installer.md` |
| `04_文档/C1_CPU性能优化.md` | 首批补元数据、纠正过时路径，改为 `docs/design/design-cpu-performance.md`；**单独清理批（第 5 批）**又整篇重写为零历史数字口径，重写前全文逐字保全为 `docs/archive/c1-cpu-performance-20261106.md` |
| `04_文档/顶层菜单插件说明.md` | **已合并自**（2026-11-06，第 2 批）：改写为 `docs/guides/guide-ui.md`；保留机制 / 三个坑 / 目录名坑，按 CPU 宏分列菜单与角标口径，删除已失效的「底层 SDK 全局状态」限制 |
| `04_文档/方案A_GPU移植开发计划.md` | 第 2 批归档 `docs/archive/gpu-porting-plan-20261106.md`（与纯 CPU 方向冲突、从未开工） |
| `04_文档/面板使用说明.md` | 第 2 批归档 `docs/archive/ui-html-websocket-proposal-20261106.md`（未采用的 HTML+websocket 方案，引用脚本与路径全部不存在） |
| `04_文档/方案边界调整_开源可商用.md` | 第 2 批归档 `docs/archive/opensource-boundary-20261106.md`（§4「CPU 不能实时」结论已被实测推翻；许可判据 / 选型表 / 体积对比待第 3 批合并） |
| `04_文档/验收报告_v3.1.34.md`、`复刻评分_v3.1.39.md` | 第 2 批归档 `docs/archive/acceptance-quality-20261106.md`、`docs/archive/scorecard-20261106.md`（历史轴数字，CPU `1.0.0.0` 未重测） |
| `04_文档/开源参考仓库_对照与可复用清单.md` | 第 3 批归档 `docs/archive/oss-survey-20261106.md`（§0–3 / §5 的 GPU 化论证与纯 CPU 方向冲突；§4 许可证红线已并入当前版；§7 / §8 算法差异点待第 4 批引用） |
| `04_文档/D1_我们自己的技术线路.md` | 第 3 批归档 `docs/archive/tech-roadmap-20261106.md`（「不上 GPU」结论与当前方向一致；按 B 方案不另建 roadmap 当前版，证伪结论留归档头待第 4 批引用） |
| `04_文档/S1_掩码对拍结论.md`、`S2_磨皮核对拍结论.md`、`S3_对拍口径修正_结论.md` | 第 3 批归档 `docs/archive/ab-mask-20261106.md`、`docs/archive/ab-smooth-20261106.md`、`docs/archive/ab-metric-20261106.md`（`ab-*` 命名避开与 `D1` §4 步骤编号的同名异义；证伪 / 口径结论留归档头待第 4 批引用） |
| `docs/archive/opensource-boundary-20261106.md` §1 / §2、`oss-survey` §4 | **已合并自**（2026-11-06，第 3 批）：许可判据、选型表、许可证红线 → 新建 `docs/reference/reference-licensing.md`（仅许可部分，被推翻的 GPU 化结论未带入） |
| `docs/design/design-cpu-performance.md` §7 | 第 3 批增量更新：旧引用改指 `docs/archive/oss-survey-20261106.md` §3，补注「历史轴 GPU 化推算、不得据此施工」的有效性边界（**原文未删改、未润色**） |
| `04_文档/C2`~`C12`、`C14`~`C21`（19 篇） | **第 4A 批**（提交 `bca2d6f`）：`git mv` 到 `docs/archive/cNN-*-20261106.md`，逐篇加 `ARCHIVED` 头登记废弃原因、失效信息、仍有价值内容与当前版映射；正文逐字保全（CRLF 归一化后 19/19 MATCH），归档总数 15 → 34 |
| `docs/archive/c02` / `c04` / `c07` / `c08` / `c15` | **第 4B 批**：归并为 `docs/design/design-smoothing.md`（结论 / 开关 / 坑 / 证伪 / 失效说明） |
| `docs/archive/c06` / `c09` / `c11`（并引用 `c03`） | **第 4B 批**：归并为 `docs/design/design-tone-detail.md`；含三处「EMA」同名异义辨析 |
| `docs/archive/c03` / `c05` / `c12` / `c20` / `c21`（并引用 `ab-mask` / `c02` / `c19`） | **第 4B 批**：归并为 `docs/design/design-face-mask.md`；闭合 `c19` 根因被 `c20` 推翻、`c21` 落地的证伪链 |
| `docs/archive/c14` / `c16` / `c17` / `c18` / `c19`（并引用 `ab-metric` / `ab-smooth` / `c20` / `c21`） | **第 4B 批**：归并为 `docs/design/design-quality-findings.md`；只留证伪链与口径纪律，**不搬历史轴数字表格** |
| `docs/archive/c10-async-detect-20261106.md` | **第 4B 批**：并入 `docs/design/design-cpu-performance.md` 新增 §8（不新建 design 文件）；登记抢核副作用、确定性与 stagesurface 往返盲区 |
| 治理输出第 6 项（方案 B） | 新建 `05_验证/check_docs.py`（六条断言、纯标准库、只读、负向测试通过）；`docs/INDEX.md` §0 补统一文档头模板与自动校验规则、§5 补第 7 条提交前双闸门；本 README §2.4 / §5 同步。未引入 hook / CI，不改变提交行为 |
| 单独清理批（第 5 批，方案 B） | 新建 `docs/archive/c1-cpu-performance-20261106.md`（逐字保全重写前全文，含 `3.1.40` 修补附录 A）；整篇重写 `docs/design/design-cpu-performance.md`，删净历史加速比 / 耗时 / SHA256 / 离线 A/B 表，§8 异步检测按原文保留且编号不变；`05_验证/check_docs.py` 清空数字表格白名单并升 `0.1.1`；`docs/INDEX.md`、`docs/design/design-face-mask.md` 与本文 §5 / §8 / §9 同步。归档件 34 → 35，CPU 产品轴仍 `1.0.0.0` |
| `1.0.0.3` 交付链路对齐批（2026-11-07，方案 A + B） | 把 `06_安装包\build_setup.ps1`（取件目录 / 四个 `$*Ver` / 版本串自检 / 注释）、`obs-beauty.nsi`（兜底 define / 头注释）、`e2e_test.ps1`（`$Setup` 文件名）由 `1.0.0.2` 对齐到 `1.0.0.3`，生成 `OBS美颜_CPU_v1.0.0.3.exe`；本文 §0 / §2 / §4 / §5 / §8 / §9 与 `docs/CHANGELOG.md`、`docs/INDEX.md`、`docs/guides/guide-build-installer.md` 同步。**只改字符串与文档，未改源码、未重新编译、未跑装/卸回归**；新发现的 `CoreEngine::version()` 旧版本串登记为 §8 第 8 项 |
| `1.0.0.3` 装机脚本补齐批（2026-11-07，方案 C 前半） | 从 `03_装机\install_1.0.0.1.bat` 复制出 `install_1.0.0.3.bat`，只改标题、`SRCDIR=build_1.0.0.3` 与一段「两条链路路径不一致」的注释；保持纯 ASCII + CRLF（133 行、非 ASCII 字节 0）。`e2e_test.ps1` **没有执行**：实测发现非提权、路径口径冲突与 Phase A 递归删除三重阻断，登记为本文 §8 第 9 项与 `docs/guides/guide-build-installer.md` §6 第 8 项；`docs/CHANGELOG.md` §1 / §2、`docs/INDEX.md` §6 同步 |
| `1.0.0.3` 装机口径统一批（2026-11-07，用户裁定 **C-1**） | 把 `obs-beauty.nsi` 的 `$OBSDIR`、`.onInit` / `un.onInit` 路径推导、SecCore 目录创建、旧 SDK 清理路径、卸载目录链清理全部改到 `%ProgramData%\obs-studio\plugins\obs-beauty\bin\64bit`；`e2e_test.ps1` 的 `$OBSDIR`、`build_setup.ps1` 的 README.txt 四个路径与 `$Installed` 对照表、`install_1.0.0.3.bat` 的注释同步；顺手修正 README.txt 里 `09_安装包` → `06_安装包` 的过时路径。重新打包出同号 exe（3,638,687 B / `1c31531db60eee19130efc1fcc71ccf4`），旧同号包作废。静态核对四件 MD5 与判据自洽，但 **40 项装/卸断言在该批时点仍未执行**（同日 16:56 由用户手动补跑通过，见下一行），登记为本文 §8 第 9 / 10 项；`docs/CHANGELOG.md`、`docs/INDEX.md`、`docs/guides/guide-build-installer.md` 同步 |
| `1.0.0.3` 装卸回归验收批（2026-11-07 16:56） | 用户关闭 OBS 后以管理员 PowerShell 独立进程执行 `06_安装包\e2e_test.ps1`：Phase A「新机模拟 → 装 → 卸 → 归零」25 项、Phase B「升级覆盖 → 备份 → 还原」15 项，**40/40 PASS、0 FAIL**；卸载注册表 `DisplayName` = `OBS美颜 CPU 版 1.0.0.3（纯 CPU 滤镜 + 参数面板）`、`DisplayVersion` = `1.0.0.3`、`EstimatedSize` = 12250 KB；终态四件 MD5 与测试前一致，`C:\Program Files\obs-beauty` 与两个注册表键均不存在。日志 `%TEMP%\obsbeauty_test\log.txt`（"log.txt" l. 1–73）。**本批只做验收与文档同步，未改代码、未升版本号**；本文 §2.3 / §8 第 2 / 9 项 / §9、`docs\CHANGELOG.md` §1 / §2、`docs\INDEX.md` §6、`docs\guides\guide-build-installer.md` §5 / §6 第 4 / 8 / 10 项同步 |
| `1.0.1.0` 修订位升版批（2026-11-07，用户裁定 **A**） | `beauty_params.h` 的 `BEAUTY_BUILD_STR` → `1.0.1.0` 并把递增规则注释改为四段式；`beauty_core.cpp` 的 `CoreEngine::version()` 与 `obs-beauty-ui.cpp` 的 `BEAUTY_UI_VERSION` / 关于框版本轴均改为引用唯一出处；原生 PowerShell 调 `cl.exe` 重编两件 DLL 到 `02_构建\build_1.0.1.0\`；`build_setup.ps1` / `obs-beauty.nsi` / `e2e_test.ps1` 全链路升版，新增 `install_1.0.1.0.bat`（旧脚本保留）；重打包 `OBS美颜_CPU_v1.0.1.0.exe`（3,637,954 B / `e0684330f8f3b79a98c6752d1b365793`）。本文 §0 / §1 / §2 / §4 / §8 / §9、`docs\CHANGELOG.md`、`docs\INDEX.md`、`docs\guides\guide-build-installer.md` 同步。**装卸回归尚未在新包上复跑**，登记为 §8 第 2 / 11 项 |

---

*本文只描述 CPU `1.0.1.0` 当前有效结论。历史细节、评分口径、版本演进史、20 条雷区见 §9 所列归档件；
所有未在 §8 标注的「当前结论」均可在 `01_源码\`、`02_构建\`、`06_安装包\` 中逐字核对。
**许可为例外**：§0 只登记 `LICENSE` 的逐字内容，`docs/reference/reference-licensing.md` 只并列三处冲突，
两者都**不是对外许可结论**。*
