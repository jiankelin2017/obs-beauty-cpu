> **ARCHIVED · 已废弃，见根 `README.md` §1、§3**
> 归档日期：2026-11-06 · 状态：`Deprecated` · 适用代码版本：历史轴 `3.1.39 / core 1.4.0`（**非当前 CPU `1.0.0.0`**）
> 废弃原因：本文是「GPU 移植开发计划稿（待用户确认开工）」，目标是把滤镜 GPU 化。当前产品线已明确 **纯 CPU、不依赖 GPU**，方向直接冲突，且该计划从未开工；主目录不得保留。
> 本文为历史原件，正文未改写、未删减，**不得据此施工**。GPU 版是另一仓库、另一条版本轴（`3.0.1`），不可互比。
> 维护人：待人工确认 · 最后核对：2026-11-06

---

# 方案 A：OBS 美颜插件 GPU 移植开发计划

> 状态：计划稿（待用户确认开工）｜依据：`01_源码` 代码探查 + 根 `README.md` + `obs-beauty.cpp` 性能埋点
> 目标产物：现有 OBS 美颜滤镜（`obs_beauty_filter`，v3.1.39 / 引擎 core 1.4.0）的 GPU 化版本
> 动机：用户明确——**降低 CPU 功耗**（非单纯提帧率）。理论降幅见对话：CPU 占用 9%→约 4%（区间 2–6%），折算 CPU 功耗约降到原来的 40%。

---

## 一、目标与动机

- **主目标**：把占 CPU 大头的逐像素运算（磨皮 / 美白 / 红润 / 清晰 / 五官立体 / 美型 / 细节回填）从 CPU 多线程搬到 GPU，让画面全程留在显存，消灭 `gs_stage_texture → gs_texture_map`（D3D11 Map 同步等待）→ CPU 处理 → `gs_texture_set_image` 上传的往返。
- **功耗动机**：CPU 负载下降后，DVFS 主动降频降压，CPU 功耗 ∝ 占用^α（α≈1.2–1.5），降幅大于占用降幅。人脸检测已走 DirectML GPU，无需动。
- **非目标**：不动人脸检测（已 GPU）；不做纯 DirectML 算子图（见第四节，方案 B 更贵更险）；不删 CPU 引擎（保留作兜底 + 回归 golden）。

## 二、架构总览（GPU 主 + CPU 辅 / 兜底）

```
OBS D3D11 纹理
   │  (不下载 CPU)
   ▼
[GpuBeautyEngine::processGpu]  ← 新增，实现 IBeautyEngine
   ├─ Pass1 tone.hlsl      美白/红润/清晰/五官立体(+region mask)   → 色调纹理
   ├─ Pass2 blur_sep.hlsl  可分离高斯(横/竖)                       → 模糊纹理
   ├─ Pass3 skin.hlsl      引导/表面3混合 + 振幅门控               → 磨皮纹理
   ├─ Pass4 blend.hlsl     按皮肤掩码 + 强度 t 混合原图            → 混合纹理
   ├─ Pass5 warp.hlsl      按位移图重采样(瘦脸/大眼/下巴)          → 变形纹理
   └─ Pass6 detail.hlsl    细节回填(加回高频/锐化)                 → 输出纹理
   ▼
回 OBS 绘制
```

**CPU 在稳态下只做（"辅"）：**
1. 人脸检测主机侧后处理：从 ONNX(DirectML) landmarks 算**位移图**与**皮肤掩码**（小数据，缓存），上传为纹理/常量缓冲；
2. 每帧准备着色器**常量缓冲**（参数、区域参数）；
3. OBS 胶水（取帧、读面板参数、绘制）。

**CPU 引擎（core 1.4.0）保留为：**
- `BEAUTY_GPU=0` 或 `auto` 探测失败时的**兜底**；
- GPU 每个算子改写完后的**逐像素 golden 对拍基准**（守 79.0 复刻分）。

## 三、关键技术决策

| 决策点 | 结论 | 理由 |
|---|---|---|
| GPU 后端 | **D3D11 HLSL 着色器**（像素/计算），非纯 DirectML | OBS 是 D3D11，DirectML 跑 D3D12 需 D3D11↔D3D12 互操作，复杂度×2、风险高；DirectML 是推理框架，表达逐像素算子别扭 |
| 人脸检测 | 保持现有 DirectML（已 GPU） | 不动、不回退 |
| 引擎接口 | 扩展 `IBeautyEngine`，新增 `processGpu(slot, gs_texture_t* in, gs_texture_t* out, ...)` | CPU 引擎也实现它（内部下载→CPU process→上传），统一调用面；兜底零成本 |
| 资源生命周期 | 每 slot 的 GPU 中间纹理/常量缓冲随源 resize 重建，复用 `obs-beauty.cpp` 现有 `f->stage/out_tex` 管理套路 | 防泄漏、防 resize 崩溃 |
| 开关 | `BEAUTY_GPU` 环境变量（0/1/auto，命名对齐 DaVinci 端）+ 面板"渲染后端"下拉 | auto=探测 D3D11 compute 可用性，失败回 CPU |
| 量化对齐 | 每算子 A/B 对拍（CPU 当 golden，diff 阈值），必要时定点近似 | 守 79.0 分与 11 项对齐 |

## 四、引擎接口改造（beauty_core.h / beauty_core.cpp）

当前：`virtual bool process(int slot, const unsigned char* src, unsigned char* dst, ...)`（CPU 路径，glue 先下载再调）。

新增（不影响现有 CPU 路径）：
```cpp
// 在 IBeautyEngine 中新增
virtual bool processGpu(int slot, void* in_tex, void* out_tex,
                        int w, int h, const BeautySettings& s) = 0;
```
- `CoreEngine`（CPU）：`processGpu` 内部 `gs_texture_map` 下载 → 原有 `process` → `gs_texture_set_image` 上传。**行为与现有一致，保证兜底等价。**
- `GpuBeautyEngine`（新增 `beauty_gpu.cpp` + `beauty_gpu.h`）：原生在纹理上跑着色器，全程不回 CPU。
- `obs-beauty.cpp`：`BEAUTY_GPU != 0` 时改走 `processGpu`（不下载）；`== 0` 时仍走原 `process`。

## 五、着色器清单（01_源码/shaders/，新增目录）

| 文件 | 职责 | Pass 数 | 难度 |
|---|---|---|---|
| `tone.hlsl` | 美白/红润/清晰/五官立体（region mask 乘区域增益） | 1（合成） | 低（逐像素映射） |
| `blur_sep.hlsl` | 可分离高斯（横+竖两趟），喂 surface3 | 2 | 中 |
| `skin.hlsl` | 引导/表面3 混合 + 振幅门控（保边近似 bilateral） | 2–3 | **高**（数值敏感） |
| `blend.hlsl` | 按皮肤掩码 + 强度 t 混合原图与磨皮图 | 1 | 低 |
| `warp.hlsl` | 按位移图重采样（瘦脸/大眼/下巴），uv 含 flipY 修正 | 1 | 中（复用 DaVinci 的 flipY 坑经验） |
| `detail.hlsl` | 细节回填（加回高频/锐化） | 1 | 低 |

> 复用现有 `beauty_smooth.cpp` 的 `lvI/lvE/lvT` 查表与 `beauty_warp.cpp` 的几何量（`makeGeom` 的 `flipY` 逻辑）——**只改"怎么算"，不改"算什么"，保证量化分不降。**

## 六、分阶段移植计划

### Phase 0 — 基线测量（0.5 天，只读）
- 动作：`BEAUTY_PROFILE=1` 量 1080p/4K 的 下载/引擎/上传 ms；同时用 `typeperf "\Process(obs-studio)\% Processor Time"` 或 HWiNFO 采 CPU 占用/功耗（开美颜 vs 关美颜）。
- 产出：基线表（含 `引擎` ms 与 CPU 占用/功耗），作为"做完省多少"的硬证据，也用于反推 `B`（美颜占 CPU 比）与 `f`（像素计算占比）。
- 门禁：无。纯测量，不动代码。

### Phase 1 — GPU 调度层 + 开关（1 天）
- 涉及：`beauty_core.h/.cpp`（加 `processGpu` 虚函数 + `GpuBeautyEngine` 桩）、`beauty_gpu.cpp/.h`（新建，先只做"直通"）、`obs-beauty.cpp`（加 `BEAUTY_GPU` 分支，auto 探测 D3D11 compute）、`beauty_params.h`（加 `render_backend` 字段）。
- 技术方案：GPU 路径先只做"直通"（读纹理→原样写回），跑通纹理接驳与常量缓冲，不引入任何算子。
- 门禁：`BEAUTY_GPU=0/1/auto` 切换无崩溃；直通输出与 CPU 逐字节一致。

### Phase 2 — 色调类算子 GPU 化（2 天，高收益低风险）
- 涉及：`tone.hlsl` + `beauty_gpu.cpp` 的 tone pass；`beauty_region.cpp` 的 5 项局部增益改由 region mask 纹理传入。
- 技术方案：美白/红润/清晰/立体/全局锐化为**一个 HLSL pass**（src 纹理 + 参数常量缓冲 → dst）。无邻域依赖，并行度最高，最易做对。
- 门禁：逐像素 diff ≤1 灰阶；复刻评分不降（清晰 93.1 / 美白 75.1 / 红润 79.8 / 立体 79.4）。

### Phase 3 — 磨皮 GPU 化（3–4 天，核心难点）
- 涉及：`blur_sep.hlsl` + `skin.hlsl` + `beauty_gpu.cpp`。
- 技术方案：
  - 高斯类 → `blur_sep.hlsl` 两趟可分离；
  - **保边（bilateral）有值域依赖**→ 用"引导图 + 分离高斯"近似（复用 surface3 的 guide 思路），先近似后精确；
  - 混合/振幅门控 → `blend` 前的 `skin.hlsl` 合成 pass。
  - 复用 `lvI/lvE/lvT` 标定，只改实现。
- 门禁：`score_replica.py` 磨皮分 ≥82.7（原值）；离线对齐 JSON 复跑通过。

### Phase 4 — 美型（瘦脸/大眼/下巴）GPU 化（2 天）
- 涉及：`warp.hlsl` + `beauty_gpu.cpp`；`beauty_warp.cpp` 的 `makeGeom`/`flipY` 逻辑移到 CPU 算位移图（缓存），GPU 仅采样。
- 技术方案：几何变形=按位移场重采样，GPU 天然适合；**bottom-up 行序坑**直接复用 DaVinci 那边修过的 `flipY` 修正（视觉下沿/上沿不等式 + 比例换算）。
- 门禁：真机 5 关键点位移与 CPU 一致；可选 shape 基准对拍。

### Phase 5 — 细节回填 + 整合 + 回归（2 天）
- 涉及：`detail.hlsl` + `beauty_gpu.cpp` 串联；`obs-beauty.cpp` 接 `processGpu` 全链路。
- 技术方案：全管线串联，中间结果尽量留 GPU（不回 CPU）；全 0 参数透传、IsIdentity 等契约保持。
- 门禁：复刻评分 ≥79.0（主口径）、逐项达标 6/8 不降；11 项对齐全过；`BEAUTY_PROFILE` 对比 Phase 0 确认"下载+引擎"项归零（引擎项应≈0）。

**合计 ≈ 10.5–11.5 人天。**

## 七、工程与版本（按用户永久规则）

GPU 化 = 架构重写 / 破坏性变更 → **主版本 +1，其余归零**：
- 引擎 core：`1.4.0 → 2.0.0`
- 滤镜：`3.1.39 → 4.0.0`
- CPU 旧路径保留作回退，但版本号按"大版本"处理；`NAMA_BUILD_*` 同类宏在 `beauty_core.h` 同步升。

## 八、验收门禁总表

| 维度 | 门禁 |
|---|---|
| 功能 | 复刻评分 ≥79.0（主口径）、逐项达标 6/8 不降；11 项对齐全过 |
| 性能 | 1080p/4K 下"下载+引擎"相比 Phase 0 基线下降 ≥70%；目标 4K60 不卡 |
| 功耗 | CPU 占用相比基线下降（理论 9%→约 4%）；`BEAUTY_GPU=0` 时回到原 CPU 占用（验证兜底等价） |
| 兼容 | `BEAUTY_GPU=0` 逐字节回退 CPU；`auto` 在任意 DX12 机器可用；OBS 30（D3D11）通过 |
| 工程 | `verify_roi` / `score_replica` / 离线对齐 JSON 全绿；md5 不可复现老坑仍用 `verify_roi` 哈希验证源码 |

## 九、风险登记

1. **量化对齐回退（最高）**：GPU 浮点顺序不同，保边/引导滤波易漂。对策：每算子 A/B 对拍（CPU golden），必要时定点近似。
2. **资源生命周期**：每 slot GPU 纹理/常量缓冲随 resize 重建、旧资源释放。对策：复用 `f->stage/out_tex` 管理套路。
3. **跨帧状态**：异步人脸检测 worker + 区域缓存 + 掩码池仍有状态。对策：检测仍 CPU 小数据，landmarks/mask 传 GPU。
4. **OBS 后端版本**：OBS 30 仍 D3D11；需确认 OBS 31 是否转 D3D12（影响 `gs_get_device` 取法）。
5. **可调试性**：GPU 出错难定位。对策：每 pass 后接一次 stage 回读 self-check（复用现有机制）。
6. **功耗反作用（需预期）**：GPU 负载从 0 起，平台总功耗净降但通常小于 CPU 单项降幅；若目标是笔记本电池，净收益打折扣，但 CPU 温度/风扇确定性利好。

## 十、启动确认（下一步）

待用户确认后从 **Phase 0（基线测量）** 开工——该步只读，仅跑 `BEAUTY_PROFILE` + CPU 占用/功耗采样，**不碰任何代码**，产出基线表后即暂停汇报，再决定是否进入 Phase 1。
