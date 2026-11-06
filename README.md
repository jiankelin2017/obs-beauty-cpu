# OBS 美颜滤镜 · CPU 版

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.0` |
| 最后更新 | 2026-11-06 |
| 适用代码版本 | CPU 线 `1.0.0.0`（提交 `5323856`） |
| 维护人 | 待人工确认 |
| 状态 | `Active` |
| 替代文档 | `docs/archive/readme-archive-20261106.md`（910 行结项归档版全文）、`docs/archive/readme-entry-20261106.md`（旧仓库入口） |

> **本文是全库唯一 README。** 所有「当前有效结论」以 `docs/INDEX.md` 登记的路径为准；
> 同一主题不允许两份当前版并存，旧版一律进 `docs/archive/`。

---

## 0. 一句话结论

**这是一个纯 CPU 实现的 OBS 美颜滤镜插件，独立产品线版本 `1.0.0.0`；不引入自定义 shader / GPU 计算管线，美颜算法全部在 CPU buffer 上完成。**

| 关键事实 | 值 |
|---|---|
| 宿主 | OBS Studio 32.1.1（Windows 10/11 x64，64 位） |
| 滤镜 ID | `obs_beauty_filter`（**不得更改**，改了老场景里的滤镜会变成「缺失滤镜」） |
| 版本轴 | CPU 线 `1.0.0.0`（四段）／ GPU 版 `3.0.1`（三段，**另一仓库、另一条轴、不可互比**） |
| 版本号唯一出处 | `01_源码/beauty_params.h` 的 `BEAUTY_BUILD_STR` |
| UI 显式标识 | 编译期宏 `BEAUTY_UI_CPU_EDITION=1` 时，菜单「美颜·CPU(&A)」、窗口标题、蓝色 `CPU 版` 徽章、版本角标 `CPU v1.0.0.0`；默认 `0` 时行为零变化 |
| 当前构建产物 | `02_构建/build_1.0.0.0/`（`obs-beauty.dll` 441,856 B / `obs-beauty-ui.dll`） |
| 当前安装包 | `06_安装包/OBS美颜_CPU_v1.0.0.0.exe`（3,637,129 B，版本资源四段 `1.0.0.0`） |
| 许可 | 动态链接 libobs → **GPL-2.0**（`LICENSE`）。**许可口径存在冲突，见 §8 待人工确认项** |

---

## 1. 版本轴（先读，避免用错口径）

**CPU 线自 `1.0.0.0` 起另立，不是把 `3.1.40` 回退，也不是 `3.1.41`。**
历史 `3.1.x / core 1.4.x` 整条轴及其版本演进史、验收报告、产物 md5 已整体归档，不再作为现状口径。

| 线 | 版本 | 段数 | 仓库 | 说明 |
|---|---|---|---|---|
| **CPU（本仓库）** | `1.0.0.0` | 四段 | `D:\插件\OBS美颜源码` | 纯 CPU，本 README 适用 |
| GPU | `3.0.1` | 三段 | `D:\插件\OBS美颜GPU版` | 正式版，**只读参照，本轮所有改动均未触碰该库** |

递增规则（CPU 线）：普通升级第四位 +1（`1.0.0.1`）；大版本第一位 +1 其余归零（`2.0.0.0`）。
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

**CPU `1.0.0.0` 请用独立产物目录，不要覆盖 `build_output\` 里的 3.1.39 / 3.1.40 定稿 DLL：**

```bat
set BEAUTY_OUTDIR=D:\插件\OBS美颜源码\02_构建\build_1.0.0.0
build_manual.bat
build-ui_320.bat
```

工具链：MSVC 14.51.36231 + Windows SDK 10.0.26100.0 + `C:\Qt` + NSIS 3。
`vcvars64.bat` 在受限环境里因 `reg.exe` 被拦不可直接使用，需手工设置 `INCLUDE` / `LIB` / `PATH`（构建脚本内已硬编码探测逻辑）。
构建脚本按**内容探测**定位依赖目录（源码看 `obs-beauty.cpp`、SDK 看 `obs-studio-32.1.1\libobs`、验证目录看 `deps\runtime\include`），目录编号改动不会失效。

构建后自检：

```powershell
& python '02_构建\verify-ui-imports.py' '02_构建\build_1.0.0.0\obs-beauty-ui.dll'
```

### 2.2 打包

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "06_安装包\build_setup.ps1"
```

脚本默认从 `02_构建\build_1.0.0.0\` 取件（可用 `BEAUTY_BUILD_OUT` 覆盖），做版本串自检 `1.0.0.0` + `obs_beauty_filter`，暂存到纯 ASCII 临时目录，确保 `obs-beauty.nsi` 为 UTF-8 with BOM 后调 `makensis`，产物落到 `06_安装包\OBS美颜_CPU_v1.0.0.0.exe`。

**2026-11-06 实测**：滤镜与 UI 两种宏配置均编译通过；CPU 宏相关字符串（`[obs-beauty-ui][CPU]` / `beautyCpuTag` / `CPU v`）**只出现在 `=1` 版**；定稿 DLL 的 MD5 编译前后完全一致；安装包 `ProductVersion` / `FileVersion` 均为四段 `1.0.0.0`。

### 2.3 装机

> ⚠️ **待人工确认**：当前 `03_装机\` 下只有历史轴脚本（`install_3.1.39.bat` / `install_3.1.40.bat`），
> **尚无与 CPU `1.0.0.0` 对应的装机脚本**；CPU `1.0.0.0` 也尚未执行过真机装/卸验证。
> 在补齐之前，不要按历史脚本直接装机。已有安装包可双击安装，但装/卸回归需按 `06_安装包\e2e_test.ps1` 复跑。

装机通用约束（历史实测，仍适用于路径规则）：必须**手动提权**（受限进程写不进 `C:\Program Files`）；先关 OBS；`C:\ProgramData` 可写。
面板插件目录名必须与 DLL 名一致（`<目录名>\bin\64bit\<目录名>.dll`），名字对不上 OBS 会**静默跳过且不写日志**。

### 2.4 上传前自检（法务/隐私红线，务必执行）

```powershell
python 05_验证\check_upload.py            # 检查当前索引
python 05_验证\check_upload.py --staged   # 提交前检查暂存区
python 05_验证\check_upload.py --fix      # 移除「已跟踪但工作区已删」的残留条目
```

四道断言：索引一致性 · 法务红线（闭源商业资产）· 隐私红线（真人面部位图 / `.raw` 帧）· 体积红线（单文件 > 1 MB 应走 Release 附件）。

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
| `02_构建\` | 编译脚本、`build_output\`（历史定稿，**勿覆盖**）、`build_1.0.0.0\`（当前 CPU 产物）、`build_3.1.40\`（历史） |
| `03_装机\` | 装机/卸载与回滚脚本（**目前均为历史轴版本，见 §2.3**） |
| `04_文档\` | 尚未治理的分主题历史文档；**新文档不再放这里** |
| `05_验证\` | 离线验证脚本、goldens 真值、上传自检 |
| `06_安装包\` | NSIS 脚本 `obs-beauty.nsi`、打包脚本、装卸实测脚本、安装包产物 |
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
| CPU 性能设计 | `docs/design/design-cpu-performance.md` |
| 安装包构建指南 | `docs/guides/guide-build-installer.md` |
| 历史原件（只读） | `docs/archive/` |

**可信度顺序**：逐字源码 > 动态实测 > 推断 > 拟合（`01_源码\` > 本 README > `04_文档\`）。

---

## 6. 合规与红线

**`.gitignore` 是唯一的排除闸门。** 任何未在其中列出的文件**默认会被上传**——新增文件前必须先确认它不该公开，或先加规则再 `git add`。

| 绝不入库 | 位置 | 理由 |
|---|---|---|
| 闭源商业 SDK 二进制、对照提取物 | `参考文件\01_参考分析\`、`参考文件\03_依赖与SDK_OBS\` | 无再分发权（法务红线） |
| 含可识别真人面部的位图 / `.raw` 帧 | `05_验证\` | 隐私红线 |
| 构建中间产物 / `*.exe` / `*.obj` | `02_构建\*` | 可再生；正式产物走 Release 附件 |
| 含参考实现内部细节的 5 份文档 | `04_文档\01_第三方磨皮真值.md` 等（`.gitignore` §10） | 仅本机查证用 |

> ⚠️ **闸门待补**：`.gitignore` 目前只忽略 `02_构建/build_output/`，**新增的 `build_1.0.0.0/` 与历史 `build_3.1.40/` 不被忽略**，
> 2026-11-06 靠显式 `git add` 排除。是否补 `02_构建/build_*/` 见 §8 待人工确认项。

第三方组件：ONNX Runtime / YuNet（MIT，随包分发）、OBS Studio libobs（GPL-2.0，宿主，不随仓库分发）、
`07_开源参考\` 内 MIT 许可原文。GPL-2.0 参考仓库只读思路、未抄代码。完整出处与许可明细见
`docs/archive/readme-archive-20261106.md` §16。

---

## 7. 变更记录（当前版）

见 `docs/CHANGELOG.md`。历史逐提交流水账见 `docs/archive/changelog-raw-20261106.md`。

---

## 8. 待人工确认项（不得当作已确认结论使用）

| # | 项 | 说明 |
|---|---|---|
| 1 | **许可口径冲突** | 旧仓库入口声明「个人学习、研究与本地自用，不得商用或再分发」，根 README 历史版声明「动态链接 libobs → GPL-2.0 发布」。两者矛盾，需确定对外口径后再统一。 |
| 2 | CPU `1.0.0.0` 装机脚本 | `03_装机\` 无对应版本脚本；真机装/卸、`e2e_test.ps1` 对新包未跑过回归。 |
| 3 | 性能与画质数字 | `6.43 / 7.25 / 7.11 / 9.48 ms`、`79.0 / 70.2 分`、`14/14` 均为**历史轴引擎层口径**，未在 CPU `1.0.0.0` 上重测；口径互不通用，勿混用。 |
| 4 | 已知遗留 | 旧入口记录的「磨皮=0 时锐化滑块无效」「浅色主题未复核」「美白补 6.5%」「祛斑痘/亮眼素材信号在噪声级」均属历史轴，需在当前代码上逐项复核是否仍存在。 |
| 5 | 旧版 GPU 移植计划 | `04_文档\方案A_GPU移植开发计划.md` 与当前「纯 CPU」方向冲突，待后续批次归档。 |
| 6 | `.gitignore` 构建产物规则 | 是否补 `02_构建/build_*/`，补后需回归 `check_upload.py`。 |
| 7 | 文档维护人 | 统一文档头的「维护人」暂缺，需指定。 |

---

## 9. 合并与归档记录（2026-11-06）

| 来源 | 处置 |
|---|---|
| 根 `README.md`（910 行结项归档版） | 全文保全到 `docs/archive/readme-archive-20261106.md`；本文按模板重写为结论先行的当前版 |
| `04_文档/README.md` | **已合并自**（2026-11-06）：架构一图流、帧管线、两个入口与面板动态控件、目录名坑、开源借鉴清单、已知遗留；原件归档为 `docs/archive/readme-entry-20261106.md` |
| `04_文档/验收报告_v3.1.39.md`、`验收报告_安装包v3.1.39.md` | 归档为历史版本验收记录（`docs/archive/`） |
| `04_文档/CHANGELOG_提交记录.md` | 2532 行流水账整体归档；里程碑提炼进 `docs/CHANGELOG.md` |
| `06_安装包/README_打包说明.md` | 按 CPU `1.0.0.0` 重写为 `docs/guides/guide-build-installer.md` |
| `04_文档/C1_CPU性能优化.md` | 补元数据、纠正过时路径，改为 `docs/design/design-cpu-performance.md` |

---

*本文只描述 CPU `1.0.0.0` 当前有效结论。历史细节、评分口径、版本演进史、20 条雷区见 §9 所列归档件；
所有未在 §8 标注的「当前结论」均可在 `01_源码\`、`02_构建\`、`06_安装包\` 中逐字核对。*
