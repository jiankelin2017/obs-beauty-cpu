# OBS美颜 CPU `1.0.3.0` · 全帧遍历融合改造的否定结果归档

> 本文件是 `05_验证/` 下的取证副本，**不是 Active 文档**，`docs/INDEX.md` 不登记它。
> 实验时间：2026-11-08 19:44–20:08。对象是离线测试 DLL `05_验证/beauty_core_test.dll`，
> 不涉及真机 OBS 录制，也不涉及装机 DLL。
> 实验结论为**否定结果**：改造在输出上逐字节等价，但在三档分辨率上都没有可测的耗时收益。
> 按用户 2026-11-08 20:06 选定的 A 方案，六个被改文件已按备份还原，改造代码不在当前工作区。
> 两个验证脚本与本文件保留；改造版源码和 DLL 只留在 `%TEMP%` 的实验快照，按 `.gitignore` 不入库。

| 字段 | 值 |
|---|---|
| 要回答的问题 | 把默认磨皮路径的两次相邻全帧遍历合成一次，能否降低引擎耗时 |
| 被测对象 | `beauty_core_test.dll`（离线台架，非 OBS 插件本体），源码为工作区 `1.0.3.0` 未提交状态 |
| 改造开关 | `BEAUTY_TONE_FUSION=0/1`，默认关，`=0` 路径逐字节不变 |
| 判定 | **不通过**。17 组 A/B 全部 `maxdiff=0 / ndiff=0`，但 3 轮基准差值落在噪声内且方向互相矛盾 |
| 处置 | 六个文件按备份还原并逐字节校验；未提交、未改 Active 文档、未动 OBS 配置 |
| 当前 HEAD | `b92d042`（本轮未产生新提交） |

## 1. 结论

这次改造把独立调用 `toneColor` 的整帧上色，搬进 `surface3RgbBand` 的合成循环里就地完成，机制上少了一次全帧读写。实现是对的：17 组逐字节对拍全部等价，自检标记也证明 `fusion=1` 确实走了合并路径。但性能目的没有达成，三档分辨率的三轮差值忽正忽负，中位数在 ±0.5 ms 以内，无法与测量噪声区分。按「无稳定收益即不合并」的判据，本轮改造不通过，代码已还原。

## 2. 目标为什么改过一次

最初提出的合并对象是 `blendWithMask` 与 `toneColor`，核实后发现该对象在现版本默认配置下不执行。

- 默认值为 `smoothModel = 1`（《beauty_core.cpp》l. 326）与 `s3Band = 1`（同文件 l. 389）。
- `process()` 经 l. 1789 → l. 1790 → l. 1859 命中 `surface3RgbBand`，并在 l. 1905 置 `didSurface3 = true`。
- l. 1940–1949 的分支是 `if (didSurface3) { /* 不能再走 blendWithMask */ } else if (haveMask) { blendWithMask(...) }`。

所以默认路径相邻的两趟全帧循环，实际是《beauty_smooth.cpp》l. 697–759 区段的 `surface3RgbBand` 合成段，以及随后《beauty_core.cpp》l. 1988 调用的 `toneColor`（实现在《beauty_freq.cpp》l. 614–709，默认整帧）。合并要跨 `beauty_smooth.cpp`、`beauty_freq.cpp` 与两个头文件，不是最初说的单文件最小增量。

另有一处口径冲突：《beauty_params.h》l. 96 的注释仍写 `s3Band` 默认关闭，与《beauty_core.cpp》l. 389 的实际初始化值相反，施工以源码为准。

## 3. 实现范围

| 文件 | 改动 |
|---|---|
| `beauty_freq.h` / `beauty_freq.cpp` | 把 LUT 构造抽为 `makeToneLut`，逐像素上色抽为 `tonePixel`；独立路径与合并路径共用同一公式 |
| `beauty_smooth.h` / `beauty_smooth.cpp` | 给 `surface3RgbBand` 增加默认 `nullptr` 的 `ToneLut*` 参数；合成段写完每像素后，指针非空时调用 `applyTone` |
| `beauty_core.cpp` | 提前计算色调参数，按 `BEAUTY_TONE_FUSION` 构造 LUT 并传入；融合命中时跳过外层 `toneColor`；命中处另加 `[WB_FUSION_ACTIVE]` 自检标记 |

构建两次均返回 `[core-test] BUILD OK`。Bash 调 `cmd.exe` 被工具安全策略拦下，改由 PowerShell 直接执行 `05_验证/build_core_test.bat` 成功。

## 4. 等价性：17 组全部逐字节相同

自写脚本 `05_验证/ab_tone_fusion.py` 用两个独立子进程分别注入 `BEAUTY_TONE_FUSION=0/1`，覆盖三档分辨率、单线程全帧与 ROI 自动线程、两组非零色调档位、`BEAUTY_TONE_GLOBAL=0` 回退、legacy 路径、色调全 0 早退，共 17 组。全部 `PASS maxdiff=0 ndiff=0`，脚本汇总行为 `[AB] 17 cases -> ALL PASS`。加入自检标记并重编译后复跑，结果不变。

抽样几组输出哈希（`sha256` 前 16 位）：

| 组名 | 哈希 |
|---|---|
| `640x394_full_1t_toneA` | `058cb3e4485449f7` |
| `720p_full_1t_toneB` | `8ab9e645cc012aaf` |
| `1080p_roi_auto_toneA` | `31339e033e72fece` |

同一组名在 `fusion=0` 与 `fusion=1` 下哈希相同，这是逐字节等价的直接证据。

## 5. 合并路径确实被执行

「输出等价」也可能来自开关根本没生效。为排除这个假象，`beauty_core.cpp` 在融合命中时向 stderr 打印 `[WB_FUSION_ACTIVE]`，`bench_tone_fusion.py` 汇总输出：

```
FUSION_MARKER  f0=False  f1=True  (f0 should be False, f1 should be True)
```

`f1=True` 证明 `fusion=1` 走到了合并分支，所以第 4 节的等价结论不是空跑。

## 6. 性能：无可测收益（否定判据）

`05_验证/bench_tone_fusion.py` 排除每 5 帧一次的检测帧，每轮每档取 48 个稳态样本，跑 3 轮取中位数。下表 `off_ms` / `on_ms` 为三轮中位数，`delta_by_round` 为每轮 `off − on`（正表示融合更快）。

| 分辨率 | off_ms | on_ms | 三轮 delta | delta 中位 | 样本数 |
|---|---|---|---|---|---|
| 640×394 | 4.04 | 3.99 | `+0.05 / +0.09 / +0.01` | `+0.05 ms (+1.3%)` | 48/轮 |
| 720p | 10.82 | 11.28 | `−0.49 / −0.46 / +0.58` | `−0.46 ms (−4.2%)` | 48/轮 |
| 1080p | 24.28 | 24.03 | `+0.96 / −0.94 / +0.45` | `+0.45 ms (+1.8%)` | 48/轮 |

三档方向不一致，1080p 单轮摆动接近 2 ms，远大于中位差。按「收益需在同一方向稳定复现」的判据，这一组数只能读作噪声，不能读作优化有效。

补充一个对照：设计文档口径的 `bench_core.py` 两组 `--cycles 5`，1080p 均摊为 17.86 ms 对 20.02 ms，看起来 fusion=1 更慢；但该脚本不设色调参数，`toneColor` 会早退、融合分支不会激活，所以这个差值只能说明单轮基准噪声大，不能用来评价融合。

## 7. 三道既有回归的适用性

本轮逐项核过仓库原有的三道回归，结论是它们都不能直接验收这次改造：

| 脚本 | 本轮结果 | 适用性判断 |
|---|---|---|
| `verify_roi.py` | 新 DLL 在 720p／1080p 的 ROI 项 FAILED（`maxdiff=3`）；用备份旧 DLL 重跑得到**完全相同**的失败位置与哈希 `c5ce090375032681` / `e3f1e7d608f2fe50`；`fusion=0` 与 `=1` 两组哈希一致 | 属仓库既有问题，与本轮改造无关；且它只验 ROI／多线程等价，不验融合前后等价 |
| `bench_core.py` | 跑通，两组数据见 §6 末段 | 不设色调参数，测不到融合 |
| `core_vs_sdk.py` | 跑通，曲线 `RMSE=14.85`、`11.7 ms` | 脚本头部自述 SDK 基准口径存疑，该 RMSE 不能当画质达标判据；且它同样不设色调 |

因此 §4 的 17 组对拍和 §6 的专用基准，是本轮实际承担验收的两个脚本。设计文档 §5 要求的 `BEAUTY_ASYNC_DETECT=0` 在相关运行中已显式设置。

## 8. 还原与证据留存

按用户选定的 A 方案，20:07 完成还原，六个文件逐个比对 `sha256` 与备份一致：

| 文件 | 还原后大小 | 还原后 sha256（前 16） | 与备份一致 |
|---|---|---|---|
| `beauty_core.cpp` | 215,250 B | `88596e1bd7cb1c02` | 是 |
| `beauty_smooth.cpp` | 69,553 B | `9e12c4e8570d29fa` | 是 |
| `beauty_smooth.h` | 23,096 B | `b9ec2c0bd2a3a8fb` | 是 |
| `beauty_freq.cpp` | 32,747 B | `0e7370da5438ebc8` | 是 |
| `beauty_freq.h` | 8,800 B | `8d414f7fe91998d8` | 是 |
| `beauty_core_test.dll` | 446,464 B | `336b75e923101b3b` | 是 |

还原后 `git diff --stat -- 01_源码/` 回到改造前的 6 files / 435 insertions / 19 deletions，检索 `BEAUTY_TONE_FUSION`、`makeToneLut`、`applyTone` 在 `01_源码/` 下已无命中。

留存位置：

- 改造前备份：`%TEMP%\wb_tone_fusion_20261108_194459\`（六个文件）。
- 改造版实验快照：`%TEMP%\wb_tone_fusion_patched_20261108_200755\`（五个改造后源码 + DLL，454,656 B，`ff1724a115596f60`）。快照只作复核用，不是仓库内容。
- 两个验证脚本：`05_验证/ab_tone_fusion.py`、`05_验证/bench_tone_fusion.py`，均保留为未跟踪文件。
- 对拍与基准产物：`05_验证/goldens/masks/_fusion/`，按 `.gitignore` 不入库。

**复现边界**：还原后的 `beauty_core_test.dll` 不含融合开关，两个脚本在此 DLL 上跑不出 §5 的 `f1=True`。若要复核本文件的数据，需要先把实验快照里的 DLL 临时放回 `05_验证/`（源码快照供对照），跑完再换回备份 DLL。本轮没有把改造补丁做成可打补丁的独立文件。

## 9. 复现命令

以下顺序对应本轮实际执行路径，供日后复核（命令均在仓库根目录或 `05_验证/` 下执行）：

```
:: 1) 构建（需 MSVC 14.51，脚本内含硬编码路径）
powershell -Command "& 'D:\插件\OBS美颜源码\05_验证\build_core_test.bat'"

:: 2) 逐字节 A/B（17 组）
cd /d D:\插件\OBS美颜源码\05_验证
python ab_tone_fusion.py

:: 3) 三轮稳健基准 + 开关自检
python bench_tone_fusion.py

:: 4) 三道既有回归（适用性见 §7）
set BEAUTY_ASYNC_DETECT=0
python verify_roi.py
python bench_core.py <tag> --cycles 5
python core_vs_sdk.py
```

## 10. 未验证项与边界

- 本轮全部数据是离线台架数据，没有真机 OBS 录制，也没有在 1080×1920 竖屏或 1920×1080 采集卡输入下测过融合收益。
- 本轮没有单独量过 `applyTone` 逐像素调用与范围检查的开销，因此「收益被这两项抵消」只是待检验假设，不是结论。
- `verify_roi.py` 既有 FAILED 的根因未查；其他 AI 是否仍在改这批源码，本轮不掌握。
- 本轮未提交、未改 Active 文档、未改 `docs/INDEX.md`、未动 OBS 场景与视频配置；工作区里其他 AI 的未提交改动保持原样。
