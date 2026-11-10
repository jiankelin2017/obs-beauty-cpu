# OBS 美颜滤镜 · CPU 版

| 字段 | 值 |
|---|---|
| 版本 | `1.0.14.0` |
| 最后更新 | 2026-11-09 |
| 适用代码版本 | CPU 线 `1.0.14.0`（提交见 git log） |
| 维护人 | Jian |
| 状态 | `Active` |


## 0. 一句话结论

**这是一个纯 CPU 实现的 OBS 美颜滤镜插件，独立产品线版本 `1.0.14.0`；不引入自定义 shader / GPU 计算管线，美颜算法全部在 CPU buffer 上完成。**



## 1. 版本轴（先读，避免用错口径）

**CPU 线自 `1.0.0.0` 起立


| 线 | 版本 | 段数 | 仓库 | 说明 |
|---|---|---|---|---|
| **CPU（本仓库）** | `1.0.14.0` | 四段 | `D:\插件\OBS美颜源码` | 纯 CPU，本 README 适用 |


版本递增规则（CPU 线，四段式 主.功能.修订.构建）

构建位 +1：注释/文档/重新打包等不影响行为的改动

修订位 +1，后两位归零：修 bug / 调默认值 / 优化速度，但不加新东西

功能位 +1，后两位归零：用户可见的新功能

主版位 +1，后三位归零：不兼容变更

低位不进位，跨档取高。

近期版本记录要点（1.0.2.0 → 1.0.14.0）：绝大多数为「修 bug → 修订位 +1」或「优化速度 → 修订位 +1」，画面多数逐字节不变；仅 1.0.5.0 属功能位 +1（头歪 45° 自动补偿）。1.0.13.10 → 1.0.13.11、1.0.13.11 → 1.0.13.12 经用户裁定走构建位 +1（按字面本可升 1.0.14.0，如实记、不反推规则）；1.0.13.12 → 1.0.14.0 于 2026-11-10 经裁定按四段式字面执行（修订位 +1、后两位归零），此前 1.0.13.x 第 4 位递增属历史裁定，不追溯改写。

其他：CoreEngine::version() 已并入单轴，不再维护独立 core 1.4.x 号。版本号同步位置：beauty_params.h → obs-beauty.cpp / obs-beauty-ui.cpp → build_setup.ps1 / obs-beauty.nsi / e2e_test.ps1 → docs/CHANGELOG.md。

口径提示：历史原件见 docs/archive/（2026-11-10 重建），有效结论见 docs/reference/reference-conclusions.md；根 README / 04_文档 中的 3.1.39 / 3.1.40 / core 1.4.x 只代表当时状态，不代表当前实现。

---

## 2. 快速开始（可执行）

### 2.1 构建

```bat
:: 在 02_构建\ 下，默认仍输出到 build_output\
build_manual.bat        :: 编译 obs-beauty.dll（滤镜 / CoreEngine）
build-ui_320.bat        :: 编译 obs-beauty-ui.dll（面板，脚本内定义 /DBEAUTY_UI_CPU_EDITION=1）
```

**请用独立产物目录 `02_构建\build_<版本>\`，不要覆盖 `build_output\` 里的历史定稿 DLL**（当前源码轴与最新已打包版均为 `1.0.14.0`）。以下代码块沿用 `1.0.3.0` 时期的路径示例；施工时把 `build_<版本>` 与 `install_<版本>.bat` 换成 `BEAUTY_BUILD_STR` 的当前值，构建与打包脚本会自动跟随，见 `docs/guides/guide-build-installer.md` §2。

```bat
set BEAUTY_OUTDIR=D:\插件\OBS美颜源码\02_构建\build_1.0.3.0
build_manual.bat
build-ui_320.bat
```

工具链：MSVC 14.51.36231 + Windows SDK 10.0.26100.0 + `C:\Qt` + NSIS 3。
`vcvars64.bat` 在受限环境里因 `reg.exe` 被拦不可直接使用，需手工设置 `INCLUDE` / `LIB` / `PATH`（构建脚本内已硬编码探测逻辑）。
构建脚本按**内容探测**定位依赖目录（源码看 `obs-beauty.cpp`、SDK 看 `obs-studio-32.1.1\libobs`、验证目录看 `deps\runtime\include`），目录编号改动不会失效。

构建后自检：

```powershell
& python '02_构建\verify-ui-imports.py' '02_构建\build_1.0.3.0\obs-beauty-ui.dll'
```

### 2.2 打包

`build_setup.ps1 安装包构建说明（简化）

调用：powershell -NoProfile -ExecutionPolicy Bypass -File "06_安装包\build_setup.ps1"

流程：从 01_源码\beauty_params.h 的 BEAUTY_BUILD_STR 读版本（2026-11-09 起源码是唯一出处）→ 定位 02_构建\build_<版本>\ 取件 → 自检版本串 <版本> + obs_beauty_filter → 将 /DPKGVER 等传入 obs-beauty.nsi → 产物落 06_安装包\OBS美颜_CPU_v<版本>.exe。可用 -Version / -BuildOut 或环境变量 BEAUTY_BUILD_OUT 覆盖。obs-beauty.nsi 缺 /DPKGVER 直接编译失败，不再有写死 1.0.3.0 的兜底。

实测记录

2026-11-09（1.0.13.0 正式重打包）：版本串自检通过；产物 3,652,694 B / MD5 409721014032b3e95f611ed8bc0e0269；ProductVersion / FileVersion = 1.0.13.0、ProductName = OBS美颜 CPU 版。包内四件：obs-beauty.dll 491,008 B、obs-beauty-ui.dll 218,624 B、运行时 DLL、模型文件（各附 MD5）。未跑 40 项装卸回归（e2e_test.ps1 已改为按 BEAUTY_BUILD_STR 自动选包，但需管理员进程且会增删 ProgramData 下插件与 HKLM 注册表键，本轮未执行）。

2026-11-07（1.0.1.0 升版重打包）：版本串自检 1.0.1.0 通过，makensis 编译成功；产物 3,637,954 B / MD5 e0684330f8f3b79a98c6752d1b365793；ProductVersion / FileVersion 均为四段 1.0.1.0。包内四件：obs-beauty.dll 447,488 B、obs-beauty-ui.dll 218,624 B、运行时 DLL、模型文件（各附 MD5）。两件新 DLL 内只剩 1.0.1.0 一个版本串，verify-ui-imports.py 五项导入全过。受工具安全策略限制，本轮用原生 PowerShell 直接调 cl.exe 编译（参数与 build_manual.bat / build-ui_320.bat 一致），未走 cmd.exe。

### 2.3 装机

安装/卸载回归与上传前自检

2026-11-07 16:56 装卸回归已实测通过：关闭 OBS 后以管理员 PowerShell 独立进程运行 e2e_test.ps1，Phase A 25 项 + Phase B 15 项，40/40 PASS、0 FAIL，done.flag 已写、日志以 0 failure(s) 结束；终态四件 MD5 与测试前逐一相同（"log.txt" l. 68–73）。

装机口径：按用户裁定 C-1 统一到 ProgramData（obs-beauty.nsi / e2e_test.ps1 / build_setup.ps1 / install_1.0.3.0.bat 四处一致），见 §8 第 9 项。

复跑方式：先完全关闭 OBS（含托盘），以管理员身份打开 PowerShell 执行
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\插件\OBS美颜源码\06_安装包\e2e_test.ps1"，结果写在 %TEMP%\obsbeauty_test\log.txt。

install_1.0.3.0.bat：部署到 C:\ProgramData\obs-studio\plugins\，且拒绝覆盖已有文件（符合预期时直接退出、不改动文件）；当前机插件状态以 05_验证/e2e_install_20261109_1312.md §5 实测为准（测试收尾态）。

通用装机约束（历史实测，路径规则仍适用）：必须手动提权（受限进程写不进 C:\Program Files）；先关 OBS；C:\ProgramData 可写。面板插件目录名必须与 DLL 名一致（<目录名>\bin\64bit\<目录名>.dll），对不上 OBS 会静默跳过且不写日志。

2.4 上传前自检（务必执行）
powershell
python 05_验证\check_upload.py            # 合规：检查当前索引
python 05_验证\check_upload.py --staged   # 合规：提交前检查暂存区
python 05_验证\check_upload.py --fix      # 合规：移除「已跟踪但工作区已删」的残留条目
python 05_验证\check_docs.py              # 文档：全量一致性自检
python 05_验证\check_docs.py --staged     # 文档：提交前模式，附列本次涉及的文档
提交前是双闸门，两条都要过：

check_upload.py 三道断言 = 索引一致性 · 闭源商业资产 · 体积红线（单文件 > 1 MB 应走 Release 附件）。

check_docs.py 九条断言 = Active 文档头六字段 · 归档件 ARCHIVED 头与替代指向 · docs/INDEX.md 双向登记 · docs/ 路径零断链 · 命名规范 · 当前版数字表格（只告警不阻断）· 版本轴一致性（唯一取自 BEAUTY_BUILD_STR）· 05_验证/ 引用零断链 · 总表「适用版本」列一致性（0.3.0 新增）。


例外规则

check_docs.py 只读、纯标准库、失败退出码 1；历史归档头里的「待第 N 批」措辞按已知历史标注放行。

第 7 / 8 / 9 条允许逐条登记带理由的例外，每次运行时打印清单。典型例外：

设计取证快照的头表版本与总表「适用版本」列，按定义记「最后一次内容复核版本」；

归档件可能指向已被清理的历史取证文件。

例外不等于放行：未登记的落后版本或新断链仍会阻断；已失效的例外也会提示移除。
---

## 3. 架构与帧管线

> 本节合并自 `docs/archive/readme-entry-20261106.md`（`Deprecated`） §3、§7（旧仓库入口说明）。

```
OBS Studio 32.1.1
└─ 视频源 → 滤镜链 → obs-beauty.dll · obs_beauty_filter
   └─ CoreEngine（纯 CPU，运行时不加载任何外部美颜组件）
      ├─ 人脸检测
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

色调整帧口径（1.0.2.0 起）：清晰 / 美白 / 红润三段是纯颜色表，改为整帧施加、不乘皮肤掩码（BEAUTY_TONE_GLOBAL=1，与 GPU 版同口径）；磨皮 / 锐化 / 五官仍只在皮肤掩码内。此改动针对「手遮脸时手背上出现一块美白」的成因，见 docs/CHANGELOG.md §2。

性能口径（1.0.13.0 真机实测，同会话配对）：1080p30、ROI≈480×305（约 147k 像素），分项 = 下载 2.07 + 检测掩码 0.67 + 磨皮 2.72 + 色调 0.46 + 细节 0.77 + 美形/alpha 0.86 + 上传 0.62 ≈ 8.34 ms/帧（S 组 24 个干净窗口的中位）。占 30 fps 预算（33.3 ms）的 25%、60 fps 预算（16.7 ms）的 50%。

跨会话绝对数一律不可比：同日 13:13 用同一份盒式代码测得磨皮 6.12 / 引擎 10.62，13:44 只有 3.12 / 5.97；逐段比值显示所有多线程段齐降约 1.8 倍，而唯一的单线程段（人脸检测 0.72 → 0.75）纹丝不动——是当时有后台进程抢核，不是代码也不是降频。因此早期 13.25、12.07、−1.40 的读数不再引用，真机结论只认「同一坐姿、同一会话、交替跑」的配对数据（live_matrix.py 已固定跑 S/F 两组）。
>
> | 版本 | 做法 | 效果 |
> |---|---|---|
> | `1.0.8.0` | 磨皮盒式并行粒度按块宽算、ROI 外拷贝并行、A 通道搬进引擎 | 磨皮 −2.5 ms |
> | `1.0.11.0` | 色调整数复合表（整帧模式下清晰→美白→红润对整数输入是纯函数） | 色调 4.56 → 0.84，**全链 −4.88（−27%）** |
> | `1.0.12.0` | A 通道并进色调写的 32 位存；`detailRefill` 跳过用不到的 7×7 中频盒式 | 台架 −1.69（−10.5%），真机按 ROI 对齐 −1.40（同会话口径存疑，见上） |
> | `1.0.13.0` | 磨皮盒式的水平趟三通道融合、垂直趟 SSE 一次 4 列（改的是 `surface3RgbBand` 走的 `bandBoxH/V`） | 台架全开 **−2.83（−18.7%）**；真机同会话 **磨皮 −0.40（−12.8%）、引擎 −0.37** |
>

关键结论

BEAUTY_ZERO_COPY=1（下载零拷贝）已实测证伪：下载段省 0.58 ms，但引擎 +0.41、上传 +0.19，合计反而慢 0.28——映射内存写合并/非缓存，而引擎在四个 pass 里反复读同一片输入。默认保持关，代码留作开关（换驱动/GPU 后可能不同）。

统计口径（三个坑）：

跨录制比引擎耗时必须先按 ROI 面积对齐——磨皮几乎完全由 ROI 决定（ROI 297×270→561×291 时磨皮 5.63→9.77）。只统计「无脸跳过 = 0」的窗口，无脸窗口会同比拉低各段。1.0.7.0 的 10.41 ms 旧基线是场景差异，已作废（原日志被轮转删除，无法复查）；1.0.10.0 的 H 组（= 1.0.7.0 配置）实测 19.02 ms。

抢核：录制前确认无台架/编译后台跑，特征是「多线程段一起慢 1.8 倍、单线程人脸检测不变」。判据看下载段——两组下载打平才说明同状态。

详见 docs/design/design-cpu-performance.md §2.7~§2.10 / §3.0 / §3.0b。

脖子口径（1.0.7.0 起）：脖子几何参数化到「立正方向」——u 沿画面正下方、v 横向，方向由 BEAUTY_INPUT_ROT / 自动探测的 g_effRot 决定。≤1.0.5.0 一律按源坐标 +y 往下画，源转 90/270° 时带子横向（横穿肩膀落到背景，真脖子没磨）；1.0.6.0 在旋转源上整段不画（止血）。BEAUTY_NECK=0 可无条件关脖子。取证 05_验证/ab20261109_neck_dir.md。

头歪口径（1.0.5.0 起）：人脸检测对平面内倾斜召回边界 30~40°，45° 歪头时要么无框、要么给「score 0.76 / 双眼间距仅框宽 28%」的敷衍框。1.0.5.0 在连续 8 次「无脸或框不像人脸」后试 ±45°，命中即记住倾角（FaceBox.roll），掩码按倾斜矩形画而非外接盒（45° 时外接盒面积是脸的 2.8 倍）。BEAUTY_AUTO_ROLL=0 整段关，逐字节回到 1.0.4.0；BEAUTY_AUTO_ROLL_MISS 调阈值（2~600）。取证 05_验证/ab20261109_head_roll.md。真机已验证（2026-11-09 上午，装机路径 + UGREEN 35867）：第 17.6 s 自动命中 +45°（score=0.871），之后无脸跳过全程 0，回正自动恢复，150 s 录制零丢帧（取证 05_验证/ab20261109_install_and_live.md）。同轮发现独立旧缺陷（未修）：源转 90/270° 时脖子仍按源 +y 画，立正画面里变横向——正立帧 27.9% 掩码落在脸框外（脖子没磨、窗帘肩膀被磨）。见 docs/design/design-head-roll.md §5。

输入方向口径（1.0.3.0 起）：OBS 场景项旋转只作用于显示合成，滤镜拿到原始帧。连续检不到脸时引擎自动试探 90°/270°，命中按该方向检测并把几何反变换回源坐标（BEAUTY_AUTO_ROT 默认开；已知方向可用 BEAUTY_INPUT_ROT=90/270 手工声明）。此层针对「竖屏摄像头美颜完全没效果」的成因，见 docs/CHANGELOG.md §2。

「纯 CPU」准确口径（2026-11-06 确认）：obs-beauty.cpp 中的 gs_texrender / gs_texture_* / gs_draw_sprite 是 OBS 滤镜框架唯一的帧 I/O 通道（源帧 → map 到 CPU buf_in → CPU 计算 → 回写 buf_out → 画回），不是 GPU 计算。验收标准是「不引入自定义 shader / hlsl / GPU 计算管线，美颜算法全部在 CPU buffer 上完成」，而非字面「无任何图形 API 调用」。01_源码 中无 gs_effect_create*、无 hlsl / effect 资产，唯一相关的是 OBS 内置 OBS_EFFECT_DEFAULT。

---

## 4. 目录地图

目录结构

目录	内容
01_源码\	自研引擎全部实现（.cpp/.h）
02_构建\	编译脚本；build_output\ 为历史定稿（勿覆盖）；build_1.0.13.12\ 最新已打包产物（补丁前），另有 1.0.12.0 / 1.0.11.0 / 1.0.10.0 / 1.0.9.0 / 1.0.8.0 / 1.0.7.0 / 1.0.6.0 / 1.0.5.0 / 1.0.4.0 / 1.0.3.0、1.0.0.2 / 1.0.0.1 / 1.0.0.0（前版）、build_3.1.40\（历史）
03_装机\	装机/卸载与回滚脚本；最新为 install_1.0.13.12.bat，装机路径已按 C-1 与 NSIS 安装包统一到 ProgramData（见 §2.3）
04_文档\	已清空（2026-11-09）：历史文档曾归档到 docs/archive\（该目录 2026-11-10 已移除），5 篇排除件移入 _quarantine\04_文档\；新文档不再放这里
_quarantine\	隔离区：5 篇已废弃但需本机溯源的旧文档，由 .gitignore 排除、不得对外分发；目录说明 _quarantine/README.md 随仓库入库
05_验证\	离线验证脚本、goldens 真值、上传自检
06_安装包\	NSIS 脚本 obs-beauty.nsi、build_setup.ps1、e2e_test.ps1、OBS美颜_CPU_v1.0.13.12.exe（最新已打包版）与历史各版安装包
参考文件\	外部依赖 / 对照资产 / 原始帧数据，仅本机保留，不入库
docs\	当前版文档体系（见 §5）

---

## 5. 文档体系

**总表：`docs/INDEX.md`**（主题｜路径｜类型｜状态｜适用版本｜维护人｜最后核对｜替代/归档）。

统一规则：固定分类 `README` / `design` / `guides` / `reference` / `CHANGELOG` / `adr` / `archive`；
主目录每类只留当前版，同一主题不允许两份并存；新文档只能放规定位置，命名 `类型-主题.md`；
归档件按 `主题-YYYYMMDD.md` 命名，文首标注「已废弃，见 xxx」及原因。

| 当前版 | 位置 |
文档索引

内容	路径
本 README（唯一）	README.md
变更日志（全局唯一）	docs/CHANGELOG.md
CPU 性能设计（含异步检测 §8；零历史实测数字）	docs/design/design-cpu-performance.md
磨皮：高低频分离与低频层路线	docs/design/design-smoothing.md
色调、clarity 与锐化	docs/design/design-tone-detail.md
肤色掩码、人脸框与五官局部	docs/design/design-face-mask.md
头歪 / 旋转源：方向、倾斜、脖子与 roll 锁定	docs/design/design-head-roll.md
画质对拍结论与证伪链	docs/design/design-quality-findings.md
安装包构建指南	docs/guides/guide-build-installer.md
顶层菜单与参数面板（UI）	docs/guides/guide-ui.md
历史原件	docs/archive/ 38 篇（2026-11-10 重建，逐字冷备另存仓库外）
可信度顺序：逐字源码 > 动态实测 > 推断 > 拟合（01_源码\ > 本 README > docs\ > _quarantine\）。

当前版数字口径（第 4 批起，2026-11-10 裁定）：docs/design/ 当前版只保留结论 / 开关 / 坑 / 证伪 / 失效说明，不搬历史轴数字表格；允许出现源码开关取值 / 编译期默认值，以及当前轴内部取证数字（见 design-cpu-performance.md §2.5–§2.11），后者须逐条注明时效与作废状态，且不得用于对外宣称或作为当前验收依据。扫参表、保留率、耗时、IoU 等历史实测数据不进当前版；历史原件见 docs/archive/（2026-11-10 重建；原 2026-11-06 删除裁定已由重建批取代）。开关名与默认值已按当前源码逐字复核，例如幅度门控上限是 freqMagHi、环境变量 BEAUTY_FREQ_MAG，不存在 BEAUTY_FREQ_MAG_HI。第 5 批已把最后一篇含历史数字表格的 design-cpu-performance.md 整篇重写，重写前全文（含 3.1.40 修补附录）见 docs/archive/c1-cpu-performance-20261106.md（Deprecated，2026-11-10 重建，不得据此施工）；至此 docs/design/ 当前版全部零历史实测数字（2026-11-09 拆出 design-head-roll.md 后为 6 份，同样不含验收数字），check_docs.py 的数字表格白名单也已清空。

防腐化：docs/INDEX.md §0 有统一文档头模板与自动校验规则，§4 有 9 条维护约定；check_docs.py（0.3.0）把「新增文档漏登记 INDEX / 归档件没写替代指向 / 改路径留断链 / 命名跑偏 / 升版本漏改头表 / 验证报告被删了引用还留着」变成提交前可拦截的断言。--staged 模式另提示工作区与暂存区分叉（只告警、不阻断），因为合规闸门读的是 git 索引。脚本自身版本与 CPU 产品版本轴互不相干（脚本 0.3.0，产品轴 1.0.14.0）。

6. 排除闸门
.gitignore 是唯一的排除闸门。 未在其中列出的文件默认会被上传——新增文件前必须先确认它不该公开，或先加规则再 git add。

绝不入库	位置	理由
闭源商业二进制、对照提取物	参考文件\01_参考分析\、参考文件\03_依赖与SDK_OBS\	无再分发权
本地测试素材位图 / .raw 帧	05_验证\	体积大、可再生
构建中间产物 / *.exe / *.obj	02_构建\*	可再生；正式产物走 Release 附件
隔离区 5 份旧文档	_quarantine\04_文档\（.gitignore §10）	仅本机查证用
✅ 闸门已补（2026-11-06，提交 e14f3f2）：规则由 02_构建/build_output/ 改为 02_构建/build_*/，覆盖 build_output\ / build_1.0.0.0\ / build_1.0.0.1\ / build_1.0.0.2\ / build_3.1.40\ 等全部版本化产物目录；带尾斜杠只匹配目录，不影响 build_manual.bat / build-ui_320.bat / build_log.txt / verify-ui-imports.py。已用 git check-ignore -v 与 check_upload.py 复核通过。新产物目录不再需显式 git add 规避，但提交前仍应跑 --staged 闸门。

---

## 7. 变更记录（当前版）

见 `docs/CHANGELOG.md`。历史逐提交流水账见 `docs/archive/changelog-raw-20261106.md`（`Deprecated`）。

---

## 8. 待人工确认项（不得当作已确认结论使用）

未关闭/已关闭事项

#	项	说明
2	~~装卸回归未在新包复跑~~	✅ 已关闭（1.0.13.9）：1.0.13.8（2026-11-09 17:24）、1.0.13.9（17:45）均 40 PASS / 0 FAIL（Phase A 25/25 + B 15/15），终态四件逐位还原。空档照实记：1.0.2.0~1.0.13.7 一次未跑，无同口径证据。复跑须满足第 11 项前提；$safetyMap 记的是「测试前机上已装 MD5」，装的不是待测包会因基准失配产生多条 FAIL。1.0.13.10 已跑完（19:02，40/0，同文件带 PHASE R 取证：卸载会把旧版插件还原回来）；1.0.13.11 修复验收（19:16，40/0；PHASE R backup 4→0 file(s)，R3 四件全 gone）；1.0.13.12 亦验收（22:57，40/0；[bak after R2] 0 file(s)、R3 全 gone）；画面逐字节对比与机器恢复未执行。
3	性能与画质数字	历史轴耗时/加速比/SHA256/评分口径未在本轴重测，原件见 docs/archive/，不得据此施工；当前版 docs/design/ 6 份已清零历史数字。1.0.0.2 起默认开人脸框时序 EMA，复现任何画质 A/B 必须显式设 BEAUTY_FACE_EMA=0 BEAUTY_FACE_HOLD=0。
4	已知遗留	「磨皮=0 时锐化滑块无效」「浅色主题未复核」「美白补 6.5%」「祛斑痘/亮眼素材信号在噪声级」四条为历史轴结论，须在当前代码逐项复核，未复核前不得引用。
5	~~旧版 GPU 移植计划~~	✅ 已关闭：归档 docs/archive/gpu-porting-plan-20261106.md（Deprecated），「与纯 CPU 方向冲突、从未开工、不得据此施工」。
6	~~.gitignore 构建产物规则~~	✅ 已关闭：已补 02_构建/build_*/ 并回归 check_upload.py。
7	~~文档维护人~~	✅ 已关闭（2026-11-09）：12 篇 Active 六字段头表「维护人」统一为 Jian，docs/INDEX.md §1／§2 已同步；模板示例与 05_验证/ 取证件不适用。
8	~~引擎版本串未随版本轴递增~~	✅ 已根治（1.0.1.0）：CoreEngine::version() 与 UI 版本串均引用 BEAUTY_BUILD_STR 单一出处。
9	~~路径口径冲突~~	✅ 已关闭：统一到 %ProgramData%\obs-studio\plugins\<插件目录名>\bin\64bit；⚠️ 历史扁平路径仍残留一个模型文件，属遗留未清理（guide-build-installer.md §6）。
10	~~同版本二次打包是否升版~~	✅ 已裁定：修 bug → 修订位 +1、后两位归零。1.0.13.0→1.0.13.1…1.0.13.9→1.0.13.10 均按此；1.0.13.10→1.0.13.11 走构建位 +1，是用户裁定特例（只改安装器，两份 DLL 体积逐位相同）；1.0.13.12→1.0.14.0 本轮按字面规则执行。
11	装卸回归复跑前提（新坑）	已装 DLL 的文件级 ACL 对 BUILTIN\Users 只给 ReadAndExecute：新建探测文件成功 ≠ 能覆盖已有 DLL，非提权 Copy-Item -Force 报 UnauthorizedAccessException（本机零改动）。前置覆盖必须与 e2e_test.ps1 在同一管理员进程内连续执行；NSIS /S 安装同样要求 admin。详见 guide-build-installer.md §6。
2026-11-06 裁定：评分公式与历史分数口径不抽成当前版、不长期保留；历史原件见 docs/archive/（2026-11-10 重建）。本节只登记未关闭事项与关闭结论；过程叙述见 docs/CHANGELOG.md §2 与 docs/archive/index-batchlog-20261109.md（Deprecated）。

9. 合并与归档记录（只留去向）
历史文档处置去向。过程叙述不在此：每批改了什么、为什么改见 docs/CHANGELOG.md；有效结论去向见 docs/reference/reference-conclusions.md；历史原件已全部删除（2026-11-10 重建）。

04_文档\ 目录已不存在（2026-11-09）。 最后 5 篇 .gitignore 排除件已移入 _quarantine\04_文档\，文首标「已废弃」，规则见 _quarantine/README.md。下表左列 04_文档/xxx 一律是已归档件原路径，只用于溯源，不代表当前还存在；现行替代见右列或 docs/INDEX.md。

原文档 / 来源	现址
04_文档/ 全部历史原件、docs/archive/ 38 篇归档件	2026-11-10 重建，见 docs/INDEX.md §2；有效结论唯一去向见 docs/reference/reference-conclusions.md 与 docs/INDEX.md §1
04_文档/C1_CPU性能优化.md	docs/design/design-cpu-performance.md
06_安装包/README_打包说明.md	docs/guides/guide-build-installer.md
04_文档/顶层菜单插件说明.md	docs/guides/guide-ui.md
04_文档/CHANGELOG_提交记录.md	里程碑提炼进 docs/CHANGELOG.md

## 10. 许可证

本项目以 **GNU General Public License v2.0** 发布，全文见根目录 [`LICENSE`](LICENSE)。

采用 GPL-2.0 的原因：可执行文件链接 OBS Studio 的 `libobs`（GPL-2.0），
分发衍生作品须以同一许可提供。源码全量位于 `01_源码\`，构建脚本位于 `02_构建\`、`06_安装包\`。

---

*本文只描述 CPU `1.0.14.0` 当前有效结论。历史细节、评分口径、版本演进史见 §9 所列归档件；
所有未在 §8 标注的「当前结论」均可在 `01_源码\`、`02_构建\`、`06_安装包\` 中逐字核对。
*
