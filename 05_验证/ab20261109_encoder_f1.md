# 编码过载提示的归因（2026-11-09，F1）

| 字段 | 值 |
|---|---|
| 版本 | 验证记录 `0.1.0`（非 Active 设计文档，不登记 `docs/INDEX.md`） |
| 最后更新 | 2026-11-09 |
| 适用代码版本 | CPU 线 `1.0.3.0`（装机 DLL sha256 前 32 位 `1d0b52f24fa8cd95c3a7e062c8fa2907`） |
| 维护人 | 待人工确认 |
| 状态 | `Active`（仅作本轮实测记录） |
| 替代文档 | 无（前序：`05_验证/ab20261109_zero_knob.md`） |

> 口径提醒：本文件是**验证记录**，数字只描述 2026-11-09 00:31–00:42 的这台机器、这块采集卡、
> 当时的画面内容。设计文档不引用这里的毫秒数。

## 1. 要回答的问题

录制时 OBS 状态栏出现「编码过载」提示。日志给出两行原始计数：

```
Number of lagged frames due to rendering lag/stalls: 989 (13.8%)
number of skipped frames due to encoding lag: 4267/7189 (59.4%)
```

渲染滞后 13.8%，编码滞后跳过 59.4% —— 只按渲染瓶颈推算（合计 40–46 ms/帧 → 21–24 fps），
30 fps 目标下应丢 20–28%。**多出的一倍需要解释**。本轮要回答：这多出来的部分是不是
NVENC 参数太重造成的独立瓶颈。

## 2. 方法

| 项 | 做法 | 为什么 |
|---|---|---|
| 参数载体 | 改 `%APPDATA%/obs-studio/basic/profiles/未命名/recordEncoder.json` | `basic.ini` 的 `[AdvOut]` 段里 `RecBitrate=100000` / `RecQuality=Lossless` **不生效**；实际生效的是 `recordEncoder.json`（见第 5 节） |
| 降载内容 | `preset` p5→p2、`multipass` qres→disabled、`b-frames` 2→0、`lookahead` true(8)→false，码率维持 CBR 8000 | 只动编码，不动美颜面板，保证与 00:20 那轮可比 |
| 生效校验 | 每次录制后读日志 `[obs-nvenc] settings` 块 | 配置写完不等于生效，必须看 OBS 自己打印的最终值 |
| 归一化 | 用 **skipped / lagged 比值**，而非绝对跳过率 | 绝对率随渲染滞后与画面内容漂移；比值反映「每发生 1 帧渲染滞后会连带丢多少编码帧」，不受内容差异影响 |
| 固定项 | `BEAUTY_MASK_EVERY=2`、面板 磨皮 100 / 美白 45 / 下巴 7 / 全局锐化 0、30 fps、1080×1920 | 与前序文档同口径 |

## 3. 结果

### 3.1 参数确实生效

| 键 | 目标值 | 日志实际打印 | 判定 |
|---|---|---|---|
| preset | p2 | `p2` | 生效 |
| multipass | disabled | `disabled` | 生效 |
| b-frames | 0 | `0` | 生效 |
| lookahead | false | `false (0 frames)` | 生效 |
| tuning | ll | **`hq`** | **未生效**，写入 `"ll"` 被拒，回落到默认 hq |
| bitrate | 8000 | `8000` | 未改动 |

### 3.2 降载后没有改善

| 项 | p5 基线 | p2 降载 | 差 |
|---|---|---|---|
| 录制时长 | 240 s | 120 s | — |
| 无脸帧 | 540（3 个窗口） | 0 | 不可直接比 |
| 渲染滞后 lagged | 989 (13.8%) | 674 (16.4%) | — |
| 编码跳过 skipped | 4267/7189 (59.4%) | 3044/3879 (78.5%) | — |
| **skipped / lagged** | **4.32** | **4.52** | **+4.6%** |
| 仅算人脸帧的 lagged 率 | 14.9% | 16.4% | +1.5 pt |
| 仅算人脸帧的 skipped 率 | 64.2% | 78.5% | +14.3 pt |
| 按 lagged 归一的 skipped 率 | 64.2% | 71.3% | +7.1 pt |

p2 的绝对跳过率更高，其中一部分由这一段本身渲染更慢解释（lagged 16.4% > 14.9%）。
把 lagged 拉平后仍有 7 个百分点的差距，方向是**更差**，不是更好。

补充：18 s 短测（p2）为 lagged 22.1% / skipped 77.8%，比值 3.52。三组比值落在 3.5–4.5 区间内，
**没有随编码参数变化出现系统性下降**。

### 3.3 判读

如果 NVENC 是独立瓶颈，把 lookahead、multipass、b-frames 全关、preset 降三档，
`skipped / lagged` 比值应当明显下降。实测没降（4.32 → 4.52）。

因此本轮**不支持**「编码器参数重是编码滞后的主因」这个假设。编码跳过更像是渲染滞后的
**连带计数**：每出现 1 帧渲染滞后，后续约 4 帧被一并判为编码跳过。这个 4 倍关系的机制
本轮没有查证到源码级证据，只作为观察记录，不作结论。

## 4. 副作用与异常（重要）

### 4.1 p5 参数下两次停止录制未正常收尾

| 日志 | 录制开始 | `Recording Stop` | 录像文件 | 下次启动提示 |
|---|---|---|---|---|
| `2026-11-09 00-35-46.txt` | 00:36:11 | **无** | `00-36-10.mp4` 停在 66.7 MB | — |
| `2026-11-09 00-40-07.txt` | 00:40:32 | **无** | `00-40-31.mp4` 停在 75.1 MB | `Crash or unclean shutdown detected` |

同一脚本在 p2 参数下（`00-32-39.txt`）能正常写出统计行。两次 p5 失败都发生在
`StopRecord` 之后、OBS 主线程未再输出任何日志即退出。**原因未查明**，不排除与渲染/编码
负载高时主线程阻塞有关，本轮没有做定位。这一点对实际使用的影响是：录制结束可能拿不到
完整文件。已确认 `hybrid_mp4` 有恢复机制，但未对本轮两个文件做可播性验证。

**G1 复核（`00-46-20.txt`，60 s，p5 参数）**：停录路径本身正常——

```
00:47:38.408  Waiting for file writer to finish...
00:47:38.409  ==== Recording Stop ====
00:47:38.409  File output complete. Finalization took 2 ms.
```

文件 57.4 MB / 60 s = 7.65 Mbps，与 CBR 8000 吻合；日志**没有** lagged / skipped 行，
即这一段零丢帧。对照三段文件的体积与码率：

| 录像 | 时长 | 体积 | 折算码率 | 判定 |
|---|---|---|---|---|
| `00-33-03.mp4`（p2） | 120 s | 114.3 MB | 7.62 Mbps | 完整 |
| `00-36-10.mp4`（p5） | 120 s | 63.6 MB | 4.24 Mbps | **只有 53%，截断** |
| `00-40-31.mp4`（p5） | 90 s | 71.6 MB | 6.67 Mbps | **约 86%，截断** |
| `00-46-37.mp4`（p5） | 60 s | 57.4 MB | 7.65 Mbps | 完整 |

所以不是「p5 必然停不住」，而是**渲染负载高的那几轮收不了尾**。G1 这次引擎只
23.5 ms/帧，主线程有余量，2 ms 就完成 finalize。日常使用中人脸较大、引擎 40 ms 时，
正落在会截断的那一侧，这条风险仍然成立。

**顺带修正一个判据错误**：无丢帧时 OBS **不打印** `Video stopped, number of skipped frames...`。
脚本原先以此为收尾判据，会把正常收尾误判成卡住，已改为等 `Recording Stop`。

### 4.2 崩溃标记残留已清理

`%APPDATA%/obs-studio/.sentinel/` 下残留 14 个 `run_<uuid>` 空文件（含 11-08 与 11-09 历次会话），
每次都会让下次启动弹出「非正常退出」对话框。本轮已全部删除，当前该目录为空。

### 4.3 脚本改动

`ab_run.py` 启动命令加 `--disable-shutdown-check`，避免崩溃标记导致 OBS 卡在安全模式对话框。
这是唯一一处代码改动，不影响测量逻辑。

## 5. 工程发现：编码参数不在 basic.ini 里

| 位置 | 键 | 是否生效 |
|---|---|---|
| `basic.ini` `[AdvOut]` | `RecBitrate=100000`、`RecQuality=Lossless` | **不生效** |
| `basic.ini` `[SimpleOutput]` | `Preset=veryfast`、`NVENCPreset2=p5`、`RecQuality=Stream` | 仅 Simple 模式生效，本机是 Advanced 模式 |
| `recordEncoder.json` | `rate_control`、`bitrate` | **生效** |
| 无显式配置 | preset / multipass / b-frames / lookahead | 取 OBS 内置默认（p5 / qres / 2 / 8） |

要改编码质量必须写 `recordEncoder.json`，且键名与取值受限：`tuning` 的 `"ll"` 被拒，
`"hq"` 可用；`preset` 用 `"p1"`–`"p7"`；`multipass` 用 `"disabled"` / `"qres"` / `"fullres"`。

## 6. 结论

1. **降编码参数无效**。p5 → p2 并把 lookahead / multipass / b-frames 全关，编码跳过率没有改善，
   按 lagged 归一后反而高 7 个百分点。
2. **「编码过载」提示的根因仍在渲染**：每帧 40–46 ms 超出 33.3 ms 预算，渲染只出 21–24 fps，
   编码端随之被判过载。这与前序文档「零改动旋钮已用尽」的结论一致，且补上了编码器这一项。
3. **所以 F2（输出 30→24）与 F3（关 HAGS）都不必再测**：前者只是让目标对齐现实，后者针对的
   是一个已被本轮否定的假设方向。
4. 真正能动的仍是渲染端：`blendWithMask` 全帧遍历、渲染线程每次提交的 8 MB 拷贝、
   surface3 的分辨率/ROI。
5. **新增一条产品级风险**：高负载轮次停止录制未收尾（第 4.1 节），需要单独定位。
6. **意外观察（成因未验证）**：G1 那次 60 s 录制里引擎稳定在 **23.5 ms**、合计 **26.5 ms**，
   与前几轮的 35–40 ms 相差约 40%——同配置、同 `every=2`、同分辨率、对齐率同为 33%。
   磨皮 ROI 取的就是人脸包围盒（`beauty_core.cpp` l.1853–1856，`s3roi = bounds_`），
   脸在画面里占比越大，ROI 越大，计算量随之线性增长。
   **若该假设成立，「回不到 30 fps」就只在人脸占画面较大时成立**，人脸较小时本来就能
   满 30 fps、也不会出现编码过载提示。**已用「改输入像素数」的办法验证，不用人走动**：
   见 `05_验证/ab20261109_roi_scale.md`——引擎耗时约 10–15 ms/百万像素，16 倍像素对应
   11.5 倍耗时，且 1920×1080 下 24.3 ms 的量级相当于整帧处理。

## 7. 局限与未验证

- p5 的 120 s / 90 s 两次同长度对照**都没拿到统计行**（第 4.1 节），所以 p5 一侧只能引用
  00:20 那轮 240 s 数据。两轮时长不同、无脸帧数不同，第 3.2 节的归一化是近似换算，不是严格对照。
- 「540 帧无脸」按 3 个整窗口 × 180 帧推算，窗口边界与无脸起止可能略有错位。
- `skipped / lagged` 约 4 倍的机制未查证。
- 只测了 H.264 CBR 8000。HEVC / AV1、CQP 模式、以及 8 Mbps 之外的码率都没测。
- 未做画质评估：p2 与 p5 在同一码率下的主观差异没有比对。
- **人脸尺寸这一变量没有被测量**：性能埋点只打印下载/引擎/上传与对齐率，不打印 ROI
  尺寸或人脸面积。第 6 节第 6 条的假设目前只有「引擎耗时差 40%」这个间接证据，
  以及 ROI 取 `bounds_` 的代码依据，**没有直接量到 ROI 像素数**。
- G1 只跑了一轮 60 s，样本量为 1，不能据此推断「停录失败率」。
- 本轮测的是装机 DLL `1d0b52f2…`，仓库 HEAD `b92d042` 不能标识被测二进制。

## 8. 复现

```bash
cd 05_验证

# 1) 备份并写入轻量编码参数（Windows 路径）
#    %APPDATA%/obs-studio/basic/profiles/未命名/recordEncoder.json
#    原值： {"rate_control":"CBR","crf":0,"bitrate":8000}
#    降载： {"rate_control":"CBR","crf":0,"bitrate":8000,
#            "preset":"p2","multipass":"disabled","bf":0,"lookahead":false}

python ab_run.py --tag f1p2 --every 2 --lead 15 --seconds 120 --no-patch

# 2) 恢复原参数，重跑同长度对照
cp "$APPDATA/obs-studio/basic/profiles/未命名/recordEncoder.json.bak_f1_20261109" \
   "$APPDATA/obs-studio/basic/profiles/未命名/recordEncoder.json"
python ab_run.py --tag f1p5 --every 2 --lead 15 --seconds 120 --no-patch

# 3) 读结果：必须核对 preset / multipass / b-frames / lookahead 是否真是目标值
grep -A 14 "advanced_video_recording" "$APPDATA/obs-studio/logs/<最新>.txt"
grep "lagged\|skipped" "$APPDATA/obs-studio/logs/<最新>.txt"
```

复位清单：`recordEncoder.json` 回到 `{"rate_control":"CBR","crf":0,"bitrate":8000}`；
`视频.json` 未改动（全程 `--no-patch`）；`.sentinel/` 应为空。
