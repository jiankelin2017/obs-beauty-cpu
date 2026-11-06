# guide · OBS 顶层菜单与参数面板（UI 插件）

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0.0` |
| 最后更新 | 2026-11-06 |
| 适用代码版本 | CPU 线 `1.0.0.0`（提交 `5323856`） |
| 维护人 | 待人工确认 |
| 状态 | `Active` |
| 替代文档 | 原 `04_文档/顶层菜单插件说明.md`（本文为其当前版）；`docs/archive/ui-html-websocket-proposal-20261106.md` 是**未采用的另一套方案**，不得混用 |

> 本文只描述 `obs-beauty-ui.dll` 的当前实现。凡标「历史轴实测」或「待人工确认」的数字/状态，
> 均不是 CPU `1.0.0.0` 的已验证结论，不得据此施工。

---

## 0. 一句话结论

**`obs-beauty-ui.dll` 是独立的 OBS 前端插件：拿主窗口指针 → `menuBar()->addMenu()` 加顶层菜单；面板不硬编码任何参数，遍历滤镜的 `obs_properties` 动态建控件。CPU 版显式标识由编译期宏 `BEAUTY_UI_CPU_EDITION=1` 打出，宏为 `0` 时菜单、标题、角标、关于、日志与历史行为零差异。**

---

## 1. 当前有效结论（可在 `01_源码/obs-beauty-ui.cpp` 逐字核对）

| 项 | CPU 版（宏 `=1`，当前构建） | 默认（宏 `=0`，共用源码路径） |
|---|---|---|
| 顶层菜单标题 | `美颜·CPU(&A)` | `美颜(&A)` |
| 窗口标题 | `OBS美颜 · CPU 版 v1.0.0.0` | `OBS美颜参数面板` |
| 顶栏徽章 | 蓝色 `CPU 版` QLabel（`objectName=beautyCpuTag`） | 无 |
| 版本角标 | `CPU v1.0.0.0` | `v1.0.0.0` |
| 「关于」说明 | 追加「纯 CPU 实现，不依赖 GPU / D3D」+「版本轴 `1.0.0.0` 与 GPU 版 `3.0.1` 独立、不可互比」 | 无该段 |
| 模块加载日志 | `[obs-beauty-ui][CPU] 模块已加载 v…` | `[obs-beauty-ui] 模块已加载 v…` |

- 宏**默认 `0`**（源码 `#ifndef BEAUTY_UI_CPU_EDITION / #define … 0`）。**唯一**打开它的位置是 `02_构建/build-ui_320.bat` 中 `cl` 命令的 `/DBEAUTY_UI_CPU_EDITION=1`。
  GPU 版依赖本仓库编出的独立 UI DLL，因此共用源码路径必须保持零 CPU 标识——这是硬约束，不是可选优化。
- `BEAUTY_UI_VERSION "1.0.0.0"` 与 `01_源码/beauty_params.h` 的 `BEAUTY_BUILD_STR` 同属 CPU 四段轴；
  `BEAUTY_FILTER_ID "obs_beauty_filter"` **永不随版本改动**（改了老场景里的滤镜会变成「缺失滤镜」）。
- 版本角标取的是**滤镜实机版本**：面板调 `beauty_version` proc 拿裸版本串（如 `1.0.0.0`），
  再按宏补前缀 `CPU v` / `v`。`BEAUTY_UI_VERSION` 只用于两处兜底：老滤镜没有该 proc 时的缺省值、
  以及滤镜号与面板号不一致时追加括注（这是「安装时漏换某一边」的现场证据）。比较一律用**不带前缀的裸号**。

---

## 2. 机制：为什么能加顶层菜单

下表为**历史轴本机实测证据**（对第三方「插件中心」的逆向），结论「拿主窗口指针 → `menuBar()->addMenu()`」至今仍是本插件的实现路径：

| 环节 | 证据 |
|---|---|
| 「插件中心」真身 | `%APPDATA%\obsplus\store\64bit\store_qt6.dll`（2.9 MB） |
| 依赖 | `Qt6Widgets.dll` / `Qt6Gui.dll` / `Qt6Core.dll` + `obs-frontend-api.dll`（`dumpbin /dependents`） |
| 调用的前端函数 | `obs_frontend_get_main_window`（`dumpbin /imports`） |
| 加菜单方式 | 文件内含 `?addMenu@QMenuBar@@…` 与 `?menuBar@QMainWindow@@…` 符号引用 |

即：**`obs_frontend_get_main_window()` → `QMainWindow::menuBar()->addMenu()`**。本插件走同一条路，只是把 `obsplus.dll`（纯后台服务、不含 Qt 代码）换成自己的实现。

菜单创建**不能**放在 `obs_module_load()` 里直接做——那时主窗口可能还没建好。源码用 `QTimer` 每 **250 ms** 轮询 `ensure_menu()`，直到 `menuBar()` 可用；累计 **240 次（60 s）** 仍未就绪就停止轮询并留一行 `LOG_WARNING`，不会无限唤醒。

---

## 3. 安装（路径规则有效；当前装机状态待人工确认）

> ⚠️ **目录名必须与 DLL 文件名完全一致。** OBS 扫描 ProgramData 插件时按
> `<插件目录名>/bin/64bit/<插件目录名>.dll` 找文件（见 `obs-module.c` 的 `parse_binary_from_directory()`）。
> 名字对不上会**静默跳过、一行日志都不写**，现象和「插件压根没装」完全相同。
> 历史上装在 `nama-beauty-ui\` 目录下、DLL 却叫 `obs-beauty-ui.dll`，就是这个原因导致重启后菜单不出现。

历史轴实测的安装路径（重新覆盖 DLL 后需**重启 OBS**）：

```
C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\obs-beauty-ui.dll
C:\ProgramData\obs-studio\plugins\obs-beauty-ui\data\locale\en-US.ini
```

> ⚠️ **待人工确认**：CPU `1.0.0.0` 目前**没有对应的装机脚本**（`03_装机\` 下只有历史轴版本），
> 真机装/卸与 `06_安装包\e2e_test.ps1` 回归也尚未在 CPU `1.0.0.0` 上复跑，见 `README.md` §2.3、§8。
> 上述路径只证明「历史轴这样装成功过」，**不代表当前已安装或已验证**。

---

## 4. 使用

1. 重启 OBS。
2. 菜单栏最右侧出现「**美颜·CPU(&A)**」（CPU 版；默认构建为「**美颜(&A)**」）→ 点「**参数面板...**」。
3. 面板顶部下拉框选作用对象（显示为 `源名 → 滤镜名`），下方滑块 / 下拉 / 勾选框即该滤镜的全部参数。
4. 改动**即时生效**；「恢复默认」走 `obs_get_source_defaults()`；「刷新」重新扫描滤镜实例。
5. CPU 版「关于」会明确写出纯 CPU 与版本轴差异；菜单里另有「关于」项。

面板不硬编码任何参数，而是遍历滤镜的 `obs_properties` 动态建控件 —— 滤镜侧增删参数、改标签、改范围，面板自动跟随，不需要维护两份表。

---

## 5. 构建（可执行）

```bat
:: CPU 1.0.0.0：先设独立产物目录，避免覆盖 build_output\ 里的 3.1.40 定稿 DLL
set BEAUTY_OUTDIR=D:\插件\OBS美颜源码\02_构建\build_1.0.0.0
02_构建\build-ui_320.bat
```

```powershell
# 构建后自检：导入符号 ABI 校验
python 02_构建\verify-ui-imports.py 02_构建\build_1.0.0.0\obs-beauty-ui.dll
```

| 要点 | 说明 |
|---|---|
| CPU 宏 | `build-ui_320.bat` 的 `cl` 命令已含 `/DBEAUTY_UI_CPU_EDITION=1`；**不带宏的编译须去掉该项**（GPU 共用源码路径） |
| 版本号 | **不在脚本里**，唯一出处是 `01_源码/obs-beauty-ui.cpp` 的 `BEAUTY_UI_VERSION`；脚本版本无关 |
| 输出 | `%BEAUTY_OUTDIR%\obs-beauty-ui.dll`；未设 `BEAUTY_OUTDIR` 时默认 `02_构建\build_output\`，**不要用于 CPU `1.0.0.0`** |
| 目录探测 | 按**内容**定位目录（源码看 `obs-beauty-ui.cpp`、SDK 看 `obs-studio-32.1.1\libobs`），目录改编号不会失效 |
| 脚本编码 | 纯 ASCII —— 源码树在中文路径下，UTF-8 的 `.bat` 被 `cmd.exe` 按 GBK 读会路径乱码（`C1083`） |

依赖：**Qt 6.8.3 msvc2022_64**（`C:\Qt`，与 OBS 32.1.1 内置 Qt 一致）、`obs.lib` / `obs-frontend-api.lib`、MSVC 14.51（本机 VS 18）。

### 5.1 三个必须知道的坑

1. **必须加 `/permissive-`**。MSVC 14.51（VS 18）默认不是一致性模式，Qt 6.8.3 头文件会直接
   `static_assert` 失败（`error C2338: On MSVC you must pass the /permissive- option`），
   紧接着报一堆 `C2666` 重载歧义与 `C2139` 不完整类型的**连带错误**。这些连带错误看着像 Qt 与编译器不兼容，
   加 `/permissive-` 后全部消失。
2. **`QAction` 在 Qt6 属于 `QtGui`**，不是 `QtWidgets`。写 `#include <QtWidgets/QAction>` 会报找不到头文件。
3. **`obs-frontend-api.h` 安装包不提供**。本插件只用到 `obs_frontend_get_main_window()` 一个函数，
   直接在源码里按 ABI 声明即可；导入库可用 `lib.exe /def` 从 `obs-frontend-api.dll` 导出表生成
   （历史轴实测 96 个导出）。当前现成的 `.def` / `.lib` 位于 `参考文件\03_依赖与SDK_OBS\obs-sdk\` ——
   **该目录是法务红线、仅本机保留，不入库**。

---

## 6. 文件清单（当前路径）

| 文件 | 作用 |
|---|---|
| `01_源码/obs-beauty-ui.cpp` | 插件源码：菜单 + 通用属性面板 + CPU 版标识 |
| `02_构建/build-ui_320.bat` | CPU 版编译脚本（含 `/DBEAUTY_UI_CPU_EDITION=1`） |
| `02_构建/verify-ui-imports.py` | 导入符号 ABI 校验 |
| `参考文件/03_依赖与SDK_OBS/obs-sdk/obs.lib`、`obs-frontend-api.lib`、`obs-frontend-api.def` | 导入库与导出定义（**仅本机，不入库**） |

---

## 7. 已知限制

- 面板对少数控件类型（颜色、路径、字体、可编辑列表、按钮）显示为占位文字。
- `OBS_PROPERTY_BUTTON` 在 libobs 没有外部触发接口 → 面板用「恢复默认」按钮替代（走 `obs_get_source_defaults`）；
  「保存参数到 preset.json / 从 preset.json 读取」仍在滤镜属性页里操作。
- 面板按 `源名 + 滤镜名` 定位实例，多摄像头互不干扰。

---

## 附录 A · 历史轴验证数据（`3.1.x` 实测，CPU `1.0.0.0` 未复核）

| 检查 | 当时结果 |
|---|---|
| 导入符号完整性 | `verify-ui-imports.py`：`qt6widgets` 402 + `obs.dll` 41 + `qt6core` 37 + `qt6gui` 4 + `obs-frontend-api` 1 = **485 个符号全部在 OBS 自带 DLL 中可解析** |
| 真实加载 | 独立进程 `LoadLibrary` 冒烟测试通过（基址 `0x7ff9759d0000`） |
| 编译 | `build-ui.bat` 通过，产物 `build\obs-beauty-ui.dll`（191,488 字节） |

> 产物路径与体积属旧目录结构；当前产物为 `02_构建\build_1.0.0.0\obs-beauty-ui.dll`。
> 2026-11-06 的 CPU `1.0.0.0` 编译验证见 `README.md` §2.2（两种宏配置均通过、宏相关字符串只出现在 `=1` 版）。

---

## 附录 B · 失效内容说明与合并记录（2026-11-06）

- 来源：`04_文档/顶层菜单插件说明.md`，`git mv` 为本文后按模板改写（机制 / 三个坑 / 目录名坑保留）。
- **菜单名**：原文单写「美颜(&A)」→ 按 `BEAUTY_UI_CPU_EDITION` 分列 CPU 版与默认版两种口径。
- **构建脚本**：`build-ui.bat` → `02_构建/build-ui_320.bat`；源码路径 `src/` → `01_源码/`；
  校验脚本 → `02_构建/verify-ui-imports.py`；产物路径 `build\` → `02_构建\build_1.0.0.0\`。
- **删除**「底层 SDK 的全局状态问题仍属滤镜端」：当前是纯 CPU 自研 CoreEngine，运行时不加载第三方美颜 SDK，
  该限制的前提已不成立。
- **未采用的另一套方案**：`docs/archive/ui-html-websocket-proposal-20261106.md`（纯 HTML 面板 + obs-websocket +
  自定义浏览器停靠窗口）与本文不是同一实现，其引用的脚本与路径全部不存在，不得混用。
- 历史实测数据统一移入附录 A；装机状态、维护人、验证数字均标「待人工确认」。

---

*本文的「当前有效结论」均可在 `01_源码/obs-beauty-ui.cpp` 与 `02_构建/build-ui_320.bat` 逐字核对；
凡标注「待人工确认」的项不得当作已确认结论使用。*
