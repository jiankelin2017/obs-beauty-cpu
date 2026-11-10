# guide · 构建并打包 CPU 版安装包

| 字段 | 值 |
|---|---|
| 版本 | `1.0.13.12` |
| 最后更新 | 2026-11-09 |
| 适用代码版本 | CPU 线 `1.0.13.12`（版本取自 `01_源码\beauty_params.h`） |
| 维护人 | Jian |
| 状态 | `Active` |
| 替代文档 | `docs/archive/acceptance-installer-20261106.md`（`Deprecated`）（3.1.39 装/卸验收原件）；旧文 `06_安装包\README_打包说明.md` 已移入本文件重写 |

> **归档重建声明（2026-11-10）**：`docs/archive/` 下 38 篇历史原件已按 `MANIFEST.tsv` 逐字恢复，
> MD5 与字节数 38/38 一致；文首均标「ARCHIVED · 已废弃，见 xxx」，状态 `Deprecated`、**不得据此施工**。
> 文中以 `docs/archive/` 开头的路径现在指向真实存在的归档件，读者可据此溯源，但不得当作现状引用。
> 有效结论（含正向与负向／证伪结论）只在唯一 Active 文档留存一份，去向总表见
> `docs/reference/reference-conclusions.md`；`docs/INDEX.md` §2 登记 38 行归档件。

---

## 0. 一句话结论

**当前口径（2026-11-09，`1.0.13.12`）**：版本号唯一出处是 `01_源码\beauty_params.h` 的
`BEAUTY_BUILD_STR`；`build_setup.ps1` 读它来定位 `02_构建\build_<版本>\`、做版本串自检、
生成 `06_安装包\OBS美颜_CPU_v<版本>.exe`，并通过 `/DPKGVER` 等传给 `obs-beauty.nsi`。
`obs-beauty.nsi` 与 `e2e_test.ps1` 都不再写死版本号（前者缺 `/D` 直接编译失败）。
**已打包的最新安装包是 `1.0.13.12`**（`OBS美颜_CPU_v1.0.13.12.exe`，3,643,148 B / MD5 `4cfbcb33d3729204e0c22f92b0a98c9d`；**装/卸 40 项回归已通过：2026-11-09 22:57，40 PASS / 0 FAIL（含 `PHASE R`）**；打包命令无参数，脚本自动从 `BEAUTY_BUILD_STR` 取版本、从 `02_构建\build_1.0.13.12\` 取件）。**`1.0.13.10` 曾有两份构建**：`build_1.0.13.10\` 是发布版（`/DBEAUTY_ENV_LOCK=1`，`BEAUTY_*` 覆盖一律失效，打包只用它），`build_1.0.13.10_dev\` 是同版本诊断版（不加锁，供 `05_验证` 台架做环境变量 A/B）；`build_setup.ps1` 只认 `build_<版本>`，不会误取诊断版。历史各版包体与 MD5 清单已归并到本文 §7（只读保全，不得当作当前值）。
按用户裁定 C-1，插件目标路径统一到 `%ProgramData%\obs-studio\plugins\<插件目录名>\bin\64bit\`。
脚本先做版本串自检，再经纯 ASCII 暂存目录调 NSIS 编译。

**历史背景（勿当当前值）**：`1.0.0.2` 起默认开启人脸框时序 EMA，离线复现历史 golden
基线须设 `BEAUTY_FACE_EMA=0 BEAUTY_FACE_HOLD=0`；`1.0.3.0` 时期打包脚本的默认取件目录
与版本串写死在 `02_构建\build_1.0.3.0\`，`v1.0.0.0.exe` 为立轴时前版产物。旧版
`OBS美颜_Setup_v3.1.39.exe` 的路径、md5、版本值一律不适用。

> NSIS 每次编译的时间戳/压缩顺序不同，**同一份源码连编两次 md5 也不同**；md5 只用于核对「这一次打出来的包」，不能当源码一致性证据。

---

## 1. 前置条件（缺一即失败）

| 项 | 路径 / 值 |
|---|---|
| 滤镜 DLL | `02_构建\build_<版本>\obs-beauty.dll`（当前 `1.0.13.12`：464,896 B，含 `1.0.13.12` 与 `obs_beauty_filter` 串；**MD5 不写死** —— 每次链接的 PE 时间戳都会变，同一份源码重编出的 MD5 就不同，一律用 `certutil -hashfile` 现场核对） |
| 面板 DLL | `02_构建\build_<版本>\obs-beauty-ui.dll`（当前 `1.0.13.12`：218,624 B，含 `1.0.13.12` 串，**须由 `build-ui_320.bat` 带 `/DBEAUTY_UI_CPU_EDITION=1` 编出**） |
| ONNX Runtime | `05_验证\deps\runtime\onnxruntime.dll`（缺时回退 `参考文件\03_依赖与SDK_OBS\installer-stage\`） |
| YuNet 模型 | `05_验证\models\yunet.onnx`（同上回退） |
| NSIS | `C:\Program Files (x86)\NSIS\makensis.exe` |

> **别拿 `02_构建\build_output\` 里的 DLL 打包**——那是 3.1.40 / 3.1.39 历史定稿，版本串自检会直接报
> `does not contain '<当前版本>' - it is a stale build`。这也是「独立产物目录」设计的目的：定稿 DLL 一个字节都不用动。

---

## 2. 操作（按顺序）

### 2.1 编译两件 DLL

```bat
set BEAUTY_OUTDIR=D:\插件\OBS美颜源码\02_构建\build_1.0.13.12
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

1. 从 `01_源码\beauty_params.h` 读 `BEAUTY_BUILD_STR` 定版本，取上述 4 个源文件（`$BuildOut` 默认 `02_构建\build_<版本>`，可用 `-BuildOut` 参数或环境变量 **`BEAUTY_BUILD_OUT`** 覆盖）
2. **版本串自检**：滤镜与面板 DLL 里必须搜到当前版本串，滤镜还须含 `obs_beauty_filter`；否则直接 `exit 1`（防「把上一版构建打进包，界面上看不出来」）
3. 与已装机文件对照 md5，**不一致只提示不阻断**（机器上跑的可能是另一版，这不是错误）
4. 暂存到 `$env:TEMP\obsbeauty_pkg`，路径必须**纯 ASCII**，否则 NSIS 报 `no files found`
5. 生成暂存目录 `docs\README.txt`（用户说明书）与 `docs\md5.txt`（四件文件清单）
6. 确保 `obs-beauty.nsi` 为 **UTF-8 with BOM**（否则中文界面乱码；脚本会自动补 BOM）
7. 调 `makensis` 编译，产物落到 `06_安装包\OBS美颜_CPU_v<版本>.exe`，打印大小/md5/四件指纹，最后清掉暂存目录（`-KeepStage` 时保留）

### 2.3 版本号只改一处

唯一口径是 `01_源码\beauty_params.h` 的 `BEAUTY_BUILD_STR`，打包链路里没有任何手抄的
版本号：

```powershell
# build_setup.ps1（读取，不定义版本）
$m = Select-String -LiteralPath $ParamsH -Pattern 'BEAUTY_BUILD_STR\s+"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"'
$Ver = if ($Version) { $Version } else { $m.Matches[0].Groups[1].Value }
# 产物目录 02_构建\build_$Ver、自检串 $Ver、/DPKGVER=$Ver 全部由它派生
```

`build_setup.ps1` 支持 `-Version`（会打印与源码不一致的 WARNING，用于复打历史包）和
`-BuildOut`。`obs-beauty.nsi` 里 `!ifndef PKGVER` 分支是 `!error`，**没有默认值**：
手工跑 `makensis` 必须显式传 `/DPKGVER=x.x.x.x`；`FILTERVER` / `PANELVER` /
`COREVER` 未传时自动跟随 `PKGVER`。以前这里写死 `1.0.3.0` 兜底，手工编译会静默
打出旧号包。`e2e_test.ps1` 用同一个 `BEAUTY_BUILD_STR` 推导被测 exe 名，需要测旧包时
设 `BEAUTY_E2E_SETUP` 指向那个 exe。

**升版顺序**：`beauty_params.h` → 重新编译两件 DLL 到 `02_构建\build_<版本>\` →
跑 `build_setup.ps1` → `03_装机\install_<版本>.bat` → `docs/CHANGELOG.md` → 根 `README.md`
→ 本指南 §0 的当前口径。2026-11-09 之前这里要求同步四个 `$*Ver` 和 `e2e_test.ps1`
的 `$Setup` 文件名，现在这两处会自动跟随源码，不要再手改。

---

## 3. 三个编译期硬约束

| 约束 | 原因 | 脚本里的做法 |
|---|---|---|
| **源路径必须纯 ASCII** | NSIS 处理中文源路径报 `no files found` | 先复制到 `%TEMP%\obsbeauty_pkg`，`File` 只认暂存目录 |
| **`/DOUTFILE` 不能含中文** | makensis 按控制台代码页解析命令行，中文名变乱码文件名 | 先出 `OBSBeauty_CPU_Setup_v<版本>.exe`，再由脚本复制改名为中文名 |
| **源文件自检必须在编译期** | `File` 是编译期把内容写进 exe 的，安装时不需要暂存目录，而脚本编完就清掉它 | nsi 里用 `!if ! /FileExists … !error`；写成运行时会导致安装直接 Abort（退出码 2） |

**四段版本号不能再补 `.0`**：`PKGVER` 已是 `1.0.13.1` 这样的四段式，`VIProductVersion` /
`FileVersion` 直接取 `${PKGVER}`；沿用旧写法 `${PKGVER}.0` 会变成五段。

---

## 4. 包里装什么 / 装到哪

| 文件 | 装到（2026-11-07 C-1 统一口径） |
|---|---|
| `obs-beauty.dll` | `C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\` |
| `onnxruntime.dll` | 同上 |
| `models\yunet.onnx` | `…\obs-beauty\bin\64bit\models\` |
| `obs-beauty-ui.dll` | `C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\` |

外加 `C:\Program Files\obs-beauty\` 下的 `README.txt`、`md5.txt`、卸载器与 `backup\`。
`InstallDir` 与 HKLM 注册表仍在原处，因此安装包仍声明 `RequestExecutionLevel admin`；
插件四件套本身不再写入 `C:\Program Files`。

> ✅ **口径已统一（用户裁定 C-1）**：`obs-beauty.nsi` / `e2e_test.ps1` / `build_setup.ps1` /
> `install_<版本>.bat` 现在都用本表这条 ProgramData 全局插件路径。
> 目录名 `obs-beauty` / `obs-beauty-ui` 必须与各自 DLL 主名一致，且 DLL 必须位于 `bin\64bit\` 下，
> 否则 OBS 静默跳过且不写日志（本指南 §3、"guide-ui.md" §3）。
> 历史轴 `C:\Program Files\obs-studio\obs-plugins\64bit\` 扁平布局已废弃，只在卸载器清理旧 SDK 目录时按历史路径引用。

> **不能改的两处位置**：`beauty_core.cpp` 的 `ensureReady()` 用 `selfDir()`（= 滤镜 DLL 所在目录）解析
> `onnxruntime.dll` 与 `models\yunet.onnx`。放错位置滤镜照样能加载，但**人脸检测静默失效 → 磨皮退化成全帧**，不报错，只对拍能看出。

包内**不含任何第三方商业 SDK**。安装包名、`Name` / `Caption` / `BrandingText` / `DisplayName` 均带 `CPU 版` 标识，
`FileDescription` 注明「纯 CPU，不依赖 GPU」。

---

## 5. 卸载

> ✅ **当前结论（2026-11-09）**：`1.0.13.12` 装/卸回归 40 PASS / 0 FAIL（含 `PHASE R`），证据 `05_验证/e2e_install_20261109_1312.md`；以下卸载规则对该版有效。
>
> 2026-11-07 的 `1.0.0.3` 历史验收原文已物理归并到本文 §7，不得当作当前版结论。

历史规则：「装之前什么样，卸完还是什么样」——装前有同名文件先备份、卸载时还原；装前没有则删除；
`models` 目录按是否本包创建决定删或留；`ui.ini` 默认保留；别的途径装的 SDK 目录一律不动。
支持 `/S` 静默卸载。卸载器同时注册进「程序和功能」与开始菜单。

一个语义提醒：备份还原的是「装这个包之前的状态」，装完后若又手动换过 DLL，卸载会把旧版本放回去。

---

## 6. 已知偏差与待人工确认项

> **时效声明（2026-11-10 文档治理）**：本表 1–11 项的历史状态只对其标注的日期与版本有效，
> **不得当作当前版结论**。逐次打包与复跑原文已物理归并到 §7（只读保全）；当前 `1.0.13.12` 的装/卸 40 项回归
> 已于 2026-11-09 22:57 通过（40 PASS / 0 FAIL，含 `PHASE R`），结论见 §0 与 `05_验证/e2e_install_20261109_1312.md`。

| # | 项 | 说明 |
|---|---|---|
| 1 | ~~脚本生成的用户说明书路径过时~~ | ✅ **已关闭（C-1）**：`build_setup.ps1` 生成的 `README.txt` 末尾已改为 `06_安装包\build_setup.ps1` / `06_安装包\obs-beauty.nsi`，四个安装路径也同步到 ProgramData。 |
| 2 | **日志样例与实际不符** | 同一份 `README.txt` 里写 `init OK (v1.0.0.0, engine=core/1.0.0.0 …)`，而 `obs-beauty.cpp` 的 init 日志已改为 `init OK (CPU v…)`。按该样例去日志里找会找不到。待确认后修。 |
| 3 | 第三方 SDK 名称字样 | `README.txt` 仍出现某商业 SDK 的产品名，与「正文中性表述」的合规口径不一致。待人工确认。 |
| 4 | ~~e2e 回归~~ | ✅ **已关闭（2026-11-07 16:56，属 `1.0.0.3` 包）**：40/40 PASS、0 FAIL；日志归档在 `05_验证/e2e_install_20261107.md`。⚠️ 该结论只对 `1.0.0.3` 有效，原文与逐次复跑细节见 §7；当前 `1.0.13.12` 见 §0。 |
| 5 | 图形界面 | 静默安装验证过落地行为，界面文字未逐页截图核对（UTF-8 BOM + `Unicode true` 沿用既有写法）。 |
| 6 | 环境边界 | 只支持 64 位 OBS；只认注册表 `HKLM\SOFTWARE\OBS Studio` 的(默认)值（缺失回退 `%ProgramFiles%\obs-studio`）；不做 OBS 版本兼容性判断。 |
| 7 | ~~滤镜 DLL 仍含旧版本串~~ | ✅ **已根治（1.0.1.0）**：`CoreEngine::version()` 改为返回 `BEAUTY_BUILD_STR`，UI 的 `BEAUTY_UI_VERSION` 也引用同一宏；实测两件 DLL 内只剩一个四段串。 |
| 8 | ~~路径口径冲突 + 执行环境阻断~~ | ✅ **已关闭（C-1）**：四处路径统一到 `%ProgramData%\obs-studio\plugins\<插件目录名>\bin\64bit`，40 项断言全过；历史扁平布局已废弃。归并前原文见 §7，遗留模型见第 10 项。 |
| 9 | ~~同版本二次打包，版本递增待裁定~~ | ✅ **已裁定（用户选 A）**：按四段式「修 bug → 修订位 +1」升 `1.0.1.0`，后两位归零；源码、两件 DLL、打包链、装机脚本、文档全链路同步，见根 `README.md` §9 与 `docs\CHANGELOG.md` §2。 |
| 10 | 历史扁平路径残留模型 | 2026-11-07 16:57 实测 `C:\Program Files\obs-studio\obs-plugins\64bit\models\yunet.onnx` 仍存在，而同目录的 `obs-beauty.dll` / `onnxruntime.dll` 已不存在。该文件属于历史轴装机遗留，不在 C-1 与本次 40 项判据覆盖范围内；本批**只读核对、未删除**（系统目录，需人工确认后再处理）。 |
| 11 | ~~1.0.1.0 装卸回归的复跑前提~~ | ✅ **已关闭（2026-11-08 00:58）**：在管理员 High 完整性进程内完成「覆盖两件 DLL → 校验 MD5 → 同进程调用 `e2e_test.ps1`」，40 PASS / 0 FAIL，日志归档在 `05_验证/e2e_install_20261108.md`；文件级 ACL 限制与 00:09 无效回归的逐字记录见 §7。 |

## 7. 历史打包与复跑记录（只读保全）

> **本节由 2026-11-10 文档治理物理归并生成**：以下各段是归并前 §0 / §5 / §6 的原文，
> **逐字搬入、未删改一字**；只对其标注的日期与版本有效，**不得据此施工，也不得当作当前版结论**。
> 当前有效口径见 §0 与 `05_验证/e2e_install_20261109_1312.md`。括号内为归并前的行号。

### 7.1 §0 历史各版包体与 MD5（原 L20 后半）

前一版 `1.0.13.11`（3,643,921 B / `2a992d2c…`）与 `1.0.13.10`（3,642,955 B / `385e0df749e9d4ddad2750ca198ecdc8`）、`1.0.13.9`（3,660,462 B / `7002dd6acb9070bed4dd436a54a5be53`）、`1.0.13.8`（3,659,749 B / `e79dbf522a5869297c06c369db06236a`）、`1.0.13.7`（3,659,515 B / `4c1b397ecd3a774f9af89d689343b95a`）、`1.0.13.6`（3,659,389 B / `3d5c1913447379cb2fb90904a15189ed`）、`1.0.13.5`（3,659,220 B / `001a9059214f0670ca3d382848eec531`）、`1.0.13.4`（3,654,548 B / `9980bd64702b89642d6c1f725ecda02b`）、`1.0.13.3`（3,655,173 B / `845ef17303c1b10ef9ddcc99b661d4cb`）、`1.0.13.1`（3,652,641 B / `9f669cbf3c91256fae46b5c97258a1e3`）保留。

### 7.2 §0 逐版打包实测（原 L29、L31）

2026-11-08 实测（`1.0.3.0` 修复重打包）：`build_setup.ps1` 版本串自检 `1.0.3.0` 全绿，`makensis` 编译成功，产物 **3,641,958 B**、MD5 `185927d8b6533f79a5de6a89e189aa5f`；Windows 版本资源 `ProductVersion` / `FileVersion` 均为**四段** `1.0.3.0`。包内四件：`obs-beauty.dll` 456,704 B / `470d636c…`、`obs-beauty-ui.dll` 218,624 B / `b3d09761…`、`onnxruntime.dll` / `cd5e3b3e…`、`yunet.onnx` / `4ae92eeb…`；两件 DLL 内均只剩 `1.0.3.0` 一个四段串。**该包未跑 40 项装卸回归**（`e2e_test.ps1` 的 `$safetyMap` 仍是机上 `1.0.0.3` 快照），见根 `README.md` §8 第 2 项。

2026-11-07 实测（`1.0.1.0` 升版重打包）：`build_setup.ps1` 版本串自检 `1.0.1.0` 全绿，`makensis` 编译成功，产物 **3,637,954 B**、MD5 `e0684330f8f3b79a98c6752d1b365793`；Windows 版本资源 `ProductVersion` / `FileVersion` 均为**四段** `1.0.1.0`，`ProductName` = `OBS美颜 CPU 版`。包内两件新 DLL 的 MD5 见 `docs\CHANGELOG.md` §2；两件 DLL 内均只剩 `1.0.1.0` 一个版本串。当日 `1.0.0.3` 的两次打包（3,639,172 B / `aeba502f…`、3,638,687 B / `1c31531d…`）均属历史，不可与本次产物混用。

### 7.3 §5 历史装卸验收（原 L150–L154）

> ✅ **2026-11-07 16:56 已装/卸实测**：用户关闭 OBS 后以管理员 PowerShell 独立进程跑完 `e2e_test.ps1`，
> **40/40 PASS、0 FAIL**；C-1 改过的卸载 Section（新增 `obs-beauty` 目录链 `RMDir`、旧 SDK 清理回退历史路径）
> 已由 A3 的 11 项删除断言与 B2 的 9 项断言（含 4 项备份还原）覆盖，见 `docs/CHANGELOG.md` §2 与本文 §6 第 4 项。
> 以下规则由此从「历史记录」升级为「实测通过」。
> ⚠️ **该验收属于 `1.0.0.3` 包**（2026-11-07 的历史结论）；此后各版回归见 §6 第 4 项，当前 `1.0.13.12` 的 40/40 见 §0 与 `05_验证/e2e_install_20261109_1312.md`。

### 7.4 §6 表内逐次记录（原 L176 / L180 / L183）

| 4 | ~~e2e 回归~~ | ✅ **已关闭（2026-11-07 16:56）**：`06_安装包\e2e_test.ps1` 在管理员 `-NoProfile` 独立进程执行，Phase A 25/25、Phase B 15/15，合计 **40/40 PASS、0 FAIL**；日志 `%TEMP%\obsbeauty_test\log.txt`（"log.txt" l. 1–73），终态四件 MD5 与测试前一致。此前「未跑」结论作废。⚠️ 该结论属于 `1.0.0.3` 包，`1.0.1.0` 待复跑（见第 11 项）；完整日志逐字归档在 `05_验证/e2e_install_20261107.md`。 |

| 8 | ~~路径口径冲突 + 执行环境阻断~~ | ✅ **全部关闭**：C-1 把 `obs-beauty.nsi` / `e2e_test.ps1` / `build_setup.ps1` / `install_1.0.0.3.bat` 统一到 `%ProgramData%\obs-studio\plugins\<插件目录名>\bin\64bit`，判据未改、四键齐全；用户关闭 OBS 并在管理员独立进程复跑后，提权被拦、OBS 占用、safe-delete 包装三项阻断均不复现，40 项断言全过（见第 4 项）。历史 `C:\Program Files\obs-studio\obs-plugins\64bit` 扁平布局废弃。遗留的历史残留模型见第 10 项。 |

| 11 | **1.0.1.0 装卸回归的复跑前提** | `e2e_test.ps1` 的 A2 / B1 以 `$safetyMap`（测试前机上已装四件 MD5）为判据；本机现装 `1.0.0.3` 四件，而新包两件 DLL 已重编，直接跑会出现多条 FAIL。**裁定（2026-11-08，用户选甲）**：不改任何断言，复跑前把 `02_构建\build_1.0.1.0\` 两件 DLL 覆盖到 ProgramData 对应位置；方案乙（改判据为「包内四件 MD5」）已否决。⚠️ **2026-11-08 实测新坑（文件级 ACL）**：两件已装 DLL 的 ACL 只给 `SYSTEM` / `BUILTIN\<user>s` `FullControl`，`BUILTIN\Users` 仅 `ReadAndExecute, Synchronize`，而父目录 ACL 另给 `BUILTIN\Users` 一个 `Write`——故「能新建探测文件」不等于「能覆盖 DLL」。WorkBuddy 会话 `IsElevated=False`，`Copy-Item -Force` 实测报 `UnauthorizedAccessException` 且**本机零改动**；前置覆盖必须与 `e2e_test.ps1` 在同一管理员进程连续执行。本批**未改任何断言**，详见 `docs\CHANGELOG.md` §2。**2026-11-08 00:09 首次复跑实测（前置不满足的无效回归）**：用户运行 `e2e_test.ps1`，结果 **28 PASS / 12 FAIL**（Phase A 14/11、Phase B 14/1，`%TEMP%\obsbeauty_test\log.txt` 开头 00:09:28、结束行 00:09:38）。`safety` 备份的四件仍是 `1.0.0.3` 旧值（`88c54ecd…` / `cd5e3b3e…` / `4ae92eeb…` / `62076bfa…`），证明**前置覆盖未生效**；`A0 filter removed` / `A0 models dir removed` 也 FAIL，说明 Phase A 的删除动作没成功。12 条 FAIL 分三类：① 判据基准失配 3 条（A2 filter / A2 panel / B1 filter）；② `A0` 删除失败 2 条；③ 连带语义失效 7 条（`A2 ModelsCreated=1` 与 A3 六条删除断言）——models 目录没删掉，安装器判为「预先存在」并写 `ModelsCreated=0`，卸载器遂把旧四件当既有文件还原。**安装器本身表现正常**：两次 `setup exit code: 0`、`DisplayName` / `DisplayVersion` 均为 `1.0.1.0`，卸载后安装目录与两个 HKLM 键清空；终态四件与测试前逐位相同，无残留。**判定**：Phase A 已不再是「新机模拟」，本轮不得作为 `1.0.1.0` 的装卸验收结论。**裁定（2026-11-08，用户选方案一）**：不改任何仓库文件与断言，在管理员进程内依次做「提权自检 → 覆盖两件 DLL → 校验新 MD5 → 同进程调用 `e2e_test.ps1`」，复跑结果待回收。该次失败日志只留在 `%TEMP%`，因其为无效回归，不归档进 `05_验证\`。**2026-11-08 00:58 第二次复跑（方案一执行，有效验收）**：以提权封装在同一 High 完整性进程内完成「管理员自检 → OBS 进程自检 → 覆盖两件 DLL → 校验 MD5 → 同进程调用 `e2e_test.ps1`」，结果 **40 PASS / 0 FAIL**（Phase A 25/25、Phase B 15/15，`%TEMP%\obsbeauty_test\log.txt` 开头 00:58:46、结束行 00:58:55）。`safety` 备份的 filter 已为 `e34117…`、panel 已为 `ea79c0…`，证明**前置覆盖生效**；`A0` 两条删除断言由 FAIL 转 PASS，Phase A 恢复「新机模拟」语义。两次 `setup exit code: 0`、`DisplayVersion` = `1.0.1.0`，卸载后安装目录与两个 HKLM 键清空；终态四件与本次测试前逐位相同。**判定**：本轮可作为 `1.0.1.0` 的装卸验收结论；日志逐字归档到 `05_验证/e2e_install_20261108.md`。**边界与后续补正（2026-11-08 01:04 / 01:15 实测）**：本次回归只覆盖静默装卸的文件与注册表逻辑，图形界面未逐页核对。后续两轮启动核实已确认 `1.0.1.0` 的模块与 UI 能在 OBS 32.1.1 内加载，插件完全卸除后 OBS 也正常启动退出；**后续补正（2026-11-08 01:24 实测）**：`1.0.1.0` 装回后启动 OBS 已实际出图，`frame#N drawn` 8 条、`GetDevice failed` 0 条（"2026-11-08 01-24-56.txt" l. 443–447），故「仅出图未验证」这句已失效；`1.0.3.0` 的真机加载、出图、自动方向补偿与片内 A/B 性能对照另见 `05_验证/ab_perf_20261108.md`。装卸通过不等于画质观感达标。 |

---

*本文以 `06_安装包\build_setup.ps1`、`06_安装包\obs-beauty.nsi` 的当前内容为唯一真相源。
历史打包链路与踩坑记录（含 3.1.39 装/卸 40 项断言实测数据）见 `docs/archive/acceptance-installer-20261106.md`（`Deprecated`）
及本机 `04_文档\C13_装机链路.md`（不入库）；当前版指南正文不重复保留历史验收数据；历史逐次打包与复跑记录见本文 §7。*
