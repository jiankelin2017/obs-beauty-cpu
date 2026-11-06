# guide · 构建并打包 CPU 版安装包

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.0` |
| 最后更新 | 2026-11-06 |
| 适用代码版本 | CPU 线 `1.0.0.0`（提交 `5323856`） |
| 维护人 | 待人工确认 |
| 状态 | `Active` |
| 替代文档 | `docs/archive/acceptance-installer-20261106.md`（3.1.39 装/卸验收原件）；旧文 `06_安装包\README_打包说明.md` 已移入本文件重写 |

---

## 0. 一句话结论

**当前产物是 `06_安装包\OBS美颜_CPU_v1.0.0.0.exe`；打包脚本 `build_setup.ps1` 只从 `02_构建\build_1.0.0.0\` 取件，先做版本串自检，再经纯 ASCII 暂存目录调 NSIS 编译。旧版 `OBS美颜_Setup_v3.1.39.exe` 的路径、md5、版本值一律不适用。**

2026-11-06 实测：打包自检全绿，产物 **3,637,129 B**，Windows 版本资源 `ProductVersion` / `FileVersion` 均为**四段** `1.0.0.0`，`ProductName` = `OBS美颜 CPU 版`。
> NSIS 每次编译的时间戳/压缩顺序不同，**同一份源码连编两次 md5 也不同**；md5 只用于核对「这一次打出来的包」，不能当源码一致性证据。

---

## 1. 前置条件（缺一即失败）

| 项 | 路径 / 值 |
|---|---|
| 滤镜 DLL | `02_构建\build_1.0.0.0\obs-beauty.dll`（含 `1.0.0.0` 与 `obs_beauty_filter` 串） |
| 面板 DLL | `02_构建\build_1.0.0.0\obs-beauty-ui.dll`（含 `1.0.0.0` 串，**须由 `build-ui_320.bat` 带 `/DBEAUTY_UI_CPU_EDITION=1` 编出**） |
| ONNX Runtime | `05_验证\deps\runtime\onnxruntime.dll`（缺时回退 `参考文件\03_依赖与SDK_OBS\installer-stage\`） |
| YuNet 模型 | `05_验证\models\yunet.onnx`（同上回退） |
| NSIS | `C:\Program Files (x86)\NSIS\makensis.exe` |

> **别拿 `02_构建\build_output\` 里的 DLL 打包**——那是 3.1.40 / 3.1.39 历史定稿，版本串自检会直接报
> `does not contain '1.0.0.0' - it is a stale build`。这也是「独立产物目录」设计的目的：定稿 DLL 一个字节都不用动。

---

## 2. 操作（按顺序）

### 2.1 编译两件 DLL

```bat
set BEAUTY_OUTDIR=D:\插件\OBS美颜源码\02_构建\build_1.0.0.0
D:\插件\OBS美颜源码\02_构建\build_manual.bat
D:\插件\OBS美颜源码\02_构建\build-ui_320.bat
```

不设 `BEAUTY_OUTDIR` 时脚本仍输出到 `build_output\`（默认行为与历史一致）。
`build-ui_320.bat` 内已固定带 `/DBEAUTY_UI_CPU_EDITION=1`；不带该宏编出的 UI 没有 CPU 标识，属于另一种配置。

### 2.2 打包

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\插件\OBS美颜源码\06_安装包\build_setup.ps1"
# 保留暂存目录用于排查：
powershell -NoProfile -ExecutionPolicy Bypass -File "...\build_setup.ps1" -KeepStage
```

脚本按顺序做 7 件事：

1. 取上述 4 个源文件（`$BuildOut` 默认 `02_构建\build_1.0.0.0`，可用环境变量 **`BEAUTY_BUILD_OUT`** 覆盖）
2. **版本串自检**：滤镜与面板 DLL 里必须搜到 `1.0.0.0`，滤镜还须含 `obs_beauty_filter`；否则直接 `exit 1`（防「把上一版构建打进包，界面上看不出来」）
3. 与已装机文件对照 md5，**不一致只提示不阻断**（机器上跑的可能是另一版，这不是错误）
4. 暂存到 `$env:TEMP\obsbeauty_pkg`，路径必须**纯 ASCII**，否则 NSIS 报 `no files found`
5. 生成暂存目录 `docs\README.txt`（用户说明书）与 `docs\md5.txt`（四件文件清单）
6. 确保 `obs-beauty.nsi` 为 **UTF-8 with BOM**（否则中文界面乱码；脚本会自动补 BOM）
7. 调 `makensis` 编译，产物落到 `06_安装包\OBS美颜_CPU_v1.0.0.0.exe`，打印大小/md5/四件指纹，最后清掉暂存目录（`-KeepStage` 时保留）

### 2.3 版本号只改一处

`build_setup.ps1` 顶部四行，通过 `/D` 传给 nsi：

```powershell
$Ver       = '1.0.0.0'   # 包版本（产物文件名、控制面板显示）
$FilterVer = '1.0.0.0'   # 滤镜版本
$PanelVer  = '1.0.0.0'   # 面板版本
$CoreVer   = '1.0.0.0'   # 引擎版本（已并入 CPU 单轴，不再有独立 core 号）
```

唯一口径出处仍是 `01_源码\beauty_params.h` 的 `BEAUTY_BUILD_STR`。
`obs-beauty.nsi` 里的同名 `!ifndef` define 只是手工跑 `makensis` 时的兜底默认值，正常打包以 `/D` 为准。
**改版本必须同步**：`beauty_params.h` → 重新编译两件 DLL → 四个 `$*Ver` → `e2e_test.ps1` 的 `$Setup` 文件名 → `docs/CHANGELOG.md` → 根 `README.md`。

---

## 3. 三个编译期硬约束

| 约束 | 原因 | 脚本里的做法 |
|---|---|---|
| **源路径必须纯 ASCII** | NSIS 处理中文源路径报 `no files found` | 先复制到 `%TEMP%\obsbeauty_pkg`，`File` 只认暂存目录 |
| **`/DOUTFILE` 不能含中文** | makensis 按控制台代码页解析命令行，中文名变乱码文件名 | 先出 `OBSBeauty_CPU_Setup_v1.0.0.0.exe`，再用 PowerShell 复制改名为中文名 |
| **源文件自检必须在编译期** | `File` 是编译期把内容写进 exe 的，安装时不需要暂存目录，而脚本编完就清掉它 | nsi 里用 `!if ! /FileExists … !error`；写成运行时会导致安装直接 Abort（退出码 2） |

**四段版本号不能再补 `.0`**：`PKGVER` 已是 `1.0.0.0`，`VIProductVersion` / `FileVersion` 直接取 `${PKGVER}`；
沿用旧写法 `${PKGVER}.0` 会变成五段 `1.0.0.0.0`。

---

## 4. 包里装什么 / 装到哪

| 文件 | 装到 |
|---|---|
| `obs-beauty.dll` | `C:\Program Files\obs-studio\obs-plugins\64bit\` |
| `onnxruntime.dll` | 同上 |
| `models\yunet.onnx` | `…\obs-plugins\64bit\models\` |
| `obs-beauty-ui.dll` | `C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\` |

外加 `C:\Program Files\obs-beauty\` 下的 `README.txt`、`md5.txt`、卸载器。

> **不能改的两处位置**：`beauty_core.cpp` 的 `ensureReady()` 用 `selfDir()`（= 滤镜 DLL 所在目录）解析
> `onnxruntime.dll` 与 `models\yunet.onnx`。放错位置滤镜照样能加载，但**人脸检测静默失效 → 磨皮退化成全帧**，不报错，只对拍能看出。

包内**不含任何第三方商业 SDK**。安装包名、`Name` / `Caption` / `BrandingText` / `DisplayName` 均带 `CPU 版` 标识，
`FileDescription` 注明「纯 CPU，不依赖 GPU」。

---

## 5. 卸载

> **待人工确认**：CPU `1.0.0.0` 的 NSIS 卸载逻辑沿用 3.1.39 版本（本轮立轴只改了名称、版本与版本资源，未改卸载 Section），
> 且 `e2e_test.ps1` **尚未对新包跑过装/卸回归**。以下规则来自历史验收记录，需复跑确认后方可作为保证。

历史规则：「装之前什么样，卸完还是什么样」——装前有同名文件先备份、卸载时还原；装前没有则删除；
`models` 目录按是否本包创建决定删或留；`ui.ini` 默认保留；别的途径装的 SDK 目录一律不动。
支持 `/S` 静默卸载。卸载器同时注册进「程序和功能」与开始菜单。

一个语义提醒：备份还原的是「装这个包之前的状态」，装完后若又手动换过 DLL，卸载会把旧版本放回去。

---

## 6. 已知偏差与待人工确认项

| # | 项 | 说明 |
|---|---|---|
| 1 | **脚本生成的用户说明书路径过时** | `build_setup.ps1` 生成的 `README.txt` 末尾仍写 `09_安装包\build_setup.ps1` / `09_安装包\obs-beauty.nsi`，实际目录是 `06_安装包\`。本轮未改代码，待确认后修。 |
| 2 | **日志样例与实际不符** | 同一份 `README.txt` 里写 `init OK (v1.0.0.0, engine=core/1.0.0.0 …)`，而 `obs-beauty.cpp` 的 init 日志已改为 `init OK (CPU v…)`。按该样例去日志里找会找不到。待确认后修。 |
| 3 | 第三方 SDK 名称字样 | `README.txt` 仍出现某商业 SDK 的产品名，与「正文中性表述」的合规口径不一致。待人工确认。 |
| 4 | e2e 回归 | `06_安装包\e2e_test.ps1` 已指向新安装包名，但 CPU `1.0.0.0` 的真机装/卸两轮 40 项断言**未跑**。 |
| 5 | 图形界面 | 静默安装验证过落地行为，界面文字未逐页截图核对（UTF-8 BOM + `Unicode true` 沿用既有写法）。 |
| 6 | 环境边界 | 只支持 64 位 OBS；只认注册表 `HKLM\SOFTWARE\OBS Studio` 的(默认)值（缺失回退 `%ProgramFiles%\obs-studio`）；不做 OBS 版本兼容性判断。 |

---

*本文以 `06_安装包\build_setup.ps1`、`06_安装包\obs-beauty.nsi` 的当前内容为唯一真相源。
历史打包链路与踩坑记录（含 3.1.39 装/卸 40 项断言实测数据）见 `docs/archive/acceptance-installer-20261106.md`
及本机 `04_文档\C13_装机链路.md`（不入库）；当前版指南不重复保留历史验收数据。*
