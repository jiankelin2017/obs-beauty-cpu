# OBS美颜 CPU `1.0.2.0` · 「色调整帧施加」取证记录

> 本文件是 `05_验证/` 下的取证副本，**不是 Active 文档**，`docs/INDEX.md` 不登记它。
> 台架源码与三个可执行文件在同目录 `_tone_global_probe/`；`.raw` 帧与 `.exe` 按 `.gitignore` 不入库。
> 本轮**没有**在 OBS 里出图（本机摄像头报 `data.GetDevice failed`），观感仍待人工确认。

| 字段 | 值 |
|---|---|
| 改动 | `01_源码/beauty_freq.cpp`：`toneColor()` 默认**整帧施加**（不乘皮肤掩码，`BEAUTY_TONE_GLOBAL=1`，对齐 GPU 版）；`BEAUTY_TONE_GLOBAL=0` 恢复 `1.0.1.0` 行为 |
| 台架 | `_tone_global_probe/tone_probe.cpp` —— 直接调 `beautycore::toneColor()`，同一份输入 + 同一张**合成**软边椭圆掩码（25.52% 面积，12 px 羽化），只切换环境变量 |
| 素材 | 真机帧 `参考文件/02_原始帧数据/probe_in.raw`（640×394 RGBA）；SDK 真值对 `out_white_off.raw` / `out_white_on.raw`（同场景美白开关切换）；计时用 1920×1080 帧 `05_验证/全项对齐_20261030/_mx_whiten_100_core.raw` |
| 结论 | A PASS（回退逐字节一致）、B PASS（`=1` 掩码外改动 49,673 px、箱内 σ 0.00）、C PASS（SDK 差值 bbox 与本工程 `=1` 完全一致） |

## 1. 判据 A：回退开关等于改动前的实现

`probe_old.exe` 用 `b92d042:01_源码/beauty_freq.cpp`（1.0.1.0 交付态）单独编译，
`probe_new.exe` 用当前源码 + `BEAUTY_TONE_GLOBAL=0`。两者的输出必须逐字节相同。

```
A. 回退保真（BEAUTY_TONE_GLOBAL=0 必须等于改动前实现）
   probe_old   md5 6E7714D3BC1CD03DD1A3D29057AC4E44
   probe_new=0 md5 6E7714D3BC1CD03DD1A3D29057AC4E44
   逐字节相同: True   → PASS
```

同一次运行里 `probe_new` 走 `=1` 的 md5 是 `1D970E9E8E0F873D15DC77FC75B9C8C0`，与上两者不同 ——
说明开关确实改变行为，不是「改了也没生效」。

## 2. 判据 B：掩码形状的色界是否消失

「箱内 σ」是本工程一贯的判据：按**输入灰阶**分箱后看 Δ 的离散度。σ≈0 表示 Δ 只由颜色决定，
与像素位置无关 —— 也就是画面里不存在任何空间边界。

```
B. 掩码边界是否还在（改动的全部意义）
   =0 掩码内: 改动像素  22.7%   掩码内   57222   掩码外       0
        箱内 σ（整帧） 1.90 灰阶 / （掩码内） 1.74 灰阶  共 210 箱
   =1 整帧: 改动像素  42.8%   掩码内   58327   掩码外   49673
        箱内 σ（整帧） 0.00 灰阶 / （掩码内） 0.00 灰阶  共 210 箱
```

读法：

- `=0` 的掩码外改动是 **0 像素**，所以掩码边界必然是一条色界；σ 1.90 就是「同一个输入灰阶，
  因为落在掩码内外不同位置而得到不同 Δ」的量化。
- `=1` 的掩码外也改了 49,673 像素，且 σ 归零 —— 手背拿到的是与全画面同一条曲线，
  不可能再出现「贴在手背上的椭圆」。
- 掩码内改动的像素数几乎不变（57,222 → 58,327，差异来自 LUT 展开与整帧边界像素），
  说明这不是「把效果整体加强」，而是**改了施加范围**。


```
   改动像素 31.0%   bbox x172-466 y0-393
   本工程 =0 掩码内: bbox x172-466 y49-313
   本工程 =1 整帧: bbox x172-466 y0-393
```

`out_white_on/off` 是同一场景下 SDK 美白开关的开关对：差值铺满整条 9:16 视频带
（`x172-466 / y0-393`，含头发、衣服、背景），不是「某块脸被点亮」。
本工程 `=1` 的改动 bbox 与之**逐位相同**；`=0` 只在 `y49-313`（脸区）动。

## 4. 代价（1080p / 8 线程 / 美白 100）

`_mx_whiten_100_core.raw`（1920×1080），每档 30 次取单轮值，跑 3 轮（同机 Intel Ultra 7 255HX / 20 线程）：

| 轮次 | `BEAUTY_TONE_GLOBAL=0` | `=1` |
|---|---|---|
| 1 | 1.35 ms | 4.02 ms |
| 2 | 1.27 ms | 3.63 ms |
| 3 | 1.25 ms | 2.85 ms |

- 面积是 3.9 倍（掩码占 25.59%），耗时约 2.4 倍 —— 单像素反而更便宜：17 锚点表预展开成
  256 项之后，每像素从「2 次 lut17 × 3 通道」降到「1 次查表 + 线性插值」。
  `BEAUTY_TONE_GLOBAL=0` 一行回退，不必换 dll。

## 5. 复算命令

```powershell
# 1) 重建台架（旧实现从 b92d042 现取，不落库）
powershell -NoProfile -ExecutionPolicy Bypass -File 05_验证\_tone_global_probe\build_probes.ps1

# 2) 跑三份输出（640×394 真机帧，美白 100）
$p = '05_验证\_tone_global_probe'; $f = '参考文件\02_原始帧数据\probe_in.raw'
& "$p\probe_old.exe" $f 640 394 0 1 0 "$p\out_old.raw"  "$p\mask.raw"
$env:BEAUTY_TONE_GLOBAL='0'; & "$p\probe_new.exe" $f 640 394 0 1 0 "$p\out_new0.raw" "$p\mask.raw"
$env:BEAUTY_TONE_GLOBAL='1'; & "$p\probe_new.exe" $f 640 394 0 1 0 "$p\out_new1.raw" "$p\mask.raw"
Remove-Item Env:\BEAUTY_TONE_GLOBAL

# 3) 判据 A/B/C
$env:PYTHONUTF8='1'; py -3 05_验证\_tone_global_probe\tone_global_check.py

# 4) 计时（1080p / 8 线程 / 30 次）
$env:TONE_PROBE_REPEAT='30'; $env:TONE_PROBE_THREADS='8'
$env:BEAUTY_TONE_GLOBAL='0'; & "$p\probe_new.exe" 05_验证\全项对齐_20261030\_mx_whiten_100_core.raw 1920 1080 0 1 0 "$p\_t0.raw"
$env:BEAUTY_TONE_GLOBAL='1'; & "$p\probe_new.exe" 05_验证\全项对齐_20261030\_mx_whiten_100_core.raw 1920 1080 0 1 0 "$p\_t1.raw"
```

## 6. 本记录不覆盖什么

1. **真机出图与观感** —— 没在 OBS 里看到画面；本机摄像头 `data.GetDevice failed`。
2. **物理手遮脸素材** —— 台架用的是合成椭圆掩码 + 真机帧，不是「手托腮 / 手挡眼」片段；
   本仓库没有这类素材（与 `docs/design/design-face-mask.md` §12 记的同一个缺口）。
3. **整条管线的其它项** —— 磨皮 / 锐化 / 五官仍按皮肤掩码走，本轮一字未改。
4. **无脸帧** —— 色调仍只在 `haveMask` 时施加；脸彻底丢失时整幅亮度会一起回到原图，
   这条路径**未单独实测**（见 `docs/CHANGELOG.md` §2 的 `1.0.2.0`「行为边界」一行）。

> 补正（2026-11-08 17:36）：以上第 1 条描述的是本轮台架取证当时的状态，保留原貌。之后 16:51–17:22 的真机运行（装机 `1.0.3.0`）已在 OBS 内实际出图，`data.GetDevice failed` 不再出现，自动方向探测也命中 270°（"2026-11-08 16-51-40.txt" l. 107, l. 274, l. 270–273）；片内 A/B 性能对照见 `05_验证/ab_perf_20261108.md`。**第 2 条「物理手遮脸素材」缺口仍然存在**，本批没有对手背做逐帧观感判定；`1.0.2.0` 的 40 项装卸回归也仍未复跑。
