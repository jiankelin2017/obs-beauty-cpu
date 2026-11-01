# 第三方组件与来源说明

本项目为 OBS Studio 插件，动态链接 libobs。本文件列明随源码分发或被参考的第三方组件及其许可，
以便使用者判断再分发的合法性。

---

## 1. 本项目自身的许可

**GPL-2.0**（完整文本见仓库根目录 `LICENSE`）。

理由：本插件动态链接 OBS Studio 的 libobs，libobs 属 GPLv2；按 GPL 传染性条款，本插件源码
须以 GPLv2 提供。源码全量位于 `01_源码/`，构建脚本位于 `02_构建/`、`09_安装包/`。

## 2. 被引用但未随包分发的组件（仅本地研究/对照用）

| 组件 | 版本 | 许可 | 位置 | 说明 |
|---|---|---|---|---|
| **FaceUnity NamaSDK**（`CNamaSDK.dll` / `fuai.dll`） | 8.10.0_r（产品侧 2.4.2） | **闭源商业授权** | `07_依赖与SDK/installer-stage/` | FaceUnity（相芯科技）商业资产。**无再分发权，不随本仓库分发**，仅本机作画质对照真值与逆向研究。商用或公开发布请自行申请正版授权：https://www.faceunity.com/ |
| **NamaSDK 道具 bundle**（`face_beautification.bundle` / `ai_face_processor_pc.bundle`） | — | **闭源商业授权** | 同上 | 同上 |
| **授权包**（`auth_package.bin`） | — | **闭源商业授权** | 同上 | 同上 |

> 以上三个组件被 `.gitignore` 显式排除在版本库之外。仓库内的 `06_逆向资料/`（逆向着色器、
> 解密脚本、内存 dump）同样因法务风险被排除。

## 3. 随源码分发或需另行分发的可商用组件

| 组件 | 版本 | 许可 | 来源 | 分发方式 |
|---|---|---|---|---|
| **ONNX Runtime**（`onnxruntime.dll`） | — | **MIT** | https://github.com/microsoft/onnxruntime | 运行时，随安装包分发（GitHub Release 附件，不入 git） |
| **YuNet**（`yunet.onnx`） | 2023mar | **MIT** | https://github.com/opencv/opencv_zoo | 人脸检测模型，随安装包分发 |
| **PP-HumanSeg**（`pphumanseg_2023mar.onnx`） | 2023mar | **Apache-2.0** | https://github.com/PaddlePaddle/PaddleSeg | 人像分割模型，**当前生产路径未使用**，仅作离线对照 |
| **OBS Studio**（`libobs`） | 32.1.1 | **GPL-2.0** | https://github.com/obsproject/obs-studio | 宿主程序，插件动态链接，不随本仓库分发 |
| **wuxiwuhen/obs-beauty-filter**（effect 源码） | — | **MIT** | https://github.com/wuxiwuhen/obs-beauty-filter | **MIT 许可全文保留**于 `10_开源参考/MIT_LICENSE_wuxiwuhen.txt`；effect 源文件头部已附版权声明 |

### 关于 MIT 组件的处理

MIT 许可要求「在所有副本或实质性部分中保留版权声明与许可声明」。本项目的处理：

- `10_开源参考/MIT_LICENSE_wuxiwuhen.txt` — MIT 许可全文（含 `Copyright (c) 2026 wuxiwuhen`）
- `10_开源参考/MIT_wuxiwuhen_beauty_filter.effect.txt` — 源文件头部已加注版权声明与许可全文摘要

## 4. 只读参考、未抄用代码的仓库

以下仓库为 GPL-2.0，**仅阅读架构思路与参数取值，未复制任何一行代码**（抄用会导致整个插件被迫 GPL 化）：

| 仓库 | 许可 | 参考内容 |
|---|---|---|
| https://github.com/wtnl-zhi/obs-beauty-filter | GPL-2.0 | 异步检测架构、掩码羽化参数 |
| https://github.com/iesv/OBS-Beauty | GPL-2.0 | 功能清单 |
| https://github.com/vanawaker/BetterFaceOBS | GPL-2.0 + Apple Vision | 仅 Apple 平台，本项目未采用 |

`dinjufen/lumina-beauty` 核心 SDK 为 MIT（可商用），OBS 插件层为 GPL-2.0（仅读思路）。
详见 `04_文档/开源参考仓库_对照与可复用清单.md`。

---

*本文档随源码同步维护。新增第三方依赖时必须同步更新本文件。*
