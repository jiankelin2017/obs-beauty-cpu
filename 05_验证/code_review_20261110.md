# 代码变更静态审查报告 · 2026-11-10

| 字段 | 值 |
|---|---|
| 文档版本 | `1.0.0.0` |
| 审查日期 | 2026-11-10 07:33–07:57（GMT+8） |
| 适用代码版本 | CPU 线 `1.0.13.12`（`BEAUTY_BUILD_STR`，`01_源码/beauty_params.h:888`） |
| 基线提交 | `b92d0424428430f740f6bcb73994ef0dfc05f3f9`（`main`，2026-11-08 01:21） |
| 审查对象 | 工作区未提交变更：staged 15 个源码文件、unstaged 3 个源码文件，去重后共 **16 个** |
| 审查方法 | 四组并行静态审读 + 逐条回读工作区源码复核；**只读，无编译、无运行、无动态测试** |
| 状态 | `Active`（**审查基线已变更**：2026-11-10 08:39 源码已按本文 §9 修改，第 2 节行号与代码原文为改前快照） |
| 维护人 | 待人工确认 |
| 替代文档 | 无（新建） |
| 失效说明 | 一旦这批变更被提交、回滚或继续修改，本文的「当前结论」即失效；**该条件已于 2026-11-10 08:39 触发**（§9 补丁落地）。引用者须以 §9 的改后定位与备份 `D://插件//_整理_20261110//before_patch_20261110//` 为准 |

> 本文属 `05_验证/` 取证与记录类文件。按 `05_验证/INDEX.md` 的裁定，该目录不纳入 `docs/` 文档体系，不登记 `docs/INDEX.md`，也不强制六字段 Active 头表。本文保留元信息表，目的是让审查基线可复核。

---

## 0. 结论先行

**本轮在 16 个变更源码文件里确认 1 条高危、3 条中危、7 条低危问题。用户关注的三类风险（空指针、资源未释放、安全漏洞）均有命中。所有后果判断都是基于代码结构的静态推断，本文没有复现任何一次故障，也没有编译或运行插件。**

| 类别 | 命中条数 | 最高严重度 | 代表条目 |
|---|---|---|---|
| A 空指针 / 未初始化解引用 | 3 | 中 | `obs-beauty.cpp:316-317` 的 `bzalloc` 未判空 |
| B 资源未释放 | 2 | 低 | `beauty_onnx.cpp:198` 失败 status 未 `ReleaseStatus` |
| C 安全漏洞 / 竞态 / UB | 6 | **高** | `beauty_core.cpp:2162-2166` 的 `releaseSlot` 与异步 worker 数据竞争 |

---

## 1. 审查口径（可复核事实）

| 项目 | 实测值 | 取得方式 |
|---|---|---|
| 仓库 | `D:/插件/OBS美颜源码`，`main` 分支 | `git rev-parse` / `git branch` |
| git 工作区 | 236 条未提交变更 | `git status --short \| wc -l` |
| staged 源码 diff 原始行数 | 11030 行 | `git diff --cached -- 01_源码 \| wc -l` |
| staged 源码语义变更 | **+3718 / −490**（14 个文件） | `git diff --cached -w --stat` |
| unstaged 源码 diff | 234 行（+101 / −20，3 个文件） | `git diff -- 01_源码` |
| 直接 `getenv` 调用 | 0 处（仅剩 2 处注释文字） | `grep -rn getenv 01_源码` |

**重要口径说明**：原始 staged diff 呈「整文件全删全加」的观感，其中大部分是行尾与缩进变化，不能按 11030 行理解语义改动量。`beauty_params.h` 的 591 行变更几乎全部是版本历史注释与一行 `BEAUTY_BUILD_STR` 宏，不产生可执行逻辑差异。本文只审查真实语义变更。

---

## 2. 确认成立的问题清单

### 2.1 高危

#### #1 `beauty_core.cpp:2162-2166` ↔ `:3963` — 数据竞争（C，本轮引入）

```cpp
2162  void releaseSlot(int slot) override {
2163      if (slot < 0 || slot >= kMaxSlots) return;
2164      std::lock_guard<std::mutex> lk(slotsMtx_);
2165      slotUsed_[slot] = false;
2166      slots_[slot] = DetState();
...
3963  const bool ok = buildMaskInto(slots_[slot], &async_.frame[0], w, h,
3964                               mask, protect, b, fbox, px, faces, msg);
```

- **事实**：`releaseSlot()` 只持 `slotsMtx_` 就对 `slots_[slot]` 整体赋值。`asyncWorker()` 在 `async_.m` 临界区之外（第 3954 行已解锁）把同一 `slots_[slot]` 引用传入 `buildMaskInto()`。`BEAUTY_BIND_DET_ALL` 把 `mask_` / `protect_` / `faces_` 等 `std::vector` 成员绑成局部引用 (Jian, `01_源码/beauty_core.cpp`, ll. 1715–1740)。两个线程对同一对象没有共同锁。
- **触发条件**：滤镜销毁调用 `releaseSlot()` 时，该 slot 恰好还有未排空的异步检测任务。`beauty_filter_destroy()` 在 `01_源码/obs-beauty.cpp:353-355` 调用它，而 worker 是进程级单例线程，不随单个滤镜销毁停止。
- **推断后果（非已证实）**：并发析构与读写 `std::vector` 内部指针可能造成堆损坏或崩溃。本文没有实测复现。
- **待人工确认**：OBS 是否保证 `beauty_filter_destroy` 与 `video_render` / 异步 worker 串行；`buildMaskInto` 是否在内部另持其他锁。
- **修复建议**：`releaseSlot()` 在重置前排空该 slot 的 pending 任务——等待 `async_.working == false`、丢弃 `async_.ready && async_.slot == slot` 的结果并把 `async_.slot` 置为无效值；或给每个 `DetState` 配独立 mutex，并在 `process` / `collectAsync` / `asyncWorker` 的全部访问点统一持有。

### 2.2 中危

#### #2 `obs-beauty.cpp:316-317` — 空指针解引用（A，本轮引入）

```cpp
316  struct beauty_filter *f = (struct beauty_filter *)bzalloc(sizeof(struct beauty_filter));
317  InitializeSRWLock(&f->param_lock);
318  f->context = source;
```

- **事实**：`bzalloc()` 返回值未判空，第 317 行立即对 `&f->param_lock` 求成员地址并写入。第 317 行由本轮 `1.0.13.12` D1 线程安全改动新增，把首个解引用点从旧代码的第 318 行提前。
- **触发条件**：分配失败返回 `NULL`。
- **待人工确认**：本机 libobs 的 `bzalloc` 在 OOM 时返回 `NULL` 还是直接 `abort`。若属后者，本条不成立。
- **修复建议**：`bzalloc` 之后立即加 `if (!f) return NULL;`，再执行 `InitializeSRWLock` 与后续字段赋值。

#### #3 `beauty_onnx.cpp:198-201` — 失败 status 泄漏 + 失败分支释放无效指针（A + B，本轮引入）

```cpp
197  char* inName = nullptr;
198  if (A->SessionGetInputName(sess, 0, alloc, &inName) != nullptr || !inName) {
199      err = "读取输入名失败或返回空名称";
200      if (inName) alloc->Free(alloc, inName);
201      return false;
202  }
203  inName_ = inName;
204  alloc->Free(alloc, inName);
```

- **事实**：本轮把条件从 `!= nullptr` 改为 `!= nullptr || !inName`，并新增第 200 行的 `Free`。返回的 `OrtStatus*` 仍未被接住，因此没有 `ReleaseStatus`；对比同文件第 132–138 行与第 184–190 行，两处本轮新增的失败分支都释放了 status。`inName_` 声明为 `std::string` (Jian, `01_源码/beauty_onnx.h`, l. 65)，所以第 203–204 行的「先复制后释放」是安全的，本条不涉及悬空指针。
- **推断后果（非已证实）**：失败路径泄漏一个 `OrtStatus`；若 ORT 在失败时把 `*inName` 写成非 nullptr 但非本 allocator 分配的值，第 200 行 `Free` 可能破坏堆。
- **待人工确认**：ORT C API `SessionGetInputName` 返回错误 `OrtStatus*` 时对 `*name` 的写入语义，是否保证保持调用方传入的 `nullptr`。
- **修复建议**：接住 status 并 `ReleaseStatus`，把「调用失败」与「成功但空名」拆成两个分支；失败分支不要 `Free(inName)`，成功路径沿用第 204 行已有的释放。

#### #4 `beauty_core.cpp:3855, 3864` — 输出槽覆盖与锁外共享缓冲写（C，本轮引入）

```cpp
3855  if (async_.hasJob || async_.working) return;
3860  async_.slot = slot;
3864  memcpy(&async_.frame[0], src, (size_t)w * h * 4);
3906  heldFrame_.swap(async_.frame);
```

- **事实**：`submitAsync()` 的互斥条件只判 `hasJob` / `working`，不判 `ready`。`collectAsync()` 用 `async_.ready && async_.slot == slot` 认领结果 (Jian, `01_源码/beauty_core.cpp`, l. 3890)。第 3864 行的 `memcpy` 在 `async_.m` 锁外执行，与第 3906 行的 `swap` 无共同互斥。
- **推断后果（非已证实）**：多实例下，slot A 的结果尚未被取走时 slot B 提交任务，会覆盖 `async_.slot` 与帧缓冲，使 A 永久取不到结果、掩码静默不更新；若两个滤镜实例的 `process` 跨线程并发，帧缓冲本身构成真实数据竞争。
- **待人工确认**：OBS 多个滤镜实例的 `process` 是否可能跨线程并发。
- **修复建议**：`submitAsync` 增加 `if (async_.ready) return;`；让 `async_.frame` 的整段写入与 `collectAsync` 的 `swap` 同在 `async_.m` 之下，或改双缓冲。

### 2.3 低危

| # | 位置 | 类别 | 本轮引入 | 事实陈述 | 建议动作 |
|---|---|---|---|---|---|
| 5 | `beauty_onnx.cpp:222-224` | A | 否 | `SessionGetOutputName` 成功但 `*on` 为空时，`outNames_.push_back(on)` 会以 `nullptr` 构造 `std::string`。本轮「ORT 判空」只改了输入名，对称的输出名未改 | 补 `&& on` 判空，并补失败 status 的 `ReleaseStatus` |
| 6 | `core_probe.cpp:153-169` | B | 是 | 全文只有 `BeautyCoreAcquireSlot` 导出，没有对应的 `ReleaseSlot`；`kMaxSlots = 8`，离线台架反复领取后 `acquireSlot` 返回 −1。该导出仅存在于验证 DLL | 增加 `BeautyCoreReleaseSlot` 导出，或让台架复用固定槽位 |
| 7 | `obs-beauty.cpp:625` | C | 是 | `bytes = (size_t)cx * (size_t)cy * 4` 无溢出检查。该函数在第 648 行有 `gs_*` 创建失败的整体兜底，本文未证实越界写可达 | 乘法前加溢出检查，或按 D3D11 上限钳制 `cx/cy` |
| 8 | `beauty_freq.cpp:727` | C | 是 | `*(uint32_t*)(void*)p = v` 把 `unsigned char*` 强转 32 位写；入口第 628 行只判空，未校验对齐。x86 上通常可工作 | 改用 `memcpy(p, &v, 4)` 或逐字节写；至少加对齐断言与 `w/h` 正数校验 |
| 9 | `beauty_face.cpp:367-369` | C | 待确认 | 循环只校验 `f.kps[p*2+0]`（x 分量），`f.kps[p*2+1]`（y 分量）与 bbox 的 `bx/by/bw/bh` 均无数/有限性校验 | 逐分量加 `std::isfinite`，bbox 同理 |
| 10 | `beauty_face.h:112,117` | C | 是 | `lastMs()` / `lastBestScore()` 无锁读普通 `float` / `double`，`detect()` 在 `mtx_` 内写这两个成员 | getter 加锁，或改 `std::atomic`，或删除 getter 只保留 `DetMeta out` |
| 11 | `02_构建/build_*.bat` | C | 部分 | 25 个 `build_*.bat` 中仅 4 个提及 `BEAUTY_ENV_LOCK`；当前 `build_1.0.13.12.bat:73` 已定义 `/DBEAUTY_ENV_LOCK=1`，全库直接 `getenv` 调用为 0 | 给旧脚本补锁宏，或在脚本里显式声明「该产物不可发布」 |

---

## 3. 复核后被推翻或降级的推断

本节记录初筛结论与最终结论的差异，避免把推断沉淀成事实。

| 初筛结论 | 复核结果 | 依据 |
|---|---|---|
| `beauty_warp.cpp:86` 的 NaN 经 `atan2f` 进入采样索引，高危 | **不成立** | 该文件第 85 行 `if (fabsf(dxe) + fabsf(dye) > 4.0f)` 在 `dye` 为 NaN 时比较结果为 false，`phi` 保持 0；第 98 行死区再清零。初筛漏掉了这道前置门。真实缺口收窄为第 9 条的输入校验不完整，级别降为低 |
| `obs-beauty.cpp:939-946` 分段日志的 `%d` 与变参类型可能不匹配 | **不成立** | `boxBlockWidth()` / `boxMinPixels()` / `parCopyOn()` / `boxFuseOn()` 均声明为 `int` (Jian, `01_源码/beauty_smooth.h`, ll. 363–369)；该行 13 个占位符与实参类型一致 |
| `beauty_env.h` 使发布版存在环境变量注入面，中危 | **当前版不成立，降为低** | 最新发布脚本已定义锁宏，全库直接 `getenv` 调用归零。风险只存在于用旧脚本构建的场合 |

---

## 4. 未发现问题的范围

| 类别 | 明确未发现的文件 |
|---|---|
| B 资源未释放 | `obs-beauty.cpp`（`beauty_filter_alloc` 的失败/成功路径成对释放；SRWLOCK 在 update / snapshot 内无提前 return）、`beauty_smooth.cpp`、`beauty_freq.cpp`、`beauty_warp.cpp`、`beauty_region.cpp` |
| A 空指针 | `beauty_core.cpp`、`beauty_face.cpp`、`beauty_smooth.cpp`、`beauty_freq.cpp`、`beauty_warp.cpp`（`FaceBox` / `RoiRect` 有类内默认初始化，slot 越界有兜底） |
| C 安全漏洞 | `beauty_smooth.cpp` / `.h`（新增 SSE 路径与 ROI 裁剪已逐项核对边界） |

---

## 5. 待人工确认清单（我不知道，不臆断）

1. 本机 libobs 的 `bzalloc` / `bmalloc` 在 OOM 时返回 `NULL` 还是直接 `abort`。
2. ORT C API `SessionGetInputName` / `SessionGetOutputName` 在返回错误 `OrtStatus*` 时对 `*name` 的写入语义。
3. OBS 是否保证 `beauty_filter_destroy` 与异步 worker 串行。
4. OBS 多个滤镜实例的 `process` 是否可能跨线程并发。
5. 上游 ONNX 输出（bbox 与关键点）是否可能包含 NaN / Inf。
6. `gs_stagesurface_map` 返回 true 时是否保证 `*ptr` 非空；`gs_*_create` 对超大 `cx/cy` 是否必然失败。
7. 本文所有「触发即崩溃 / 堆损坏 / 结果永久不更新」的后果判断，均需运行时证据才能升级为已证实结论。

---

## 6. 修复顺序建议（本文未修改任何代码）

1. 先修 #1：`releaseSlot()` 排空 pending 异步任务或给 `DetState` 配独立锁。
2. 再修 #2：`bzalloc` 后加一行判空。
3. 再修 #3 与 #5：接住并释放 ORT status，失败分支不 `Free(inName)`，输出名补判空。
4. #4 与 #6–#11 属加固项，建议合并进下一个修订位版本。

按项目四段式版本号规则：#1–#3 属修 bug，建议修订位 +1；#6 若新增导出函数则属用户可见的新功能，建议功能位 +1。具体版本号由维护人裁定。

---

## 7. 可验证事实与个人推测的分界

- **可验证事实**：本文所有行号、代码原文、函数签名、构建脚本宏、git 变更规模、MD5 与文件计数，均来自本轮命令输出与文件原文，读者可按标注复核。
- **个人推测（显式标记）**：第 2 节中「触发条件」「推断后果」两段，以及第 6 节的优先级排序，都是基于静态代码结构的推断。本文没有编译、没有运行、没有复现任何故障。第 5 节列出的 7 项在确认前不得当作结论引用。
- **未采信内容**：第 3 节列出的 3 条初筛结论已被推翻或降级，不得继续引用。

---

## 8. 引用来源（MLA 格式）

Jian. *01_源码/beauty_core.cpp*, ll. 1715–1740, 2152–2182, 3852–3871, 3940–3985, 2026-11-09. ———. *01_源码/obs-beauty.cpp*, ll. 305–366, 605–675, 935–955. ———. *01_源码/beauty_onnx.cpp*, ll. 125–235. ———. *01_源码/beauty_onnx.h*, l. 65. ———. *01_源码/beauty_face.cpp*, ll. 320–395. ———. *01_源码/beauty_face.h*, ll. 30–72, 112–117. ———. *01_源码/beauty_warp.cpp*, ll. 42–101, 210–240, 345–376. ———. *01_源码/beauty_smooth.h*, ll. 363–369. ———. *01_源码/beauty_env.h*, ll. 28–35. ———. *01_源码/beauty_params.h*, l. 888. ———. *02_构建/build_1.0.13.12.bat*, l. 73. ———. *05_验证/check_docs.py*, 文件头与 ll. 195–300.

---

## 9. 补丁执行回执（2026-11-10 08:39，GMT+8）

> **本节覆盖本文的审查基线。** 第 2 节的问题清单、行号与代码原文是**补丁前**快照；
> 当前工作区源码已按本节修改。复核时请同时看逐字备份
> `D://插件//_整理_20261110//before_patch_20261110//`（3 个改前源文件）。
> 本文「当前结论」自此转为历史结论，**不得据此判断补丁后代码仍存在这些问题**。

### 9.1 落地范围

按 §6 前三条 + 第 4 条中的 #4 落地，共 **4 个确认成立的高/中危问题**；#5 随 #3 一并修。
#6–#11 按 §6 第 4 条原文「建议合并进下一个修订位版本」**未落地** —— #6 是新增导出函数
（用户可见新功能）、#11 涉及 25 个构建脚本，不擅自扩大范围。

| # | 文件 | 改后定位 | 改法 |
|---|---|---|---|
| 1 | `01_源码/beauty_core.cpp` | `releaseSlot` L2162、`AsyncState` L3810/L3833、`stopAsync` L3876、`asyncWorker` L3987/L4019 | 新增 `cvDone` 与 `runningSlot`；`releaseSlot` 先在 `async_.m` 下撤销该 slot 的 pending 任务、等 `runningSlot != slot`、丢弃未取走的 `ready` 结果，**之后**才持 `slotsMtx_` 重置 `DetState`；worker 取任务记 `runningSlot`、收尾清并 `cvDone.notify_all()`；`stopAsync` 补 notify 防退出时死等 |
| 2 | `01_源码/obs-beauty.cpp` | L319 | `bzalloc` 后加 `if (!f) return NULL;`，再 `InitializeSRWLock` |
| 3 + 5 | `01_源码/beauty_onnx.cpp` | L201、L235 | 接住 `SessionGetInputName` / `SessionGetOutputName` 的 `OrtStatus*` 并 `ReleaseStatus`；「调用失败」与「成功但空名」拆两支；失败分支不 `Free(name)`；补 `!on || !on[0]` 判空，避免 `nullptr` 构造 `std::string` |
| 4 | `01_源码/beauty_core.cpp` | `submitAsync` L3883 | 互斥条件加 `async_.ready`；`src/w/h` 前置校验；8MB 帧 `memcpy` 从 `async_.m` 锁外移入锁内，与 `collectAsync` 的 `heldFrame_.swap` 同锁 |

输出名分支额外收紧：任一输出名取不到时**整体返回模型加载失败**，不再静默跳过。
理由是 `outNames_` 的元素顺序与 ORT 输出序号一一对应（`run()` 直接拿它构造 `Run` 的名字数组），
跳过会造成名字与索引错位。这属于行为变化，见 §9.3。

### 9.2 验证证据（可复核）

| 检查 | 结果 |
|---|---|
| 改前基线：`cl -Zs` × 3 文件 | 全部 `exit=0` |
| 改后语法：`cl -Zs -EHsc -std:c++17 -W3 -utf-8 /DBEAUTY_ENV_LOCK=1` × 3 文件 | 全部 `exit=0`，0 error / 0 warning |
| 完整编译链接：11 个 `.cpp` + `obs.lib`，MSVC 19.51.36260 | `exit=0`，产出 `C:/Temp/beauty_patch_build/obs-beauty.dll` **465,920 B**（仅验证用，**未覆盖** `02_构建/build_1.0.13.12/` 的发布 DLL） |
| 行尾保持 | `beauty_core.cpp` LF、`obs-beauty.cpp` CRLF、`beauty_onnx.cpp` LF，均未变 |
| 工作区 diff 规模 | `beauty_core.cpp` +46/−10、`beauty_onnx.cpp` +27/−5、`obs-beauty.cpp` +4/−0，合计 **+77/−15** |
| **未做** | 未加载 DLL、未运行插件、未做画面逐字节对比、未做并发压测 / 装·卸 40 项回归 |

### 9.3 行为变化与新增风险（个人推测，需运行时证据）

1. **`ready` 门可能阻塞全局提交**：若某 slot 的结果长期不被取走（源隐藏、滤镜停止渲染），
   `submitAsync` 会一直 return，其他 slot 也提交不了。原实现是覆盖后继续。这是报告 #4 建议本身的取舍，**未实测**。
2. **`releaseSlot` 的等待依赖 worker 正常收工**：谓词含 `quit` 兜底，但若 worker 在 `buildMaskInto`
   内卡死，滤镜销毁会等待；本补丁未加超时保护。
3. **8MB `memcpy` 改持锁**：与 `collectAsync` 的 `swap` 互斥了，代价是 `async_.m` 持锁时间增加
   （1080p 下约 0.7ms，静态估算、未实测）。
4. **ORT 输出名失败改为整体加载失败**：避免索引错位，但改变了加载失败路径的行为。
5. **竞态只解决了一部分**：本补丁消除的是 `releaseSlot` 与 `asyncWorker` 的并发；`process()` /
   `collectAsync()` 仍无锁访问 `slots_[slot]`，其与 `releaseSlot` 的安全性仍依赖「OBS 保证
   destroy 与 render 串行」这一 **§5 第 3 项待人工确认前提**。

### 9.4 版本与文档同步

- `BEAUTY_BUILD_STR` **未改**，仍 `1.0.13.12`。理由：升版本会触发 `check_docs.py` 断言 [7]/[9]
  连锁（7 篇严格篇目的文档头须同步），且 `README.md` §2 记载 `1.0.13.11` / `1.0.13.12`
  两次源码修复的版本位**均由用户亲自裁定**。按四段式字面规则，修 bug 对应 `1.0.14.0`，
  **待维护人裁定后另行发版**；当前 `02_构建/build_1.0.13.12/` 与
  `06_安装包/OBS美颜_CPU_v1.0.13.12.exe` 都是补丁前产物。
- 已同步：`README.md` 文首声明块、`docs/CHANGELOG.md` §1 表后声明块、本文 §9。
- `docs/INDEX.md` **未改**：本批无文档增删，适用版本与「最后核对」日期均未变，总表无需变更。
- 本项目**无 `PROGRESS.md`**；按项目实况，版本/阶段/待办信息由 `README.md` §2 与
  `docs/CHANGELOG.md` §1 承担。

### 9.5 新增待人工确认项（在 §5 的 7 项之外）

1. `ready` 门在多实例 / 长期不渲染场景是否会实际造成异步检测停摆。
2. `releaseSlot` 等待是否会出现 filter 销毁卡顿；是否需要 `wait_for` 超时与告警。
3. 持锁 `memcpy` 对渲染帧率的可测影响。
4. ORT 输出名获取失败改为整体失败，是否会拒载原本可用的模型。
5. MSVC 链接产物 `465,920 B` 与发布版 `464,896 B` 的差异是否仅为补丁本身（**未做二进制 diff**）。

### 9.6 事实与推测分界

- **可验证事实**：§9.2 的命令、退出码、DLL 字节数、行尾、diff 行数，以及 §9.1 的文件与行号，
  均来自本轮命令输出与工作区源码。
- **个人推测（显式标记）**：§9.3 全部 5 条、§9.4 的版本位判断、§9.5 全部 5 项。
- **不知道**：补丁后插件能否正常加载、出图、并发下是否还有崩溃；本轮没有运行任何一次插件。

