# OBS美颜 安装包 —— 打包与卸载说明（v3.1.39）

> 2026-10-31 · 滤镜 3.1.39 / 面板 3.1.39 / 引擎 core 1.4.0
> 本目录取代旧的 `obs-beauty.nsi`（3.1.2 版、带参考实现、四段式组件页）。
> 旧包的构建链路与踩坑记录仍在 `04_文档\C13_装机链路.md`，那份是历史。

## 1. 产物

| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `OBS美颜_Setup_v3.1.39.exe` | 3,634,543 B（3.47 MB） | `9ec10d74cc432ba13c318c2a27dce59c` | 双击安装；装完自带卸载器 |

- 产物版本资源：`3.1.39.0`（`VIProductVersion`）。
- **md5 不可复现**：NSIS 每次编译的时间戳/压缩顺序都不同，同一份源码连编两次 md5 也不同。
  这个值只用于「这一次打出来的包」核对，别拿它当源码一致性证据。

## 2. 包里是什么

一个界面（欢迎 → 进度 → 完成），三个 Section，装 4 个文件：

| 文件 | 装到 | 大小 | md5 |
|---|---|---|---|
| `obs-beauty.dll` | `C:\Program Files\obs-studio\obs-plugins\64bit\` | 440,320 | `d9984544ae8ea0dbdf08b2594a13ebcb` |
| `onnxruntime.dll` | 同上 | 11,569,696 | `cd5e3b3eedbe6774b28d8fff9d0a3243` |
| `models\yunet.onnx` | `…\obs-plugins\64bit\models\` | 232,589 | `4ae92eeb150c82ce15ac80738b3b8167` |
| `obs-beauty-ui.dll` | `C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\` | 215,040 | `b59a063fa6c26d55f55e62d630395233` |

外加 `C:\Program Files\obs-beauty\` 下的 `README.txt`、`md5.txt`、`Uninstall_OBS美颜.exe`。

**后两个位置不能改**（`04_文档\C13_装机链路.md` §2）：
`beauty_core.cpp` 的 `ensureReady()` 用 `selfDir()`（= 滤镜 DLL 所在目录）解析
`onnxruntime.dll` 与 `models\yunet.onnx`。放进 `obs-beauty\`（那是参考实现的资源根）
滤镜照样能加载，但人脸检测静默失效 → 磨皮退化成全帧。**不报错，只对拍能看出。**

**不含参考实现**（约 97 MB 闭源件）。3.1.7 起默认引擎已是自研 CoreEngine，
本机实测无 SDK 目录也能 `init OK (engine=core/1.4.0, region=on)`。
机器上本来就有 `obs-beauty\` SDK 目录的，装和卸都不动它。

## 3. 怎么重新打包

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\插件\OBS美颜源码\09_安装包\build_setup.ps1"
```

脚本按顺序做 7 件事：

1. 取源：`02_构建\build_output\{obs-beauty.dll, obs-beauty-ui.dll}`、
   `05_验证\deps\runtime\onnxruntime.dll`、`05_验证\models\yunet.onnx`
   （后两个缺失时回退到 `参考文件\03_依赖与SDK_OBS\installer-stage\`）
2. **版本串自检**：两个 DLL 里必须能搜到 `3.1.39` 和 `obs_beauty_filter`，
   否则直接报错 —— 防「把上一版构建打进包，界面上看不出来」（C13 坑 #1）
3. 与已装机文件对照 md5，不一致只提示不阻断
4. 暂存到 `%TEMP%\obsbeauty_pkg`（**纯 ASCII**：NSIS 处理中文源路径会报 `no files found`）
5. 生成 `docs\README.txt`（用户说明书）和 `docs\md5.txt`（清单）
6. 确保 `obs-beauty.nsi` 是 **UTF-8 with BOM**（否则中文界面乱码），再调 `makensis`
7. 产物落到本目录，打印大小/md5/四个文件的指纹，最后清掉暂存目录

### 版本号只在一处改

改 `build_setup.ps1` 顶部这四行就够了，它们用 `/D` 传给 nsi：

```powershell
$Ver       = '3.1.39'   # 包版本（产物文件名、控制面板显示）
$FilterVer = '3.1.39'   # 滤镜版本
$PanelVer  = '3.1.39'   # 面板版本
$CoreVer   = '1.4.0'    # 引擎版本
```

`obs-beauty.nsi` 里同名 define 用 `!ifndef` 兜底，只有手工跑 `makensis` 时才生效。

### 两个必须记住的编译期硬约束

- **源路径必须纯 ASCII**：中文路径会让 NSIS 报 `no files found`（这是 C13 的坑）。
  脚本因此先复制到 `%TEMP%`，`File` 只认暂存目录。
- **`/DOUTFILE` 里不能有中文**：makensis 按控制台代码页解析命令行，中文名会变成乱码文件名。
  脚本先用 `OBSBeauty_Setup_v3.1.39.exe` 编译，再用 PowerShell 改名。
- 源文件自检写在**编译期**（`!if ! /FileExists … !error`）。写成运行时会出事：
  `File` 是编译期把内容写进 exe 的，安装时根本不需要暂存目录，而脚本编完就清掉它了 ——
  真这么写过一版，四个文件全在包里、安装却直接 Abort（退出码 2）。

## 4. 卸载做了什么

卸载器由安装器在装机时写出（`C:\Program Files\obs-beauty\Uninstall_OBS美颜.exe`），
同时注册进「程序和功能」（`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\OBSBeauty.NamaBeauty`）。
开始菜单也有入口。支持 `/S` 静默卸载。

规则是「**装之前什么样，卸完还是什么样**」：

| 情况 | 卸载动作 |
|---|---|
| 装之前有同名文件 | 先备份到 `C:\Program Files\obs-beauty\backup\`，卸载时**还原** |
| 装之前没有 | 删除 |
| `models` 目录是本包建的 | 删（`RMDir` 不带 `/r`，里面有别的模型就删不掉、自动保留） |
| `models` 目录装前就有 | 只删 `yunet.onnx`，目录保留 |
| 旧包（3.1.2）装过 SDK（`SdkCreated=1`） | 连同 `obs-beauty\` 整个删掉 |
| 别的途径装的 `obs-beauty\` SDK | **不动**（只打一行日志） |
| 面板窗口设置 `ui.ini` | 卸载时问一句，默认保留；静默卸载=保留 |

「是不是旧包装的」靠注册表状态键判断，状态键同时记下 `ObsDir` / `UIDir` / `PDir`，
所以就算 ProgramData 盘符或 OBS 安装路径变了，卸载仍能找回真实位置。

**一个要留意的语义**：备份还原的是「装这个包之前的状态」。
如果你装完之后又用 `02_装机\install_*.bat` 手动换成了更新的 DLL，
再卸载会把备份里的旧版本放回去。想彻底清干净就卸完再删文件。

## 5. 实测（不是「应该能行」）

`e2e_test.ps1`（本目录，需管理员）跑了两轮真实装/卸，40 项断言全过：

- **Phase A 全新机**：先删掉 4 个已装文件模拟干净机器 → `setup /S` → 4 个文件 md5 与包内逐位相同、
  卸载器/README/清单就位、两处注册表就位、开始菜单就位 → `Uninstall /S` →
  文件全删、`models` 空目录删掉、ProgramData 目录链删掉、安装目录删掉、注册表与开始菜单删干净
- **Phase B 覆盖装**：把原文件放回 → `setup /S`（触发备份）→ `Uninstall /S` →
  4 个文件**逐位还原**，`ModelsCreated=0`（目录装前就有，故保留）
- 两轮跑完机器状态与测试前完全一致（四个 md5 逐位相同）

明细与日志见 `04_文档\验收报告_安装包v3.1.39.md`。

## 6. 已知边界

1. **图形界面没有逐页截图核对**。静默安装验证了全部落地行为；界面文字按
   「UTF-8 BOM + `Unicode true`」的既有写法（与 3.1.2 那版一致），
   并在 exe 里按 UTF-16LE 抽查到了 `OBS美颜` / `安装程序` / `参数面板` / `滤镜` 等串。
2. **只支持 64 位 OBS**，且只认注册表 `HKLM\SOFTWARE\OBS Studio` 的(默认)值
   （缺失时退回 `%ProgramFiles%\obs-studio`）。绿色版 OBS 装不上。
3. **不做 OBS 版本兼容性判断**。滤镜用 OBS 32.1.1 的头文件构建，装到别的 32.x 上按理可用，
   但没有验证矩阵。
4. **不含 SDK 回退路径**。若某天要把 `LEGACY_ENGINE_IMPL` 切回 `nama`，需要另外补 SDK 文件。
5. 老的 `obs-beauty.nsi`（3.1.2）已被本文件同目录的新版覆盖，历史内容见 `04_文档\C13_装机链路.md`。

## 7. 本目录文件

| 文件 | 作用 |
|---|---|
| `OBS美颜_Setup_v3.1.39.exe` | **产物**，双击即装 |
| `obs-beauty.nsi` | 安装/卸载脚本（UTF-8 BOM，Unicode） |
| `build_setup.ps1` | 打包脚本：取源 → 校验 → 暂存 → 编译 → 改名 |
| `e2e_test.ps1` | 装/卸回归测试（管理员运行，会临时删再恢复 4 个文件） |
