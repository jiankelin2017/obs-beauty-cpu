> **ARCHIVED · 已废弃，见 `docs/guides/guide-ui.md`**
> 归档日期：2026-11-06 · 状态：`Deprecated` · 适用代码版本：历史轴（第三方 SDK 对接时期，**非当前 CPU `1.0.0.0`**）
> 废弃原因：本文描述的是「方案 A：纯 HTML 面板 + obs-websocket + 自定义浏览器停靠窗口」，**该方案未采用**。2026-11-06 核查：文中引用的 `index.html`、`install_dock.py`、`install_dock.bat`、`serve_panel.py` 及外部绝对路径**全部不存在**，全库源码无 websocket 实现痕迹，按本文操作得不到正确结果，属无效/误导文档。
> 当前实现是 `obs-beauty-ui.dll`：Qt 顶层菜单 + 遍历滤镜 `obs_properties` 动态建控件，见 `docs/guides/guide-ui.md`。
> 本文为历史原件，正文未改写、未删减，**不得据此施工**。
> 维护人：待人工确认 · 最后核对：2026-11-06

---

# OBS 美颜面板（方案 A）

把自制美颜滤镜的操作入口提到 OBS 主窗口的**一级停靠面板**，与「场景 / 来源 / 混音器」并列。
面板是纯 HTML，通过 obs-websocket 直接读写现有滤镜参数——**滤镜 DLL 不用改一行**。

## 前置条件

1. OBS 里给摄像头源添加了 **OBS美颜** 滤镜（面板找不到源时会给提示）。
2. obs-websocket 已启用：OBS 菜单 **工具 → obs-websocket 设置 → 启用 WebSocket 服务器**，
   端口默认 **4455**。设了密码就记下来，面板里要填。

## 使用（三步）

1. **让面板出现在 OBS 里**（二选一）：

   **方式一 · 手动添加（最快，10 秒，OBS 开着也能做）**
   OBS 菜单 **停靠窗口(D) → 自定义浏览器停靠窗口...(C)**，填两项后点「应用」：
   - 标题：`美颜面板`
   - URL：`file:///<用户目录>/Documents/deepseek-harness/default-workspace/beauty-standalone/beauty_panel/index.html`

   OBS 退出时会自己把它写进配置，下次启动就自动带出来。

   **方式二 · 脚本写入（批量部署 / 换机器用）**
   先**完全退出 OBS**，再双击 `install_dock.bat`。脚本会写入
   `%APPDATA%\obs-studio\user.ini` 的 `[BasicWindow] ExtraBrowserDocks`
   （这就是 OBS 真正读取的位置），备份为 `user.ini.bak-beautydock`，写后自动校验。
   注意：**OBS 运行中执行会被脚本拒绝**，因为 OBS 退出时会用内存里的状态覆盖配置文件。

   > 只想看状态、不改文件：`python install_dock.py --check`

2. **点面板里的「连接」**。若 obs-websocket 设了密码，先在密码框填好再点连接。

3. **在源下拉里选摄像头**（显示为 `源名 → 滤镜名`）。面板会自动读出该滤镜的当前参数，
   之后拖动任何滑块都会即时下发。

## 面板功能

- **四个分组**：美颜（11 项 + 磨皮算法 + 精准美肤）、美型（脸型预设 + 20 项细调）、
  全局（原始方向 / 识别模式 / 人物个数 / 镜像 / 总开关）、滤镜（7 个滤镜 + 强度）。
- **双击滑块** = 该项恢复默认值；**全部恢复默认** = 整组回默认并下发。
- **自检** 按钮：校验内置 SHA-256 与认证串构造、参数表条数，结果打在日志区。
- 滑块改动会合并成一次请求（120ms 防抖），不会因为拖动而刷爆 websocket。

## 已知限制

- 面板只负责**下发参数**。多个滤镜实例共用 SDK 全局 item 的问题出在滤镜端，面板按
  `源名 + 滤镜名` 定位，不会互相串参数，但底层 SDK 状态仍是全局的。
- websocket 没开 / 密码错 / 端口被占时面板不可用，此时回退到滤镜属性页（方案 C 的入口）。
- 「美牙」「祛斑痘」「磨皮算法 2/3」在实测中是零像素变化，面板里已标注，滑块保留只为兼容预设。

## 文件清单

| 文件 | 作用 |
|---|---|
| `index.html` | 面板本体，单文件、无外部依赖、无 CDN |
| `install_dock.py` | 把面板注册进 `user.ini` 的 `[BasicWindow] ExtraBrowserDocks`（备份 + 校验 + 幂等 + 自动纠偏；`--check` 只看状态，`--remove` 移除） |
| `install_dock.bat` | 上面脚本的双击入口 |
| `serve_panel.py` / `serve_panel.bat` | 备用通道：本地 `http://127.0.0.1:8765/index.html`（仅当 Dock 不认 `file://` 时用） |
| `test_panel.js` | 自检脚本：语法检查 + SHA-256 与 Node 原生 crypto 交叉验证（`node test_panel.js`） |

## 故障排查

| 现象 | 处理 |
|---|---|
| 启动 OBS 后没看到面板 | 配置位置是 `user.ini` 的 `[BasicWindow] ExtraBrowserDocks`（不是 `global.ini`）。直接手动加一次最快：**停靠窗口 → 自定义浏览器停靠窗口** |
| Dock 区域空白 | 改用 HTTP 地址：双击 `serve_panel.bat`，Dock URL 改成 `http://127.0.0.1:8765/index.html` |
| 面板显示「连接出错」 | obs-websocket 没启用，或端口不是 4455 |
| 显示「需要密码」 | 在密码框填入 obs-websocket 的密码后重连 |
| 下拉里没有源 | 该源还没加「OBS美颜」滤镜，或滤镜被改名 |
| 改了参数画面没反应 | 确认源下拉选对了实例；「启用美颜」是否勾上；美型细调需要脸型预设 = 4 |
| 脚本报「检测到 OBS 正在运行」 | 完全退出 OBS 再执行，否则配置会被 OBS 覆盖 |
| Dock 又不见了 | OBS 重装或换配置后，关掉 OBS 跑一次 `install_dock.bat`，或在界面里重新添加 |
