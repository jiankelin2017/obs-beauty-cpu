# OBS 美颜摄像头（obs-cam-beauty）· 磨皮与美颜 全量分析总览

> **文档用途**：本次逆向分析（A 静态 + B 动态双路线）的全部重要表格与发现，单文件速查，供后续学习/复现/二次开发使用。
> **取证方式**：REA v6.8.0 静态分析（导出表、字节扫描、capstone 手动反汇编）+ Frida 动态注入（`beauty.exe` 内 hook `CNamaSDK.dll` setter）+ 解密 `.bundle` 堆内存雕刻。
> **时间**：2026-10-29
> **标注约定**：`【已验证】` = 静态/动态坐实；`【推断】` = 依据 shader 语义或字符串推导，未被动态取证直接验证。

---

## 目录
1. 系统架构（4 层）
2. 磨皮算法总览（双级）
3. tex_surfaceblur1/2 的生成
4. 引擎 uniform 参数全表
5. 管线中间产物（掩码 → 关键点 → 保护掩码 → 高低频）
6. UI 滑块 → 引擎参数映射
7. 面板 0/25/50/75/100 → uniform 值表（B 路线真值）
8. B 路线捕获的完整参数名清单
9. 配套模块（美白 / 瘦脸 / 美妆）
10. 事实 vs 推测总表
11. 工具限制与已知坑
12. 证据文件索引

---

## 1. 系统架构（4 层）【已验证】

| 层 | 文件 | 职责 | 关键证据 |
|---|---|---|---|
| UI 壳 | `obs-cam-beauty_qt6.dll`（obs64 内，3.79MB） | 仅导出标准 `obs_module_*` 壳函数；持有高层 UI 参数键；经 `BEAUTY_BRIDGE_PIPE` IPC 通信 | 仅 9 个导出；串搜索见 `BEAUTY_BRIDGE_PIPE`、`BEAUTY_SETTING_`、`blur_level`/`cheek_thinning`/`eye_enlarging` |
| 引擎宿主 | `beauty.exe`（64bit，1.45MB） | 子进程，链接 CNamaSDK，真正执行引擎 | 动态插桩确认 CNamaSDK 基址落在 `beauty.exe` 子进程（非 obs64） |
| 引擎 | `CNamaSDK.dll`（19.8MB） | 解密 `.bundle`、加载 GLSL、执行 `fuItemSetParam` | 串搜索见 `blur_intensity`、`blur_amount_s_clear_blur_mix`、`fuItemSetParam` 等（各 100+ 处） |
| 资源 | `common/assets/{graphics,items,model}/*.bundle` | 加密的美颜资源（含 GLSL 着色器） | 解密后堆内存即 bundle 明文 |

**数据流**：
```
UI 滑块 (obs-cam-beauty_qt6.dll)
   ↓ IPC：BEAUTY_BRIDGE_PIPE（命名管道，高层键 → 引擎键）
引擎宿主 beauty.exe + CNamaSDK.dll
   ↓ fuItemSetParamd(itemHandle, key, value)（每帧重发）
AI 人脸检测 (fuai.dll) ──→ 关键点 ──→ 掩膜 tex_mask
   ↓
GLSL 着色器 (face_beautification 等) ──→ 磨皮 / 美白 / 瘦脸
   ↓
输出磨皮后画面帧
```

> **关键结论**：像素级算法代码封在加密 `.bundle` 中，需授权 authpack 经 `fuSetup` 初始化后由 `fuCreateItemFromPackage` 解密；解密后的 GLSL 在 `beauty.exe` 堆里以明文驻留。

---

## 2. 磨皮算法总览（双级）

磨皮**不是**单一高斯模糊，而是 **FaceUnity Nama SDK 在 GLSL 里实现的「双级边缘感知磨皮」**：

### 2.1 第一级：边缘感知预模糊（`void main`）【已验证】

```glsl
void main() {
  lowp vec4 origin_color = texture2D(tex_origin, st);
  lowp vec4 mask_color   = texture2D(tex_mask, st);
  lowp vec4 ret_color    = origin_color;
  if (mask_color.a > 0.001) {                          // 仅在皮肤区域
    lowp vec4 blur_color = texture2D(tex_pre_blur, st); // 预模糊图（低频）
    blur_color.a = origin_color.a;
    float dis = distance(vec3(0.0),
                    max(blur_color.rgb - origin_color.rgb, 0.0)) * 30.0;
    float factor = 1.0;
    factor = step(0.5, dis);                            // dis<0.5：不磨
    factor = (1.0 - smoothstep(5.0, 6.0, dis)) * factor; // dis>6：不磨
    if (dis > 0.5 && dis < 5.0) {                       // 仅中频区
      ret_color = shader_main_s_pre_enlighten(
          origin_color, factor * blur_intensity * mask_color.a * 0.25);
    }
  }
  gl_FragColor = ret_color;
}
```

**边缘判断 `dis` 表**（`dis = |blur−origin| × 30`）：

| dis 区间 | 含义 | 处理 |
|---|---|---|
| < 0.5 | 平坦皮肤 | 不磨（防噪/塑料感） |
| 0.5 ~ 6.0 | 中频（毛孔/细纹） | **磨** |
| > 6.0 | 五官强边缘 | 不磨（保边） |

### 2.2 第二级：双表面模糊（`shader_main_s_surfaceblur_mix`）【已验证】

```glsl
vec4 shader_main_s_surfaceblur_mix(vec2 st, vec4 C) {
  if (blur_amount_s_clear_blur_mix < 0.001) return C;   // 强度≈0 直接返回
  lowp vec3 blur1 = texture2D(tex_surfaceblur1, st).rgb; // 表面模糊层1（轻）
  lowp vec3 blur2 = texture2D(tex_surfaceblur2, st).rgb; // 表面模糊层2（重）
  lowp vec4 mask  = texture2D(tex_mask, st);
  lowp float eye_mask = 0.0;
  if (mask.g > 0.0 && mask.r <= 0.1 && mask.b <= 0.1)    // 绿色通道=眼睛
    eye_mask = mask.g;
  lowp float skin_mask = mask.a;                          // alpha=皮肤
  lowp float intensity = blur_amount_s_clear_blur_mix;
  // 可选肤色检测：非皮肤像素降低模糊
  #ifdef USE_SKIN_DETECT
    if (skin_detect_s_clear_blur_mix > 0.5) {
      // RGB 肤色阈值判定，非皮肤则 intensity *= nonskin_blur_scale
    }
  #endif
  intensity = mix(intensity * 1.4286, 1.0, step(0.7, intensity));
  lowp float evenfactor = mix(0.3, intensity - 0.3, step(0.6, intensity));
  lowp vec3 diff = (C.rgb - blur1) * 0.5 + 0.5;           // 高频（细节）
  lowp vec3 even = clamp(2.0 * diff + blur2 - 1.0, 0.0, 1.0); // 细节保持合成
  even = mix(C.rgb, even, skin_mask);                     // 仅皮肤内混合
  even = mix(even, blur2, skin_mask * evenfactor);
  lowp vec3 res = mix(C.rgb, even, intensity);
  result_color = vec4(mix(C.rgb, res, (1.0 - eye_mask)), C.a); // 眼睛完全不模糊
  // 可选锐化：USE_SHARPEN 下做高通锐化补偿
}
```

### 2.3 频率分解公式（核心思想）【已验证】

| 层 | 公式 | 含义 |
|---|---|---|
| 低频（模糊图） | `blur1` / `blur2` | 肤色是否均匀 |
| 高频（细节） | `diff = (C.rgb − blur1) × 0.5 + 0.5` | 毛孔 / 细纹 / 质感 |
| 合成 | `even = clamp(2.0·diff + blur2 − 1.0, 0, 1)` | 低频底 + 高频叠回 → **磨皮但保留质感** |

### 2.4 混合公式（另一条磨皮 pass）【已验证】

```glsl
float blur_level_c = clamp(blur_level, 0.0, 1.0);
gl_FragColor = vec4(mix(col_blur.rgb, col_input.rgb, 1.0 - blur_level_c), 1.0);
```
→ `blur_level` 是 `[0,1]` 线性 uniform，`mix` 线性插值，**无曲线**。

### 2.5 皮肤/五官掩膜通道约定【已验证】

| 通道 | 含义 | 作用 |
|---|---|---|
| `.a` (alpha) | 皮肤区域掩膜 | 磨皮仅在皮肤内生效（`skin_mask`） |
| `.g` (green) | 眼睛 / 五官区域 | 磨皮时被保护（`eye_mask`，最终 `mix(C,res,1−eye_mask)` 眼睛完全不模糊） |
| `.r` (red) | 非肤检测 | `mask.r<=0.1 && mask.b<=0.1` 用于判定眼区 |
| `.b` (blue) | 皮肤（美白用） | 美白模块使用 |

---

## 3. tex_surfaceblur1/2 的生成（表面模糊）

### 3.1 生成架构【已验证】
- 先由 `blur_h_fs.glsl`（横）+ `blur_v_fs.glsl`（纵）做分离模糊打底；
- 再由 `clear_blur.glsl`（表面模糊）现场生成两级产物：
  - `tex_surfaceblur1`（轻）—— 用于提取高频 `diff = (C − blur1) × 0.5 + 0.5`；
  - `tex_surfaceblur2`（重）—— 作为低频底，参与合成 `even = clamp(2.0·diff + blur2 − 1.0, 0, 1)`。

### 3.2 固定参数表【已验证，来自 bundle `config.json` + 解密 GLSL】

| 参数 | 值 | 含义 |
|---|---|---|
| `blur_size` | **4.0** | 模糊半径（采样窗口半径） |
| `blur_times` | **2** | 迭代次数（同窗口重复平均 2 遍） |
| 肤色阈值（`USE_SKIN_DETECT`） | 见 3.3 | 皮肤/非皮肤硬判定 |

### 3.3 肤色判定阈值【已验证】
```
r > 0.371 && g > 0.156 && b > 0.078
&& r > b && r > g
&& |r − g| > 0.059
&& (max(r,g,b) − min(r,g,b)) > 0.059
```
满足 → 判定为皮肤，保持磨皮强度；否则 `intensity *= nonskin_blur_scale_s_clear_blur_mix`（衰减）。

### 3.4 生成算法【重建，非逐字提取】
表面模糊 = 在 `blur_size` 半径窗口内算局部均值 μ 与方差 σ²：
- `|I − μ| < k·σ` → 保留原像素（保边、保纹理）；
- 否则 → 向 μ 混合（平坦区磨平）。

blur1（轻）/ blur2（重）两级仅混合比例与迭代强度不同。

### 3.5 诚实标注
`clear_blur` / `blur_h_fs` / `blur_v_fs` 三个**生成 shader 的逐行 GLSL 源码体在已解密堆文本中未干净捕获**（仅捕获到文件名清单）。本节给出的是 **参数级结论 + 算法重建**，非逐字源码。

---

## 4. 引擎 uniform 参数全表【已验证（名称与范围）】

| 参数名 | 含义 | 控制阶段 | 备注 |
|---|---|---|---|
| `blur_intensity` | 磨皮强度 | 第一级边缘感知模糊 | 与 `mask.a`、`0.25` 系数共同决定混合量 |
| `blur_amount_s_clear_blur_mix` | 表面模糊混合量 | 第二级双表面模糊（**主驱动**） | `<0.001` 时直接返回原图 |
| `blur_level` | 磨皮混合系数 | 另一条磨皮 pass | `clamp(blur_level, 0, 1)`，线性 `mix` |
| `blur_fs` / `blur_h_fs` / `blur_v_fs` | 模糊滤波器尺寸（含横/纵向） | 模糊核生成 | 控制模糊半径 |
| `blur_size` / `blur_times` | 模糊核大小 / 迭代次数 | 模糊核生成 | **固定 4.0 / 2** |
| `skin_detect_s_clear_blur_mix` | 肤色检测开关（>0.5 启用） | 保护 | 配合 `USE_SKIN_DETECT` |
| `nonskin_blur_scale_s_clear_blur_mix` | 非皮肤区域模糊衰减系数 | 保护 | 非肤像素模糊强度乘此值 |
| `sharpen_s_clear_blur_mix` | 锐化（清晰）强度 | 补偿 | 配合 `USE_SHARPEN` 高通锐化 |
| `widthOffset_s_clear_blur_mix` / `heightOffset_s_clear_blur_mix` | 锐化采样偏移 | 补偿 | 高通核的邻域偏移 |
| `color_level_s_color_custom_shader_whitten` | 美白强度 | 美白 | 按 `skin_mask` 混合 |
| `color_scale_s_color_custom_shader_whitten` | 美白提亮缩放 | 美白 | 预乘提亮 |
| `dim_s_*` / `raw_s_*` / `col_s_*` | 美白/提亮 3D-LUT 网格维度 | 美白/提亮 LUT | 定位 LUT 采样格 |

**已验证的 uniform 取值范围**：`blur_amount_s_clear_blur_mix` [0,1]（守卫 <0.001）；`blur_intensity` [0,~1]；`blur_size`/`blur_times` 固定 4.0/2；`skin_detect` 0/1 开关；`sharpen_*`/`color_level_*` [0,1]。

---

## 5. 管线中间产物（掩码 → 关键点 → 保护掩码 → 高低频）

**① 掩码（Mask）**
- 主掩码 `tex_mask`（多通道）：`.a`=皮肤、`.g`=眼睛/五官、`.r`=非肤检测、`.b`=皮肤（美白用）
- 独立皮肤掩码 `tex_skin`；眼睛掩码 `tex_eye_mask`
- 嘴/脸遮挡 `tex_mouthoccu` / `tex_face_occu_blur`
- 分割掩码 `tex_segmentation` / `tex_bg` / `tex_background` / `tex_back_blur`（背景虚化）

**② 关键点（Key points）** —— 由人脸 AI 追踪输出，传入形变着色器
- 轮廓：`p_nose`、`p_chin`、`p_chinleft`、`p_chinright`、`p_chinleft_u`、`p_chinright_u`
- 变换/索引：`p_origin`、`p_rot`、`p_flip`、`p_inv`、`p_faceright`、`p_5`、`p_6`、`p_8`、`p_C`、`p_T`、`p_f`、`p_type`

**③ 保护掩码（Protection mask）** —— 从掩码派生，决定「哪里不磨」
- `eye_mask`（由 `mask.g`）：眼睛/五官完全不参与模糊（`mix(C,res,1.0−eye_mask)`）
- `skin_mask`（由 `mask.a`）：模糊只在皮肤区域内生效
- 非皮肤衰减：开 `USE_SKIN_DETECT` 时，非肤像素强度 ×`nonskin_blur_scale` 衰减

**④ 高低频层（High / Low frequency layers）** —— 磨皮核心分解
- 低频（拿去磨平）：`tex_surfaceblur1`/`blur1`、`tex_surfaceblur2`/`blur2`、`tex_pre_blur`
- 高频（细节/毛孔，要保留）：`diff = (C.rgb − blur1) × 0.5 + 0.5`
- 合成：`even = clamp(2.0·diff + blur2 − 1.0, 0, 1)` → **磨皮但保质感**
- 基准：`tex_origin`（全频原图）

---

## 6. UI 滑块 → 引擎参数映射

### 6.1 UI 层参数顺序【已验证，从 `.rdata` 字符串实抽】
```
skin_dect_en → balance_smooth → heavy_blur → blur_level
→ disable_skinseg → color_level_type → color_level → clarity
```
- **`blur_level` 是「磨皮」对应的 UI 参数名**（与 `heavy_blur` 并存，不同粒度）。
- 面板**不使用**标准 `obs_properties_add_int_slider`（调用数为 0），而是自定义 Qt 控件 `DoubleSlider` / `ParameterSettingWidget` / `QDoubleSpinBox`。

### 6.2 UI 键 → 引擎键 映射表【推断】

| UI 键（qt6.dll） | 对应引擎键 / 模块 | 功能 |
|---|---|---|
| `blur_level` / `heavy_blur` | `blur_intensity` + `blur_amount_s_clear_blur_mix` | 磨皮强度 |
| `sharpen` / `sharpen_level` | `sharpen_s_clear_blur_mix`（+`USE_SHARPEN`） | 清晰/锐化 |
| `cheek_thinning`/`cheek_narrow`/`cheek_small`/`cheek_short`/`cheek_v` | `faceStretch` 形变参数 | 瘦脸/窄脸/小脸/短脸/V 脸 |
| `eye_enlarging` | 眼部纹理坐标放大 | 大眼 |
| `eye_bright` | 眼部提亮 | 亮眼 |
| `tooth_whiten` | 牙齿美白 | 白牙 |
| `red_level` | `color_level_s_color_custom_shader_whitten` | 红润 |
| `skin_dect_en`/`enable_skinseg`/`disable_skinseg` | `skin_detect_s_clear_blur_mix`（+`USE_SKIN_DETECT`） | 肤色检测 |
| `background_blur`/`background_blur_value` | 背景分割模糊 | 背景虚化 |
| `beauty_makeup`/`beauty_hair` | makeup / hair bundle | 美妆 / 染发 |

> **桥接路径**：UI 键 → `BEAUTY_BRIDGE_PIPE`（命名管道 IPC）→ `beauty.exe` → `fuItemSetParam(itemHandle, engineKey, value)` → GLSL uniform。

---

## 7. 面板 0/25/50/75/100 → uniform 值表（B 路线动态真值）

### 7.1 关键修正（A → B 路线）
- A 路线（静态）曾推断「÷100 在 OBS 侧」——**已被 B 路线动态真值推翻**。
- B 路线（Frida hook `CNamaSDK.dll!fuItemSetParamd`，读 XMM0 低 32 位 float32）证实：**OBS 侧是恒等透传**，把面板整数原样当 float32 交给 SDK，不做 ÷100。

### 7.2 映射表

| 面板刻度 | OBS→SDK 出站 `blur_level`（float32，【已验证真值】） | GLSL uniform（SDK 内 ÷100 后，【推断】） |
|---|---|---|
| 0 | **0.0** | 0.00 |
| 25 | **25.0** | 0.25 |
| 50 | **50.0** | 0.50 |
| 75 | **75.0** | 0.75 |
| 100 | **100.0** | 1.00 |

- 左列**动态取证坐实**：OBS 插件把滑块值原样（float32）交给 SDK。
- 右列**推断**：A 路线从 GLSL 看到 `clamp(blur_level, 0.0, 1.0)`，说明喂给 shader 的 uniform 是 [0,1]；从 OBS 侧传的是 0–100，中间的 ÷100 只能由 SDK/bundle 完成。

### 7.3 证据细节（xmm0 原始值，B 路线实抽）

| `xmm0` 低 32 位（hex） | f32 解码 | 对应面板值 |
|---|---|---|
| `0x40000000` | 2 | 2 |
| `0x42480000` | 50 | 50 |
| `0x42c80000` | 100 | 100 |
| `0x3f800000` | 1 | 1 |

- `xmm0.hi` 恒为 0；低 64 位当 double 读恒为 ~5.5e-315（无意义）→ 证明值在**低 32 位单精度**，不在 64 位双精度。
- 抓到 `blur_level` 取值覆盖 **1→100 连续整数**（去重 92 个）。
- 同进程 `filter_level` 实测传 `1.0`（已是 [0,1]）→ 佐证「逐参数约定不同」。

---

## 8. B 路线捕获的完整参数名清单（动态真值）

连续抓到的 `fuItemSetParamd` 参数名全集：

```
filter_name, filter_level, blur_level, delspot_level, color_level_mode2,
red_level, clarity, sharpen, face_threed, eye_bright, tooth_whiten,
remove_pouch_strength_mode2, remove_nasolabial_folds_strength_mode2,
cheek_thinning_mode2, eye_enlarging_mode3, intensity_eye_circle,
intensity_chin_mode2, intensity_forehead_mode2, intensity_nose_mode2,
intensity_mouth_mode3, intensity_lip_thick, cheek_v, cheek_narrow_mode2,
cheek_short, cheek_small_mode2, intensity_cheekbones, intensity_lower_jaw,
intensity_eye_height, intensity_canthus, intensity_eye_lid,
intensity_eye_space, intensity_eye_rotate, intensity_long_nose,
intensity_philtrum, intensity_smile, intensity_brow_height,
intensity_brow_space, intensity_brow_thick, BodySlimStrength,
LegSlimStrength, WaistSlimStrength, ShoulderSlimStrength, HipSlimStrength,
HeadSlim, LegSlim, is_clear_makeup, makeup_intensity, blur_type,
skin_detect, enable_skinseg, face_shape_level, face_shape
```

**观察**：本次 `clarity`/`red_level`/`color_level_mode2`/`face_threed` 在默认档为 0；`filter_level` 实测 1.0（归一化参数示例）。

---

## 9. 配套模块（美白 / 瘦脸 / 美妆）

| 模块 | 实现方式 | 关键点 |
|---|---|---|
| **美白** | 3D-LUT 色彩映射（`shader_main_s_color_custom_shader_whitten`） | 蓝色通道索引 LUT，`dim`/`raw`/`col` 为网格维度；按 `color_level × skin_mask` 混合，只美白皮肤 |
| **瘦脸** | 几何形变 `faceStretch(newCoord, p_chin, targetchin, radius)` | 基于关键点把轮廓网格 warp 推/拉，独立管线（改像素位置，非像素值） |
| **美妆** | `face_makeup.bundle` | 关键点定位五官，素材 warping 贴合再混合 |
| **背景虚化** | 分割掩码 `tex_segmentation` / `tex_back_blur` | 独立于磨皮 |

瘦脸形变关键片段【已验证】：
```glsl
float radius = face_width * 1.5;
vec2 targetchin = p_nose + (p_chin - p_nose) * 0.87;
vec2 chinplus   = faceStretch(newCoord, p_chin, targetchin, radius);
newCoord = newCoord - chinplus * myparameter2;
// 同理处理 p_chinleft/right（向鼻心 0.94 收缩）、p_chinleft_u/right_u
// 最终：return textureCoordinate + (newCoord - textureCoordinate) * myparameter;
```

---

## 10. 事实 vs 推测 总表

| 编号 | 内容 | 性质 |
|---|---|---|
| F1 | 像素级磨皮算法封于加密 `.bundle`，解密后 GLSL 明文已从堆取出 | 【已验证】 |
| F2 | 磨皮 = 边缘感知预模糊 + 双表面模糊 + 皮肤/眼睛掩膜 + 可选肤色检测/锐化 | 【已验证】 |
| F3 | 引擎在 `beauty.exe` 子进程（非 obs64），UI 经 `BEAUTY_BRIDGE_PIPE` IPC | 【已验证】 |
| F4 | UI 层 DLL 仅含高层参数键；着色器级参数键在 `CNamaSDK.dll` | 【已验证】 |
| F5 | `blur_size=4.0`、`blur_times=2`、肤色阈值（见 3.3） | 【已验证】 |
| F6 | 参数名 `blur_level` 经 `fuItemSetParamd` 下发；OBS 侧恒等透传 0–100，无 ÷100 | 【已验证】 |
| F7 | 频率分解公式 `diff`/`even`、`dis` 边缘判断、掩膜通道语义 | 【已验证】 |
| S1 | UI 键 → 引擎键的具体映射（表 6.2） | 【推断】 |
| S2 | SDK 内部把 0–100 映射为 GLSL [0,1]（÷100 在 SDK 内部） | 【推断】 |
| S3 | `clear_blur`/`blur_h_fs`/`blur_v_fs` 的逐行源码体（未捕获，仅参数+算法重建） | 【重建】 |

---

## 11. 工具限制与已知坑

| 问题 | 详情 | 绕行 |
|---|---|---|
| REA Ghidra 后端超时 | `CNamaSDK.dll`（19.8MB）超出启动时限（5m34s 超时，EXIT=1）；`xrefs`/`decompile` 同样 SIGTERM | 改用 `capstone 5.0.7` + `pefile` 手写反汇编 |
| `÷100` 位置静态不可追 | `blur_level` 字符串不出现在 `.text` 的 `lea` 引用，也不在数据段指针；经 `QString::fromUtf8`/字符串列表间接引用 | B 路线动态抓真值（已完成） |
| UI 滑块类型未定 | 自定义 `DoubleSlider`，未反编译出 `setRange` 参数 | B 路线实测为 0–100 整数 |
| Frida `ctx.rcx` 越界 | onEnter 首参是 `args` 数组，不是 `ctx` | 用 `args[0]`/`args[1]` |
| `Module.findExportByName` 不可用 | 该 REA Frida 运行时无此静态方法 | 用 `Process.findModuleByName` + `mod.base.add(RVA)` |
| 单独 hook `fuItemSetParamd` 零命中 | 该运行时怪癖：须同时挂 6 个 setter 才稳定触发 | 全挂 6 个 setter |
| `xmm0` 是 ArrayBuffer | 不能用 `NativePointer.and()` 解码 | 用 `DataView` 按 float32 读低 32 位 |
| OBS 中途重启 | PID 变化导致 attach 到死进程、零命中 | 每次先 `tasklist` 取当前 PID |
| `PK\x03\x04` 假阳性 | x64 代码字节可能恰为 ZIP 头 | 扫描时排除模块内存范围 |

---

## 12. 证据文件索引

| 文件 | 内容 |
|---|---|
| `beauty_algorithm_analysis.md` | 完整逆向分析报告（GLSL + 映射 + 事实/推测） |
| `beauty_source_readable.md` | 纯可读版：GLSL 源码 + 参数表（无文件路径） |
| `beauty_logic_study_guide.md` | 磨皮思路逻辑学习笔记（含图表说明） |
| `panel_uniform_mapping.md` | A 路线映射（顶部已标注被 B 路线修正） |
| `broute_result.md` | B 路线动态真值完整记录 |
| `conclusion_cheatsheet.md` | 两段结论速查（表面模糊参数 + 映射表） |
| `master_analysis.md` | **本文件：全量分析总览** |
| `heap_1..9_*.bin` | 解密堆内存（GLSL 明文来源） |
| `zip_1/zip_2_*.bin` | 合法 ZIP（含 FaceUnity authpack：`client.crt`/`client.key`/`beauty_info.txt`） |
| `frida_b*.txt` / `broute_capture*.jsonl` | Frida 动态捕获原始输出 |
| `CNamaSDK_exports.txt` | SDK 导出表（含 RVA） |

---

## 附：一句话收口

磨皮是「双级边缘感知 + 频率分解 + 掩膜限域」：第一级只磨中频（`dis∈(0.5,6.0)`）保五官边缘，第二级用 `even = 2·diff + blur2 − 1` 把毛孔细节加回低频底、做到「磨平不丢质感」，并用 `mask.a` 限皮肤、`mask.g` 保眼睛。滑块是裸 0–100 直送 SDK，÷100 由 FaceUnity SDK 内部完成；表面模糊半径固定 4.0、迭代 2 次。
