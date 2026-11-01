# BeautyCore — 独立美颜模块（从 obs-cam-beauty 插件提取）

本目录是把 **OBS 美颜相机插件（obs-cam-beauty / 相芯 FaceUnity NamaSDK 8.10）** 的美颜核心
从 OBS 插件体系中独立出来后的可运行版本。无需安装 OBS、无需插件宿主进程，
直接对图片做人脸美颜处理。

---

## 1. 目录结构

```
package/
├── beauty.bat              启动脚本
├── BeautyCore.cs           宿主程序源码（C# P/Invoke，可用 csc 重新编译）
├── bin/
│   ├── BeautyCore.exe      独立美颜宿主（.NET Framework 4.x，AnyCPU/x64）
│   ├── CNamaSDK.dll        相芯 NamaSDK 8.10.0（美颜渲染引擎，从插件提取）
│   ├── fuai.dll            相芯 FUAI 人脸/人体 AI 推理库（从插件提取）
│   ├── w32-pthreads.dll    CNamaSDK 依赖（取自 obs-studio 运行库）
│   ├── api-ms-win-downlevel-shlwapi-l1-1-0.dll（兼容 shim）
│   └── auth_package.bin    FaceUnity 授权包（1260 字节，见 §5）
├── assets/
│   ├── graphics/
│   │   ├── face_beautification.bundle   美颜道具（磨皮/美白/美型/滤镜/亮眼/美牙…）
│   │   ├── face_makeup.bundle           美妆道具（未在默认流程加载）
│   │   ├── body_slim.bundle             美体道具（未在默认流程加载）
│   │   └── background_blur.bundle       背景虚化道具（未在默认流程加载）
│   └── model/
│       ├── ai_face_processor_pc.bundle  人脸关键点/检测模型（必须）
│       └── ai_human_processor_pc.bundle 人体模型（美体/背景虚化需要，当前未加载）
└── face_in.png             测试输入图（可删除）
```

## 2. 用法

```bat
cd package
beauty.bat process 输入.jpg 输出.png
```

可选参数：

```
beauty.bat process <input> <output> [inFmt] [outFmt] [assetDir]
beauty.bat info                       只初始化并打印 SDK 状态
beauty.bat probe <inFmt> <outFmt> <in> <out>   单次渲染探测
beauty.bat scan <input> <assetDir>    格式/参数扫描（调试用）
```

- `inFmt`/`outFmt`：像素格式枚举，**0 = RGBA 缓冲**（已实测验证；2 为某种 YUV 通道序）。
- 输入输出均为 RGBA8888 位图（PNG/JPG/BMP…任意 .NET GDI+ 可读格式）。
- 渲染管线内部为 GPU(OpenGL) 缓冲模式，输出**原地写回** `out_ptr`。
- 相对路径以**调用 beauty.bat 时所在目录**为准（脚本内部会先转换为绝对路径再切换到 bin\）。

### 参数覆盖（环境变量）

```bat
set BEAUTY_PARAMS=blur_level:6;color_level:0.7;eye_enlarging:0.6;cheek_thinning:0.8;filter_name:bailiang1;filter_level:1.0
beauty.bat process in.png out.png
```

默认参数（逆自插件面板默认值 + 官方美颜文档）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| is_beauty_on | 1 | 总开关 |
| use_landmark | 1 | 关键点驱动（0=全图处理） |
| filter_name | ziran2 | 滤镜名（bailiang1/fennen1/xiaoqingxin1/lengsediao1/nuansediao1/origin…） |
| filter_level | 0.4 | 滤镜强度 |
| blur_level | 4.2 | 磨皮强度（0~6） |
| blur_type | 2 | 磨皮类型（2=精细磨皮） |
| color_level | 0.3 | 美白 |
| red_level | 0.3 | 红润 |
| sharpen | 0.2 | 锐化 |
| face_shape | 4 | 美型档位（4=精细） |
| face_shape_level | 1.0 | 美型强度 |
| eye_enlarging | 0.4 | 大眼 |
| cheek_thinning | 0.5 | 瘦脸 |
| heavy_blur | 0 | 朦胧磨皮（高级授权项） |
| skin_detect | 1 | 肤色检测 |

完整参数列表见逆向得到的插件通信字段
（`cheek_v/cheek_narrow/cheek_small/intensity_nose/intensity_forehead/intensity_mouth/intensity_chin/
eye_bright/tooth_whiten/remove_pouch_strength/remove_nasolabial_folds_strength/background_blur/...`），
均可用 `BEAUTY_PARAMS` 直接设置。

## 3. C API 调用序列（BeautyCore.Setup/渲染循环）

```csharp
// 1. 建 GL 上下文（隐藏窗口 + wglCreateContext，与官方 Demo 相同）
// 2. fuSetup(NULL,0,NULL, auth_package, 1260)   <- 必须带授权包，见 §5
// 3. fuLoadAIModelFromPackage(ai_face_processor_pc.bundle, size, 0x100)   <- 0x100=FUAITYPE_FACEPROCESSOR(实测)
//    fuLoadAIModelFromPackage(ai_human_processor_pc.bundle, size, 0x200)  <- 0x200=人体（可选）
// 4. fuSetFaceProcessorDetectMode(0)      // 0=图片模式 1=视频模式
//    fuFaceProcessorSetFaceLandmarkQuality(1)
//    fuSetMaxFaces(4)
//    fuSetDefaultRotationMode(0)
// 5. hBeauty = fuCreateItemFromPackage(face_beautification.bundle, size)
//    fuItemSetParamd(hBeauty,"blur_level",4.2) ... （见参数表）
// 6. 每帧: fuRenderItemsEx(0 /*RGBA*/, outBuf, 0 /*RGBA*/, inBuf, w, h, frameId++, {hBeauty}, 1)
//    返回值>0 表示成功（内部纹理 id）；fuFaceProcessorGetNumResults() 得到人脸数
// 7. 收尾: fuDestroyAllItems(); fuOnDeviceLost(); fuDestroyLibData();
```

关键实测结论（踩坑记录）：

1. **FUAITYPE 数值不是公开文档的 `1<<10`**。通过对 beauty.exe 的 API 调用日志代理抓取
   （见 `gen_proxy.py` + `proxy_gen.*`），真实调用为 `0x100`（人脸）和 `0x200`（人体）。
   传错会导致 `face recognizer bundle is corrupted` + AI 模型加载失败。
2. **授权包必须传给 fuSetup**，否则 `fuSetup ret=0`（g_nama_inited:0 / fuSetup_Impl exception）。
3. **像素格式 0 = RGBA**，输入输出通道序一致；`fuRenderItemsEx` 结果原地写回 out 缓冲。
4. GL 上下文必须由宿主创建并保持 current（官方 demo 用 EDIT 控件 + wglCreateContext 即可）。
5. `fuSetFaceModelConfig/fuSetFaceAlgorithmConfig` 在 beauty.exe 中**从未被调用**，无需调用。

## 4. 与原插件的关系（逆向摘要）

原插件架构：

```
obs64.exe
 └─ obs-cam-beauty.dll / obs-cam-beauty_qt6.dll   (OBS 源插件: UI/管道/取流)
     └─ beauty.exe  --parent-pid --controller-id --input-queue-id --output-queue-id
                    --beauty-setting-id --data-pipe-setting-id --resource-dir --loger-dir
                    --debug --force-use-cpu --disable-beauty
         └─ CNamaSDK.dll + fuai.dll  (真正的美颜引擎)
```

- 进程间通信：`\\.\pipe\BEAUTY_BRIDGE_PIPE<pid>`（管道，1024 字节定长帧，握手
  `module version=1.6.1.0` / `Init Result = Success`）+ 共享内存队列
  （`<guid>__DATA_READ_SEMAPHORE____BEAUTY__` 等 6 类内核对象）。
- beauty.exe 1.6.1；NamaSDK 8.10.0_ALL_74382e4；授权证书 `njss0908_MOD1638767-32`（南京双石信息）。
- 本模块**跳过整套 IPC**，直接在同一进程内调用 SDK，因此可独立运行。

## 5. 授权包说明（auth_package.bin）

`fuSetup` 必须传入 FaceUnity 授权数据。本包中的 `auth_package.bin`（1260 字节）
是通过一个导出转发代理 DLL（`proxy_gen.cpp`，582 个导出全部转发到 `CNamaSDK_real.dll`，
仅拦截 `fuSetup` 记录 `authdata/sz`）从原版 beauty.exe 运行时捕获得到，
授权主体为插件厂商的证书（`cert_name:njss0908_MOD1638767-32`，
模块码 `module[0]=1638767 / module[1]=32`）。

验证结果：

```
[fuSetup] ret=1 err=0 (ok)     fuIsLibraryInit=1
module beautification access code: 0-00000000000000000000000000000000
```

> ⚠️ 该授权与插件厂商（南京双石/OBSWorks）的商业授权绑定，
> 仅用于本机逆向学习验证。商用需要自行向 FaceUnity（相芯科技）申请授权。

## 6. 重新编译

```bat
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /r:System.Drawing.dll ^
   /out:bin\BeautyCore.exe BeautyCore.cs
```

## 7. 已验证效果

- 真人照片 640x394：人脸检测 `faces=2`，磨皮/美白/滤镜生效，
  与输入的平均像素差 ≈38/255，肉眼可见（见 `../compare_left.png`）。
- 管线支持连续多帧（frame_id 递增），可直接改造成视频流/摄像头实时处理：
  只需把输入源换成相机帧缓冲循环调用 `fuRenderItemsEx` 即可。
