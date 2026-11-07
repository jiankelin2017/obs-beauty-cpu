# guide · 构建并打包 CPU 版安装包

| 字段 | 值 |
|---|---|
| 版本 | `1.0.1.0` |
| 最后更新 | 2026-11-07 |
| 适用代码版本 | CPU 线 `1.0.1.0`（提交见 git log） |
| 维护人 | 待人工确认 |
| 状态 | `Active` |
| 替代文档 | `docs/archive/acceptance-installer-20261106.md`（3.1.39 装/卸验收原件）；旧文 `06_安装包\README_打包说明.md` 已移入本文件重写 |

---

## 0. 一句话结论

**`1.0.0.2` 起默认开启人脸框时序 EMA，产物输出带帧间状态；离线复现历史 golden 基线须设 `BEAUTY_FACE_EMA=0 BEAUTY_FACE_HOLD=0`。打包脚本 `build_setup.ps1` 的默认取件目录与版本串已切到 `1.0.1.0`（`02_构建\build_1.0.1.0\`）；当前安装包为 `06_安装包\OBS美颜_CPU_v1.0.1.0.exe`（2026-11-07 C-1 重打包版），`v1.0.0.0.exe` 为立轴时前版产物。按用户裁定 C-1，`obs-beauty.nsi` / `e2e_test.ps1` / 本打包脚本 / `install_1.0.1.0.bat` 的插件目标路径已统一到 `%ProgramData%\obs-studio\plugins\<插件目录名>\bin\64bit\`。脚本先做版本串自检，再经纯 ASCII 暂存目录调 NSIS 编译。旧版 `OBS美颜_Setup_v3.1.39.exe` 的路径、md5、版本值一律不适用。**

2026-11-07 实测（`1.0.1.0` 升版重打包）：`build_setup.ps1` 版本串自检 `1.0.1.0` 全绿，`makensis` 编译成功，产物 **3,637,954 B**、MD5 `e0684330f8f3b79a98c6752d1b365793`；Windows 版本资源 `ProductVersion` / `FileVersion` 均为**四段** `1.0.1.0`，`ProductName` = `OBS美颜 CPU 版`。包内两件新 DLL 的 MD5 见 `docs\CHANGELOG.md` §2；两件 DLL 内均只剩 `1.0.1.0` 一个版本串。当日 `1.0.0.3` 的两次打包（3,639,172 B / `aeba502f…`、3,638,687 B / `1c31531d…`）均属历史，不可与本次产物混用。
> NSIS 每次编译的时间戳/压缩顺序不同，**同一份源码连编两次 md5 也不同**；md5 只用于核对「这一次打出来的包」，不能当源码一致性证据。

---

## 1. 前置条件（缺一即失败）

| 项 | 路径 / 值 |
|---|---|
| 滤镜 DLL | `02_构建\build_1.0.1.0\obs-beauty.dll`（447,488 B / `e34117c88501956963c6c6f9370682d7`，含 `1.0.1.0` 与 `obs_beauty_filter` 串；**旧版本串残留已根治**） |
| 面板 DLL | `02_构建\build_1.0.1.0\obs-beauty-ui.dll`（218,624 B / `ea79c0dca53d1e8e5ea08b958ad3fe40`，含 `1.0.1.0` 串，**须由 `build-ui_320.bat` 带 `/DBEAUTY_UI_CPU_EDITION=1` 编出**） |
| ONNX Runtime | `05_验证\deps\runtime\onnxruntime.dll`（缺时回退 `参考文件\03_依赖与SDK_OBS\installer-stage\`） |
| YuNet 模型 | `05_验证\models\yunet.onnx`（同上回退） |
| NSIS | `C:\Program Files (x86)\NSIS\makensis.exe` |

> **别拿 `02_构建\build_output\` 里的 DLL 打包**——那是 3.1.40 / 3.1.39 历史定稿，版本串自检会直接报
> `does not contain '1.0.1.0' - it is a stale build`。这也是「独立产物目录」设计的目的：定稿 DLL 一个字节都不用动。

---

## 2. 操作（按顺序）

### 2.1 编译两件 DLL

```bat
set BEAUTY_OUTDIR=D:\插件\OBS美颜源码\02_构建\build_1.0.1.0
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

1. 取上述 4 个源文件（`$BuildOut` 默认 `02_构建\build_1.0.1.0`，可用环境变量 **`BEAUTY_BUILD_OUT`** 覆盖）
2. **版本串自检**：滤镜与面板 DLL 里必须搜到 `1.0.1.0`，滤镜还须含 `obs_beauty_filter`；否则直接 `exit 1`（防「把上一版构建打进包，界面上看不出来」）
3. 与已装机文件对照 md5，**不一致只提示不阻断**（机器上跑的可能是另一版，这不是错误）
4. 暂存到 `$env:TEMP\obsbeauty_pkg`，路径必须**纯 ASCII**，否则 NSIS 报 `no files found`
5. 生成暂存目录 `docs\README.txt`（用户说明书）与 `docs\md5.txt`（四件文件清单）
6. 确保 `obs-beauty.nsi` 为 **UTF-8 with BOM**（否则中文界面乱码；脚本会自动补 BOM）
7. 调 `makensis` 编译，产物落到 `06_安装包\OBS美颜_CPU_v1.0.1.0.exe`，打印大小/md5/四件指纹，最后清掉暂存目录（`-KeepStage` 时保留）

### 2.3 版本号只改一处

`build_setup.ps1` 顶部四行，通过 `/D` 传给 nsi：

```powershell
$Ver       = '1.0.1.0'   # 包版本（产物文件名、控制面板显示）
$FilterVer = '1.0.1.0'   # 滤镜版本
$PanelVer  = '1.0.1.0'   # 面板版本
$CoreVer   = '1.0.1.0'   # 引擎版本（已并入 CPU 单轴，不再有独立 core 号）
```

唯一口径出处仍是 `01_源码\beauty_params.h` 的 `BEAUTY_BUILD_STR`。
`obs-beauty.nsi` 里的同名 `!ifndef` define 只是手工跑 `makensis` 时的兜底默认值，正常打包以 `/D` 为准。
**改版本必须同步**：`beauty_params.h` → 重新编译两件 DLL → 四个 `$*Ver` → `e2e_test.ps1` 的 `$Setup` 文件名 → `docs/CHANGELOG.md` → 根 `README.md`。

---

## 3. 三个编译期硬约束

| 约束 | 原因 | 脚本里的做法 |
|---|---|---|
| **源路径必须纯 ASCII** | NSIS 处理中文源路径报 `no files found` | 先复制到 `%TEMP%\obsbeauty_pkg`，`File` 只认暂存目录 |
| **`/DOUTFILE` 不能含中文** | makensis 按控制台代码页解析命令行，中文名变乱码文件名 | 先出 `OBSBeauty_CPU_Setup_v1.0.1.0.exe`，再用 PowerShell 复制改名为中文名 |
| **源文件自检必须在编译期** | `File` 是编译期把内容写进 exe 的，安装时不需要暂存目录，而脚本编完就清掉它 | nsi 里用 `!if ! /FileExists … !error`；写成运行时会导致安装直接 Abort（退出码 2） |

**四段版本号不能再补 `.0`**：`PKGVER` 已是 `1.0.1.0`，`VIProductVersion` / `FileVersion` 直接取 `${PKGVER}`；
沿用旧写法 `${PKGVER}.0` 会变成五段 `1.0.1.0.0`。

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
> `install_1.0.1.0.bat` 现在都用本表这条 ProgramData 全局插件路径。
> 目录名 `obs-beauty` / `obs-beauty-ui` 必须与各自 DLL 主名一致，且 DLL 必须位于 `bin\64bit\` 下，
> 否则 OBS 静默跳过且不写日志（本指南 §3、"guide-ui.md" §3）。
> 历史轴 `C:\Program Files\obs-studio\obs-plugins\64bit\` 扁平布局已废弃，只在卸载器清理旧 SDK 目录时按历史路径引用。

> **不能改的两处位置**：`beauty_core.cpp` 的 `ensureReady()` 用 `selfDir()`（= 滤镜 DLL 所在目录）解析
> `onnxruntime.dll` 与 `models\yunet.onnx`。放错位置滤镜照样能加载，但**人脸检测静默失效 → 磨皮退化成全帧**，不报错，只对拍能看出。

包内**不含任何第三方商业 SDK**。安装包名、`Name` / `Caption` / `BrandingText` / `DisplayName` 均带 `CPU 版` 标识，
`FileDescription` 注明「纯 CPU，不依赖 GPU」。

---

## 5. 卸载

> ✅ **2026-11-07 16:56 已装/卸实测**：用户关闭 OBS 后以管理员 PowerShell 独立进程跑完 `e2e_test.ps1`，
> **40/40 PASS、0 FAIL**；C-1 改过的卸载 Section（新增 `obs-beauty` 目录链 `RMDir`、旧 SDK 清理回退历史路径）
> 已由 A3 的 11 项删除断言与 B2 的 9 项断言（含 4 项备份还原）覆盖，见 `docs/CHANGELOG.md` §2 与本文 §6 第 4 项。
> 以下规则由此从「历史记录」升级为「实测通过」。
> ⚠️ **该验收属于 `1.0.0.3` 包**；`1.0.1.0` 重编了两件 DLL、尚未复跑装/卸回归，见本文 §6 第 11 项。

历史规则：「装之前什么样，卸完还是什么样」——装前有同名文件先备份、卸载时还原；装前没有则删除；
`models` 目录按是否本包创建决定删或留；`ui.ini` 默认保留；别的途径装的 SDK 目录一律不动。
支持 `/S` 静默卸载。卸载器同时注册进「程序和功能」与开始菜单。

一个语义提醒：备份还原的是「装这个包之前的状态」，装完后若又手动换过 DLL，卸载会把旧版本放回去。

---

## 6. 已知偏差与待人工确认项

| # | 项 | 说明 |
|---|---|---|
| 1 | ~~脚本生成的用户说明书路径过时~~ | ✅ **已关闭（C-1）**：`build_setup.ps1` 生成的 `README.txt` 末尾已改为 `06_安装包\build_setup.ps1` / `06_安装包\obs-beauty.nsi`，四个安装路径也同步到 ProgramData。 |
| 2 | **日志样例与实际不符** | 同一份 `README.txt` 里写 `init OK (v1.0.0.0, engine=core/1.0.0.0 …)`，而 `obs-beauty.cpp` 的 init 日志已改为 `init OK (CPU v…)`。按该样例去日志里找会找不到。待确认后修。 |
| 3 | 第三方 SDK 名称字样 | `README.txt` 仍出现某商业 SDK 的产品名，与「正文中性表述」的合规口径不一致。待人工确认。 |
| 4 | ~~e2e 回归~~ | ✅ **已关闭（2026-11-07 16:56）**：`06_安装包\e2e_test.ps1` 在管理员 `-NoProfile` 独立进程执行，Phase A 25/25、Phase B 15/15，合计 **40/40 PASS、0 FAIL**；日志 `%TEMP%\obsbeauty_test\log.txt`（"log.txt" l. 1–73），终态四件 MD5 与测试前一致。此前「未跑」结论作废。⚠️ 该结论属于 `1.0.0.3` 包，`1.0.1.0` 待复跑（见第 11 项）；完整日志逐字归档在 `05_验证/e2e_install_20261107.md`。 |
| 5 | 图形界面 | 静默安装验证过落地行为，界面文字未逐页截图核对（UTF-8 BOM + `Unicode true` 沿用既有写法）。 |
| 6 | 环境边界 | 只支持 64 位 OBS；只认注册表 `HKLM\SOFTWARE\OBS Studio` 的(默认)值（缺失回退 `%ProgramFiles%\obs-studio`）；不做 OBS 版本兼容性判断。 |
| 7 | ~~滤镜 DLL 仍含旧版本串~~ | ✅ **已根治（1.0.1.0）**：`CoreEngine::version()` 改为返回 `BEAUTY_BUILD_STR`，UI 的 `BEAUTY_UI_VERSION` 也引用同一宏；实测两件 DLL 内只剩一个四段串。 |
| 8 | ~~路径口径冲突 + 执行环境阻断~~ | ✅ **全部关闭**：C-1 把 `obs-beauty.nsi` / `e2e_test.ps1` / `build_setup.ps1` / `install_1.0.0.3.bat` 统一到 `%ProgramData%\obs-studio\plugins\<插件目录名>\bin\64bit`，判据未改、四键齐全；用户关闭 OBS 并在管理员独立进程复跑后，提权被拦、OBS 占用、safe-delete 包装三项阻断均不复现，40 项断言全过（见第 4 项）。历史 `C:\Program Files\obs-studio\obs-plugins\64bit` 扁平布局废弃。遗留的历史残留模型见第 10 项。 |
| 9 | ~~同版本二次打包，版本递增待裁定~~ | ✅ **已裁定（用户选 A）**：按四段式「修 bug → 修订位 +1」升 `1.0.1.0`，后两位归零；源码、两件 DLL、打包链、装机脚本、文档全链路同步，见根 `README.md` §9 与 `docs\CHANGELOG.md` §2。 |
| 10 | 历史扁平路径残留模型 | 2026-11-07 16:57 实测 `C:\Program Files\obs-studio\obs-plugins\64bit\models\yunet.onnx` 仍存在，而同目录的 `obs-beauty.dll` / `onnxruntime.dll` 已不存在。该文件属于历史轴装机遗留，不在 C-1 与本次 40 项判据覆盖范围内；本批**只读核对、未删除**（系统目录，需人工确认后再处理）。 |
| 11 | **1.0.1.0 装卸回归的复跑前提** | `e2e_test.ps1` 的 A2 / B1 以 `$safetyMap`（测试前机上已装四件 MD5）为判据；本机现装 `1.0.0.3` 四件，而新包两件 DLL 已重编，直接跑会出现多条 FAIL。**裁定（2026-11-08，用户选甲）**：不改任何断言，复跑前把 `02_构建\build_1.0.1.0\` 两件 DLL 覆盖到 ProgramData 对应位置；方案乙（改判据为「包内四件 MD5」）已否决。⚠️ **2026-11-08 实测新坑（文件级 ACL）**：两件已装 DLL 的 ACL 只给 `SYSTEM` / `BUILTIN\<user>s` `FullControl`，`BUILTIN\Users` 仅 `ReadAndExecute, Synchronize`，而父目录 ACL 另给 `BUILTIN\Users` 一个 `Write`——故「能新建探测文件」不等于「能覆盖 DLL」。WorkBuddy 会话 `IsElevated=False`，`Copy-Item -Force` 实测报 `UnauthorizedAccessException` 且**本机零改动**；前置覆盖必须与 `e2e_test.ps1` 在同一管理员进程连续执行。本批**未改任何断言**，详见 `docs\CHANGELOG.md` §2。**2026-11-08 00:09 首次复跑实测（前置不满足的无效回归）**：用户运行 `e2e_test.ps1`，结果 **28 PASS / 12 FAIL**（Phase A 14/11、Phase B 14/1，`%TEMP%\obsbeauty_test\log.txt` 开头 00:09:28、结束行 00:09:38）。`safety` 备份的四件仍是 `1.0.0.3` 旧值（`88c54ecd…` / `cd5e3b3e…` / `4ae92eeb…` / `62076bfa…`），证明**前置覆盖未生效**；`A0 filter removed` / `A0 models dir removed` 也 FAIL，说明 Phase A 的删除动作没成功。12 条 FAIL 分三类：① 判据基准失配 3 条（A2 filter / A2 panel / B1 filter）；② `A0` 删除失败 2 条；③ 连带语义失效 7 条（`A2 ModelsCreated=1` 与 A3 六条删除断言）——models 目录没删掉，安装器判为「预先存在」并写 `ModelsCreated=0`，卸载器遂把旧四件当既有文件还原。**安装器本身表现正常**：两次 `setup exit code: 0`、`DisplayName` / `DisplayVersion` 均为 `1.0.1.0`，卸载后安装目录与两个 HKLM 键清空；终态四件与测试前逐位相同，无残留。**判定**：Phase A 已不再是「新机模拟」，本轮不得作为 `1.0.1.0` 的装卸验收结论。**裁定（2026-11-08，用户选方案一）**：不改任何仓库文件与断言，在管理员进程内依次做「提权自检 → 覆盖两件 DLL → 校验新 MD5 → 同进程调用 `e2e_test.ps1`」，复跑结果待回收。该次失败日志只留在 `%TEMP%`，因其为无效回归，不归档进 `05_验证\`。**2026-11-08 00:58 第二次复跑（方案一执行，有效验收）**：以提权封装在同一 High 完整性进程内完成「管理员自检 → OBS 进程自检 → 覆盖两件 DLL → 校验 MD5 → 同进程调用 `e2e_test.ps1`」，结果 **40 PASS / 0 FAIL**（Phase A 25/25、Phase B 15/15，`%TEMP%\obsbeauty_test\log.txt` 开头 00:58:46、结束行 00:58:55）。`safety` 备份的 filter 已为 `e34117…`、panel 已为 `ea79c0…`，证明**前置覆盖生效**；`A0` 两条删除断言由 FAIL 转 PASS，Phase A 恢复「新机模拟」语义。两次 `setup exit code: 0`、`DisplayVersion` = `1.0.1.0`，卸载后安装目录与两个 HKLM 键清空；终态四件与本次测试前逐位相同。**判定**：本轮可作为 `1.0.1.0` 的装卸验收结论；日志逐字归档到 `05_验证/e2e_install_20261108.md`。**边界**：本次只验证静默安装/卸载的文件与注册表逻辑，图形界面未逐页核对，卸载后未启动 OBS 验证插件加载出图。 |

---

*本文以 `06_安装包\build_setup.ps1`、`06_安装包\obs-beauty.nsi` 的当前内容为唯一真相源。
历史打包链路与踩坑记录（含 3.1.39 装/卸 40 项断言实测数据）见 `docs/archive/acceptance-installer-20261106.md`
及本机 `04_文档\C13_装机链路.md`（不入库）；当前版指南不重复保留历史验收数据。*
