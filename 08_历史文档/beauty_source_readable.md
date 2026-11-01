# OBS 美颜摄像头 · 磨皮美颜 源码与参数（可读文档）

> 本文档为人工可读版：包含磨皮功能的**实际着色器源码（GLSL）**与**关键参数表**。
> 源码从美颜引擎解密后的资源中完整抽取，未做任何逻辑改写，仅整理缩进。
> 后续如需更深溯源，原始堆内存与日志留在分析目录供程序化检索。

---

## 一、磨皮算法源码（GLSL）

磨皮由两级组成：**第一级边缘感知预模糊**（`void main` + `shader_main_s_pre_enlighten`）+ **第二级双表面模糊**（`shader_main_s_surfaceblur_mix`）。两者都在皮肤掩膜内生效，并显式保护眼睛。

### 1.1 边缘感知预模糊（磨皮主入口）

```glsl
void main() {
  lowp vec4 origin_color = texture2D(tex_origin, st);
  lowp vec4 mask_color   = texture2D(tex_mask, st);
  lowp vec4 ret_color    = origin_color;
  if (mask_color.a > 0.001) {                          // 仅在皮肤区域处理
    lowp vec4 blur_color = texture2D(tex_pre_blur, st); // 预模糊图（低频）
    blur_color.a = origin_color.a;
    // dis = 模糊图与原图的色彩差，乘以 30 作为边缘强度度量
    float dis = distance(vec3(0.0),
                    max(blur_color.rgb - origin_color.rgb, 0.0)) * 30.0;
    float factor = 1.0;
    factor = step(0.5, dis);                            // dis<0.5（平坦皮肤）：不磨
    factor = (1.0 - smoothstep(5.0, 6.0, dis)) * factor; // dis>6（五官强边缘）：不磨
    if (dis > 0.5 && dis < 5.0) {                       // 仅中频区（毛孔/细纹）磨平
      ret_color = shader_main_s_pre_enlighten(
          origin_color, factor * blur_intensity * mask_color.a * 0.25);
    }
  }
  gl_FragColor = ret_color;
}
```

### 1.2 预提亮（被 1.1 调用，细节层混合）

```glsl
lowp vec4 shader_main_s_pre_enlighten(lowp vec4 C, lowp float blend_factor) {
  lowp vec4 textureColor = C;
  float blueColor = textureColor.b * (dim_s_pre_enlighten - 1.0);
  float r_raw = 1.0 / raw_s_pre_enlighten;
  float r_col = 1.0 / col_s_pre_enlighten;
  vec2 quad1;
  quad1.y = floor(floor(blueColor) / raw_s_pre_enlighten);
  quad1.x = floor(blueColor) - (quad1.y * col_s_pre_enlighten);
  vec2 quad2;
  quad2.y = floor(ceil(blueColor) / raw_s_pre_enlighten);
  quad2.x = ceil(blueColor) - (quad2.y * col_s_pre_enlighten);
  vec2 texPos1;
  texPos1.x = (quad1.x * r_col) + 0.5/(col_s_pre_enlighten * dim_s_pre_enlighten)
            + ((r_col - 1.0/(col_s_pre_enlighten * dim_s_pre_enlighten)) * textureColor.r);
  texPos1.y = (quad1.y * r_raw) + 0.5/(raw_s_pre_enlighten * dim_s_pre_enlighten)
            + ((r_raw - 1.0/(raw_s_pre_enlighten * dim_s_pre_enlighten)) * textureColor.g);
  vec2 texPos2;
  texPos2.x = (quad2.x * r_col) + 0.5/(col_s_pre_enlighten * dim_s_pre_enlighten)
            + ((r_col - 1.0/(col_s_pre_enlighten * dim_s_pre_enlighten)) * textureColor.r);
  texPos2.y = (quad2.y * r_raw) + 0.5/(raw_s_pre_enlighten * dim_s_pre_enlighten)
            + ((r_raw - 1.0/(raw_s_pre_enlighten * dim_s_pre_enlighten)) * textureColor.g);
  lowp vec4 newColor1 = texture2D(tex_enlighten, texPos1);
  lowp vec4 newColor2 = texture2D(tex_enlighten, texPos2);
  lowp vec4 newColor = mix(newColor1, newColor2, fract(blueColor));
  return newColor = vec4(
             mix(textureColor, vec4(newColor.rgb, textureColor.w), blend_factor).rgb,
             C.a);
}
```

### 1.3 双表面模糊（磨皮主体，Photoshop 式表面模糊 + 可选锐化）

```glsl
vec4 shader_main_s_surfaceblur_mix(vec2 st, vec4 C) {
  if (blur_amount_s_clear_blur_mix < 0.001) {
    return C;                                            // 强度≈0 直接返回原图
  } else {
    lowp vec3 blur1 = texture2D(tex_surfaceblur1, st).rgb; // 表面模糊层1（低频）
    lowp vec3 blur2 = texture2D(tex_surfaceblur2, st).rgb; // 表面模糊层2（低频）
    lowp vec4 mask  = texture2D(tex_mask, st);
    lowp float eye_mask = 0.0;
    if (mask.g > 0.0 && mask.r <= 0.1 && mask.b <= 0.1) { // 绿色通道=眼睛/五官
      eye_mask = mask.g;                                   // 保护眼睛
    }
    lowp float skin_mask = mask.a;                         // alpha=皮肤区域

    lowp float intensity = blur_amount_s_clear_blur_mix;

#ifdef USE_SKIN_DETECT                                   // 可选：肤色检测
    if (skin_detect_s_clear_blur_mix > 0.5) {
      lowp float r = C.r, g = C.g, b = C.b;
      if (r > 0.371 && g > 0.156 && b > 0.078 && r > b && r > g &&
          abs(r - g) > 0.059 &&
          (max(max(r,g),b) - min(min(r,g),b) > 0.059)) {
        // 判定为皮肤：保持强度
      } else {
        intensity = nonskin_blur_scale_s_clear_blur_mix * intensity; // 非皮肤：衰减
      }
    }
#endif

    intensity = mix(intensity * 1.4286, 1.0, step(0.7, intensity));
    lowp float evenfactor = mix(0.3, intensity - 0.3, step(0.6, intensity));
    lowp vec4 result_color = C;
    // 高频（细节）层：原图与模糊1之差，映射到 [0,1]
    lowp vec3 diff = (C.rgb - blur1) * 0.5 + 0.5;
    // 细节保持合成：低频(blur2) + 高频(diff) 重新叠加
    lowp vec3 even = clamp(2.0 * diff + blur2 - 1.0, vec3(0.0), vec3(1.0));
    even = mix(C.rgb, even, skin_mask);                   // 仅在皮肤内混合
    even = mix(even, blur2, skin_mask * evenfactor);
    lowp vec3 res = mix(C.rgb, even, intensity);
    result_color = vec4(mix(C.rgb, res, (1.0 - eye_mask)), C.a); // 眼睛完全不模糊

#ifdef USE_SHARPEN                                        // 可选：高通锐化补偿
    vec4 st_offset1 =
        vec4(widthOffset_s_clear_blur_mix, heightOffset_s_clear_blur_mix,
             -widthOffset_s_clear_blur_mix, -heightOffset_s_clear_blur_mix) * 0.5
        + vec4(st, st);
    vec4 st_offset2 =
        vec4(-widthOffset_s_clear_blur_mix, heightOffset_s_clear_blur_mix,
             widthOffset_s_clear_blur_mix, -heightOffset_s_clear_blur_mix) * 0.5
        + vec4(st, st);
    lowp float sum = texture2D(tex, st_offset1.xy).g;
    sum += texture2D(tex, st_offset1.zw).g;
    sum += texture2D(tex, st_offset2.xy).g;
    sum += texture2D(tex, st_offset2.zw).g;
    sum = 0.25 * sum;
    lowp float highPass = C.g - sum + 0.5;
    lowp float flag = step(0.5, highPass);
    lowp vec3 hv = (2.0 * highPass + result_color.rgb - 1.0);
    lowp vec3 color = mix(max(vec3(0.0), hv), min(vec3(1.0), hv), flag);
    result_color.rgb = mix(result_color.rgb, color.rgb, sharpen_s_clear_blur_mix);
#endif
    result_color.a = C.a;
    return result_color;
  }
}
```

### 1.4 美白（3D-LUT 索引，被皮肤掩膜限定）

```glsl
vec4 shader_main_s_color_custom_shader_whitten(vec2 st_src, vec4 C) {
  if (color_level_s_color_custom_shader_whitten < 0.001) {
    return C;
  } else {
    vec4 textureColor = C;
    textureColor *= color_scale_s_color_custom_shader_whitten;   // 提亮缩放
    // 以蓝色通道为索引，在 dim×raw×col 的 3D-LUT 网格中定位
    float blueColor = textureColor.b * (dim_s_color_custom_shader_whitten - 1.0);
    float r_raw = 1.0 / raw_s_color_custom_shader_whitten;
    float r_col = 1.0 / col_s_color_custom_shader_whitten;
    vec2 quad1;
    quad1.y = floor(floor(blueColor) / raw_s_color_custom_shader_whitten);
    quad1.x = floor(blueColor) - (quad1.y * col_s_color_custom_shader_whitten);
    vec2 quad2;
    quad2.y = floor(ceil(blueColor) / raw_s_color_custom_shader_whitten);
    quad2.x = ceil(blueColor) - (quad2.y * col_s_color_custom_shader_whitten);
    vec2 texPos1;
    texPos1.x = (quad1.x * r_col) + 0.5/(col_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)
              + ((r_col - 1.0/(col_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)) * textureColor.r);
    texPos1.y = (quad1.y * r_raw) + 0.5/(raw_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)
              + ((r_raw - 1.0/(raw_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)) * textureColor.g);
    vec2 texPos2;
    texPos2.x = (quad2.x * r_col) + 0.5/(col_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)
              + ((r_col - 1.0/(col_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)) * textureColor.r);
    texPos2.y = (quad2.y * r_raw) + 0.5/(raw_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)
              + ((r_raw - 1.0/(raw_s_color_custom_shader_whitten * dim_s_color_custom_shader_whitten)) * textureColor.g);
    // 采样 LUT（tex_filter_s_color_custom_shader_whitten），按 color_level*skin_mask 混合
    // 返回：mix(原色, LUT色, color_level_s_color_custom_shader_whitten * skin_mask)
  }
}
```

### 1.5 脸型重塑（faceStretch 坐标形变，**独立于磨皮**）

脸型（瘦脸/窄脸）通过把纹理坐标朝关键点目标点推移实现，核心调用如下（关键点为 AI 人脸追踪输出）：

```glsl
// 在坐标形变 main 中（节选）：
float radius = face_width * 1.5;
vec2 targetchin = p_nose + (p_chin - p_nose) * 0.87;            // 下巴目标点
vec2 chinplus   = faceStretch(newCoord, p_chin, targetchin, radius);
newCoord = newCoord - chinplus * myparameter2;

vec2 chinCenter = p_nose;
radius = face_width * 1.2;
vec2 targetleftC  = chinCenter + (p_chinleft  - chinCenter) * 0.94;
vec2 targetrightC = chinCenter + (p_chinright - chinCenter) * 0.94;
vec2 leftCplus  = faceStretch(newCoord, p_chinleft,  targetleftC,  radius);
vec2 rightCplus = faceStretch(newCoord, p_chinright, targetrightC, radius);
newCoord = newCoord - leftCplus  * myparameter2;
newCoord = newCoord - rightCplus * myparameter2;
// 还有 p_chinleft_u / p_chinright_u（下颌上点）的同构处理
// 最终：return textureCoordinate + (newCoord - textureCoordinate) * myparameter;
```

关键点集合（`p_` 前缀，来自人脸追踪）：`p_nose`、`p_chin`、`p_chinleft`、`p_chinright`、`p_chinleft_u`、`p_chinright_u`。

---

## 二、磨皮关键参数表（引擎着色器 uniform）

| 参数名 | 含义 | 控制阶段 | 备注 |
|---|---|---|---|
| `blur_intensity` | 磨皮强度 | 第一级边缘感知模糊 | 与 `mask.a`、`0.25` 系数共同决定混合量 |
| `blur_amount_s_clear_blur_mix` | 表面模糊混合量 | 第二级双表面模糊（主驱动） | `<0.001` 时直接返回原图 |
| `blur_fs` / `blur_h_fs` / `blur_v_fs` | 模糊滤波器尺寸（含横/纵向） | 模糊核生成 | 控制模糊半径 |
| `blur_size` / `blur_times` | 模糊核大小 / 迭代次数 | 模糊核生成 | 控制模糊程度 |
| `skin_detect_s_clear_blur_mix` | 肤色检测开关（>0.5 启用） | 保护 | 配合 `USE_SKIN_DETECT` |
| `nonskin_blur_scale_s_clear_blur_mix` | 非皮肤区域模糊衰减系数 | 保护 | 非肤像素模糊强度乘此值 |
| `sharpen_s_clear_blur_mix` | 锐化（清晰）强度 | 补偿 | 配合 `USE_SHARPEN` 高通锐化 |
| `widthOffset_s_clear_blur_mix` / `heightOffset_s_clear_blur_mix` | 锐化采样偏移 | 补偿 | 高通核的邻域偏移 |
| `color_level_s_color_custom_shader_whitten` | 美白强度 | 美白 | 按 `skin_mask` 混合 |
| `color_scale_s_color_custom_shader_whitten` | 美白提亮缩放 | 美白 | 预乘提亮 |
| `dim_s_*` / `raw_s_*` / `col_s_*` | 美白/提亮 3D-LUT 网格维度 | 美白/提亮 LUT | 定位 LUT 采样格 |

---

## 三、管线中间产物（掩码 → 关键点 → 保护掩码 → 高低频层）

**① 掩码（Mask）**
- 主掩码 `tex_mask`（多通道）：`.a`=皮肤、`.g`=眼睛/五官、`.r`=非肤检测、`.b`=皮肤(美白用)
- 独立皮肤掩码 `tex_skin`；眼睛掩码 `tex_eye_mask`
- 嘴/脸遮挡 `tex_mouthoccu` / `tex_face_occu_blur`
- 分割掩码 `tex_segmentation` / `tex_bg` / `tex_background` / `tex_back_blur`（背景虚化）

**② 关键点（Key points）** —— 由人脸 AI 追踪输出，传入形变着色器
- 轮廓：`p_nose`、`p_chin`、`p_chinleft`、`p_chinright`、`p_chinleft_u`、`p_chinright_u`
- 变换/索引：`p_origin`、`p_rot`、`p_flip`、`p_inv`、`p_faceright`、`p_5`、`p_6`、`p_8`、`p_C`、`p_T`、`p_f`、`p_type`

**③ 保护掩码（Protection mask）** —— 从掩码派生，决定"哪里不磨"
- `eye_mask`（由 `mask.g`）：眼睛/五官完全不参与模糊（`mix(C,res,1.0-eye_mask)`）
- `skin_mask`（由 `mask.a`）：模糊只在皮肤区域内生效
- 非皮肤衰减：开 `USE_SKIN_DETECT` 时，非肤像素强度 ×`nonskin_blur_scale` 衰减

**④ 高低频层（High / Low frequency layers）** —— 磨皮的核心分解
- 低频（拿去磨平）：`tex_surfaceblur1`/`blur1`、`tex_surfaceblur2`/`blur2`、`tex_pre_blur`
- 高频（细节/毛孔，要保留）：`diff = (C.rgb - blur1) * 0.5 + 0.5`
- 合成：`even = clamp(2.0 * diff + blur2 - 1.0, 0,1)` —— 低频 + 高频重新叠回 → **磨皮但保质感**
- 基准：`tex_origin`（全频原图）

---

## 四、核心思路（一句话）

把图像拆成**低频（模糊层，磨平）+ 高频（毛孔细节，保留）**，在**皮肤掩膜**内用表面模糊合成，并用**眼睛保护掩码**排除五官；边缘感知预模糊只磨中频区（`dis∈(0.5,6.0)`）以保边——这就是"磨皮不糊五官、磨平不丢质感"的实现原理。
