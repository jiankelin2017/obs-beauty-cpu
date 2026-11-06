# -*- coding: utf-8 -*-
"""bench_core.py 0.1.2 —— CoreEngine 的 CPU 性能基线 / 优化后对比

测三档分辨率下 process() 的真实耗时，并按**确定性节拍**把「纯磨皮帧」与
「含检测帧」分开统计，再按生产口径给出 30fps 均摊值。

为什么 0.1.0 重写了分组逻辑
--------------------------
0.1.0 之前的版本用「2 倍中位数切一刀」（`ms > median * 1.8` 判为检测帧）。
实测这个判据**从来没生效过**：三档分辨率全部给出 `含检测 = None`，
均摊值退化成「混在一起的均值」。原因是检测帧相对纯磨皮帧的真实倍率只有
约 1.5x（当时 1080p 实测 ~31ms vs ~20ms；绝对值已被 0.1.1 作废，但「判据
失效」这一事实不变），远达不到 1.8 的阈值；低分辨率下两者更是完全分不开。

现在的做法：不再猜阈值，而是利用**调用序号**直接确定每帧的身份。
`01_源码/beauty_core.cpp` 的同步路径里 `maskAge_` 从 0 起算、`kMaskEverySync = 4`，
因此节拍是「1 帧重算 + 4 帧沿用」= 周期 5；换分辨率时 `maskAge_` 会被置为 999，
于是「换分辨率后的第 0 次调用必定是检测帧」。据此，第 j 次调用（j 从 0 起算）
为检测帧当且仅当 `j % 5 == 0`。逐帧实测（1080p 的尖峰精确落在第 0/5/10/15 帧）
已复核这一推断。

由此得到的均摊口径是 **4:1**（4 帧沿用 : 1 帧重算），而不是旧版注释里的 3:1。
`01_源码/beauty_core.cpp` 里 `kMaskEverySync` 的注释也自述「按 1/5 摊」，
与 4:1 一致。

为什么 0.1.1 必须关掉台架的逐帧预热
------------------------------------
0.1.0 跑出来的基线里，640x394 / 720p 的「含检测」与「纯磨皮」几乎同价
（1.04x / 0.90x），1080p 却干净地分开（1.45x）。追下来是**离线台架自身的
副作用**，不是引擎特性：

* `01_源码/core_probe.cpp` 的 `BeautyCoreRun()` **每一帧**都调 `ensureReady()`；
* `ensureReady()` 末尾无条件调 `warmUp()`（`01_源码/beauty_core.cpp`）；
* `warmUp()` 会额外跑一次完整的 YuNet 推理（合成 640×360 灰帧），这次推理在
  `process()` 之外，因此**不计入 `lastCoreMs()`**；同时它把 `mask_` 按固定的
  1920×1080 重新 `assign`，小分辨率下 `updateMask()` 下一帧又会改回 w×h，
  两条路每帧互相覆盖，顺带把 `maskAge_` 反复压回 999 ⇒ 小分辨率**根本没有
  沿用帧**，全是重算帧，所以按序号分出来的两组当然同价。

验证：`BEAUTY_NO_PREWARM=1`（源码里现成的 A/B 开关）之后，三档都出现清晰的
周期 5；强制每帧重算（在 w×h 与 (w+1)×h 之间交替）使三档帧时间分别
3.6→13.1 / 7.5→17.7 / 20.2→30.7 ms，检测开销约 +10ms 且与分辨率无关，
与「YuNet 640×640 推理」一致。关掉预热后墙钟/帧也从 28.4→12.6 ms（640x394）。

结论：本脚本必须设 `BEAUTY_NO_PREWARM=1`，把一次性预热留给热机帧自己吸收。
生产环境不会每帧调 `ensureReady()`，这个开关反而让台架更贴近稳态。
**0.1.0 的 sync_20261106 / async_20261106 两组基线数字因此作废，已用 0.1.1 重跑覆盖。**

注意 `warmUp()` 的开关写法是 `if (getenv("BEAUTY_NO_PREWARM")) return;`
（`01_源码/beauty_core.cpp:1852`）：只判断变量**是否存在**，`=0` 同样跳过预热。
做开/关对照实验时不能靠改值，必须 `os.environ.pop()` 掉整个变量。

0.1.0 还补了一个**口径开关** `--async`。原因：同步模式下检测压在渲染线程上、
每 5 帧集中收一次钱；而生产（`01_源码/beauty_core.cpp` 的 `g_cfg.asyncDetect`
默认 true）是检测跑在 worker 上、每帧提交一次。两种口径不能互换：0.1.1 在
关掉逐帧预热后实测 640x394 同步均摊 5.01ms、异步帧 p50 3.58ms，差额约 1.4ms
正好是「1/5 × 检测开销」；worker 侧的推理成本体现在 CPU 占用上，不在帧时间里。
异步模式下帧时间与检测节拍无关，本脚本只报分布（p50/p95/max），不报三组数。

为什么 0.1.2 把异步模式拆成「每档分辨率一个进程」
--------------------------------------------------
0.1.1 的异步台架在单进程内连测 640x394 → 720p → 1080p，实测高概率以
`0xC0000005`（访问违例）退出。受控实验（子进程隔离，每组 4 次）把触发条件
收敛为四条同时成立：异步检测、关掉逐帧预热、**从较小分辨率切到 1920×1080**、
默认每帧提交节奏。单档 60 帧（开/关预热都试过）4/4 正常，三档切换 + 默认节奏
0/4 全崩，640→1080 两档也 0/4 全崩；崩溃点固定在切档后 1080p 第一帧的
`BeautyCoreRun` 调用期间。每档间 sleep 250ms 无效，`BEAUTY_MASK_EVERY=4` 能规避
但会把提交节奏改成非生产口径。

0.1.2 的处理：`--async` 时父进程按分辨率依次拉起独立子进程，每个进程内只存在
一种尺寸，因此没有尺寸跃迁，触发条件不成立；父进程收集分片后统一出报告。
同步模式不崩，仍保持单进程连测三档，口径不变。

两个必须说清的代价：
* 每档子进程都要重新加载一次模型，**一次性成本由 10 帧热机吸收**；因此
  0.1.1 的异步数字与 0.1.2 不直接可比，前后对比须用同一版本重跑。
* 任一子进程失败（非零退出或没写出分片），父进程立即显式报错并中止，
  **不产出半成品报告**，也不静默给出一个看似正常的数。

不采用「异步下不关预热」这个规避法：那会把 0.1.1 刚修掉的每帧额外 YuNet
推理重新引回来，虽然不计入 `lastCoreMs`，但会抢核并污染帧时间分布。

用法：
    python bench_core.py                     # 同步模式，tag=base（会覆盖同名历史快照，慎用）
    python bench_core.py <tag>               # 同步模式，存成 bench_<tag>.{md,json}
    python bench_core.py <tag> --cycles 8    # 每档多跑几个周期（默认 6）
    python bench_core.py <tag> --async      # 异步（贴生产），0.1.2 起每档独立进程
    python bench_core.py <tag> --async --worker 1   # 内部：只测第 1 档，供父进程调度

输出：`05_验证/goldens/masks/bench_<tag>.{md,json}`

版本：0.1.2（普通升级：异步模式改为每档独立进程，规避离线台架的分辨率跃迁
访问违例；CPU 产品版本轴仍由 `01_源码/beauty_params.h` 单点维护，与脚本自身
版本互不相干）
"""

import ctypes
import json
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
SRC_PNG = os.path.join(HERE, 'goldens', 'src', 'face_src.png')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks')

SIZES = [('640x394', 640, 394), ('720p', 1280, 720), ('1080p', 1920, 1080)]
# 同步路径的检测周期：maskAge_ 从 0 起算 + kMaskEverySync = 4
# ⇒ 「1 帧重算 + 4 帧沿用」= 5 帧一轮；检测帧满足 j % 5 == 0。
CYCLE = 5
PURE_PER_CYCLE = CYCLE - 1     # 4 帧沿用
CYCLES = 6                     # 每档测 6 轮 = 6 检测 + 24 沿用
WARM_FRAMES = 2 * CYCLE        # 热机 2 轮（10 帧），10 % 5 == 0 不破坏相位

VERSION = '0.1.2'


def ascii_path(p):
    """cv2 / ORT 读不了中文路径，这里只是给模型用的；raw 读写用 ACP 转换即可。"""
    return p


def prep():
    os.makedirs(RES, exist_ok=True)
    im = Image.open(SRC_PNG).convert('RGB')
    made = []
    for name, w, h in SIZES:
        raw = os.path.join(RES, name + '.raw')
        if os.path.exists(raw) and os.path.getsize(raw) == w * h * 4:
            made.append((name, w, h, raw))
            continue
        r = im.resize((w, h), Image.LANCZOS)
        rgba = np.dstack([np.asarray(r, np.uint8),
                          np.full((h, w, 1), 255, np.uint8)])
        rgba.tofile(raw)
        made.append((name, w, h, raw))
    return made


def stats(vals):
    if not vals:
        return None
    a = np.array(vals, dtype=float)
    return {
        'n': len(vals),
        'p50': round(float(np.median(a)), 2),
        'min': round(float(a.min()), 2),
        'max': round(float(a.max()), 2),
    }


def part_file(tag, idx):
    """异步模式下，第 idx 档子进程写回的分片结果。"""
    return os.path.join(OUT, '_bench_part_%s_%d.json' % (tag, idx))


def load_engine(mode):
    # 同步模式：节拍分组的前提。异步时「第 k 帧用哪份掩码」取决于线程调度，
    # 序号与身份不再一一对应，只能报帧时间分布。
    os.environ['BEAUTY_ASYNC_DETECT'] = '1' if mode == 'async' else '0'
    # 关键：core_probe.cpp 每帧都调 ensureReady() → warmUp()，后者会额外跑一次
    # YuNet 推理（不计入 lastCoreMs）并把 maskAge_ 反复压回 999。不关掉它，
    # 小分辨率就没有「沿用帧」，分组与绝对值全是错的。见文件头 0.1.1 说明。
    os.environ['BEAUTY_NO_PREWARM'] = '1'
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    return dll


def measure_one(name, w, h, raw, dll, tmp, mode, warm, total):
    """只测一档分辨率，返回一行报告。进程内不切换尺寸。"""
    msg = ctypes.create_string_buffer(512)
    series = []
    # 热机：让模型加载、内存分配、掩码初始化都完成。
    # 同步模式下同时正好对齐相位 —— 换分辨率后第 0 次调用必定是检测帧（maskAge_=999）。
    for _ in range(warm):
        rc = dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                               w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        if rc != 0:
            print('[bench] rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
            return None
    for k in range(total):
        j = warm + k            # 换分辨率以来的调用序号，用于定身份
        rc = dll.BeautyCoreRun(raw.encode('utf-8'), tmp.encode('utf-8'),
                               w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
        if rc != 0:
            print('[bench] rc=%d %s' % (rc, msg.value.decode('utf-8', 'replace')))
            return None
        info = msg.value.decode('utf-8', 'replace')
        ms = float(info.split('ms=')[1].split()[0])
        faces = int(info.split('faces=')[1].split()[0])
        series.append({'j': j, 'detect': (mode == 'sync' and j % CYCLE == 0),
                       'ms': round(ms, 2)})

    allv = np.array([s['ms'] for s in series], dtype=float)
    p50 = float(np.median(allv))
    p95 = float(np.percentile(allv, 95))
    mean = float(allv.mean())

    if mode == 'async':
        # 异步：帧时间与检测节拍无关，只报分布。
        amortized = p50
        row = {
            'res': name, 'w': w, 'h': h, 'mode': 'async',
            'min': round(float(allv.min()), 2),
            'median': round(p50, 2),
            'p95': round(p95, 2),
            'mean': round(mean, 2),
            'max': round(float(allv.max()), 2),
            'faces': faces,
            'amortized': round(amortized, 2),
            'warn': None,
            'series': series,
        }
        print('  %-8s 帧 p50 %6s ms | p95 %6s ms | max %6s ms | faces=%d'
              % (name, row['median'], row['p95'], row['max'], row['faces']))
        return row

    pure = [s['ms'] for s in series if not s['detect']]
    det = [s['ms'] for s in series if s['detect']]
    ps, ds = stats(pure), stats(det)

    # 均摊：一轮周期 = 4 帧沿用 + 1 帧重算，按 4:1 加权
    if ps and ds:
        amortized = (ps['p50'] * PURE_PER_CYCLE + ds['p50']) / float(CYCLE)
    else:
        amortized = p50

    # 自检：检测帧理论上不该和沿用帧同价。若同价，先别信均摊值 ——
    # 要么成本被淹没在噪声里，要么检测没落在这条线程的这一帧上，两者都要人来看。
    ratio = (ds['p50'] / ps['p50']) if (ps and ds and ps['p50'] > 0) else None
    warn = None
    if ps is None or ds is None:
        warn = '分组为空：本轮没有收到 %s 帧' % ('检测' if ds is None else '沿用')
    elif ratio is not None and ratio < 0.95:
        warn = ('检测帧比沿用帧还快（%.2fx），节拍/相位与源码语义可能脱节，'
                '均摊值不可信' % ratio)
    elif ratio is not None and ratio < 1.05:
        warn = ('检测帧与沿用帧几乎同价（%.2fx）：该档重算成本被噪声淹没，'
                '或检测不在本帧本线程上 —— 均摊≈纯磨皮，绝对值需交叉核对' % ratio)

    row = {
        'res': name, 'w': w, 'h': h, 'mode': 'sync',
        'min': round(float(allv.min()), 2),
        'median': round(p50, 2),
        'p95': round(p95, 2),
        'max': round(float(allv.max()), 2),
        'pure_med': ps['p50'] if ps else None,
        'detect_med': ds['p50'] if ds else None,
        'n_pure': ps['n'] if ps else 0,
        'n_detect': ds['n'] if ds else 0,
        'pure_min': ps['min'] if ps else None,
        'pure_max': ps['max'] if ps else None,
        'detect_min': ds['min'] if ds else None,
        'detect_max': ds['max'] if ds else None,
        'detect_pure_ratio': round(ratio, 2) if ratio is not None else None,
        'cycle': CYCLE,
        'weight': '%d:1' % PURE_PER_CYCLE,
        'faces': faces,
        'amortized': round(amortized, 2),
        'warn': warn,
        'series': series,
    }
    print('  %-8s 纯磨皮 %6s ms (n=%d) | 含检测 %6s ms (n=%d) | %.2fx | '
          '30fps均摊 %6s ms | faces=%d'
          % (name, row['pure_med'], row['n_pure'], row['detect_med'],
             row['n_detect'], ratio or 0.0, row['amortized'], row['faces']))
    if warn:
        print('           ! %s' % warn)
    return row


def run_parent(tag, cycles, warm, total, made):
    """异步：每档一个独立子进程，进程内不发生分辨率跃迁。"""
    print('[bench] 模式=异步（贴生产）；台架 0.1.2 每档独立进程；'
          '热机 %d 帧，每档测 %d 帧' % (warm, total))
    report = []
    for idx, (name, w, h, raw) in enumerate(made):
        pf = part_file(tag, idx)
        if os.path.exists(pf):
            os.remove(pf)
        cmd = [sys.executable, os.path.abspath(__file__), tag,
               '--cycles', str(cycles), '--async', '--worker', str(idx)]
        print('[bench] 第 %d/%d 档 %s → 独立子进程' % (idx + 1, len(made), name))
        # 输出走管道时父进程 stdout 是块缓冲；先刷新，避免子进程日志跑到父进程前面。
        sys.stdout.flush()
        rc = subprocess.call(cmd, cwd=HERE)
        if rc != 0 or not os.path.exists(pf):
            print('[bench] 第 %d 档 (%s) 子进程 exit=%d%s；本轮中止，不产出报告。'
                  % (idx, name, rc, '' if os.path.exists(pf) else '，且没有写回分片'))
            for j in range(len(made)):
                q = part_file(tag, j)
                if os.path.exists(q):
                    os.remove(q)
            return 4
        with open(pf, 'r', encoding='utf-8') as f:
            report.append(json.load(f))
        os.remove(pf)
    render(report, tag, 'async', cycles, warm)
    return 0


def render(report, tag, mode, cycles, warm):
    if mode == 'async':
        md = ['# CoreEngine CPU 帧时间分布（异步检测） —— %s\n' % tag,
              '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
              '> 台架：`bench_core.py` %s；磨皮 50 档，down=1（未降采样）；'
              '`BEAUTY_ASYNC_DETECT=1`、`BEAUTY_NO_PREWARM=1`' % VERSION,
              '> 每档 %d 帧（热机另算 %d 帧）\n' % (cycles * CYCLE, warm),
              '| 分辨率 | p50 | p95 | max | 均值 | 预算余量(33ms) |',
              '|---|---|---|---|---|---|']
        for r in report:
            md.append('| %s | **%s ms** | %s ms | %s ms | %s ms | %s |'
                      % (r['res'], r['median'], r['p95'], r['max'], r['mean'],
                         '够' if r['p95'] <= 33
                         else '超 %.1fx' % (r['p95'] / 33.0)))
        md.append('')
        md.append('> 异步模式下检测跑在 worker 线程、每帧提交（`maskEveryAsync = 0`），'
                  '渲染线程的帧时间不再随预测节拍起伏，因此只报分布、不报三组数。')
        md.append('> **worker 侧的推理与掩码成本不含在本表内** —— 它体现在 CPU 占用上，'
                  '不在帧预算里。判「掉不掉帧」看本表，判「吃多少核」要看进程 CPU 占用。')
        md.append('> 这是贴生产口径的数（`g_cfg.asyncDetect` 默认 true）；'
                  '同步口径（每 5 帧集中收一次检测钱）见同名 `-sync` 输出。')
        md.append('')
        md.append('> **0.1.2 口径变更**：`--async` 改为每档分辨率一个独立子进程。'
                  '0.1.1 在单进程内连切三档时，异步检测 + 关预热 + 从较小分辨率切到 '
                  '1920×1080 + 默认每帧提交会稳定触发访问违例（受控实验 0/4 成功）；'
                  '独立进程内没有尺寸跃迁，条件不成立。代价是每档都重新加载一次模型，'
                  '一次性成本由 %d 帧热机吸收，**因此 0.1.1 的异步数字与本表不直接可比**，'
                  '前后对比须用同一台架版本重跑。任一子进程失败时父进程立即中止，'
                  '不产出半成品报告。' % warm)
    else:
        md = ['# CoreEngine CPU 性能基线 —— %s\n' % tag,
              '> 生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
              '> 台架：`bench_core.py` %s；磨皮 50 档，down=1（未降采样）；'
              '`BEAUTY_ASYNC_DETECT=0` 强制同步、`BEAUTY_NO_PREWARM=1`' % VERSION,
              '> 每档 %d 轮 × %d 帧 = %d 帧（热机另算 %d 帧）\n'
              % (cycles, CYCLE, cycles * CYCLE, warm),
              '| 分辨率 | 纯磨皮帧 p50 | 含检测帧 p50 | 30fps 均摊 | 预算余量(33ms) |',
              '|---|---|---|---|---|']
        for r in report:
            md.append('| %s | %s ms | %s ms | **%s ms** | %s |'
                      % (r['res'], r['pure_med'], r['detect_med'], r['amortized'],
                         '够' if r['amortized'] <= 33
                         else '超 %.1fx' % (r['amortized'] / 33.0)))
        md.append('')
        md.append('| 分辨率 | 纯磨皮 n / min–max | 含检测 n / min–max | 检测/沿用倍率 | 自检 |')
        md.append('|---|---|---|---|---|')
        for r in report:
            md.append('| %s | %d / %s–%s ms | %d / %s–%s ms | %sx | %s |'
                      % (r['res'], r['n_pure'], r['pure_min'], r['pure_max'],
                         r['n_detect'], r['detect_min'], r['detect_max'],
                         r['detect_pure_ratio'] if r['detect_pure_ratio'] else '-',
                         r['warn'] or 'ok'))
        md.append('')
        md.append('> 「纯磨皮帧」= 沿用上次掩码的帧；「含检测帧」= 重跑 YuNet 的帧。'
                  '同步路径 `kMaskEverySync = 4` 且 `maskAge_` 从 0 起算，'
                  '实际节拍为「1 帧重算 + %d 帧沿用」= 周期 %d，'
                  '故 30fps 均摊按 %d:1 加权（不是 3:1）。'
                  % (PURE_PER_CYCLE, CYCLE, PURE_PER_CYCLE))
        md.append('> 帧身份按**调用序号**判定（第 j 次调用为检测帧 ⇔ `j %% %d == 0`），'
                  '不依赖耗时阈值；「检测/沿用倍率」列与「自检」列用于验证该推断仍然成立。'
                  % CYCLE)
        md.append('> 本表是**同步口径**，不等于生产：生产默认异步检测，'
                  '帧时间见同名的 `--async` 输出。')
        md.append('> 同步模式仍是单进程连测三档；0.1.2 的进程拆分只作用于 `--async`。')
        md.append('> 均摊值只覆盖引擎层；插件层 `gs_stagesurface_map` 下载与 '
                  '`gs_texture_set_image` 上传往返不在其中。')

    md.append('> `BEAUTY_NO_PREWARM=1` 是本脚本必须的：`core_probe.cpp` 每帧都调 '
              '`ensureReady()` → `warmUp()`，后者会额外跑一次 YuNet 推理（不计入 '
              '`lastCoreMs`）并把 `maskAge_` 反复压回 999；不关掉它，小分辨率就没有 '
              '「沿用帧」，按序号分出来的两组会几乎同价。一次性预热成本已由热机帧吸收。')

    out_md = os.path.join(OUT, 'bench_%s.md' % tag)
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    with open(os.path.join(OUT, 'bench_%s.json' % tag), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[bench] -> %s' % out_md)
    return 0


def main():
    argv = sys.argv[1:]
    cycles = CYCLES
    if '--cycles' in argv:
        i = argv.index('--cycles')
        try:
            cycles = max(1, int(argv[i + 1]))
            del argv[i:i + 2]
        except (IndexError, ValueError):
            print('[bench] --cycles 需要一个整数')
            return 1

    worker = None
    if '--worker' in argv:
        i = argv.index('--worker')
        try:
            worker = int(argv[i + 1])
            del argv[i:i + 2]
        except (IndexError, ValueError):
            print('[bench] --worker 需要一个档位序号（0..2）')
            return 1
        if not 0 <= worker < len(SIZES):
            print('[bench] --worker 序号越界：0..%d' % (len(SIZES) - 1))
            return 1

    mode = 'async' if '--async' in argv else 'sync'
    if '--async' in argv:
        argv.remove('--async')
    tag = argv[0] if argv else 'base'

    if not os.path.exists(DLL):
        print('[bench] missing %s (run build_core_test.bat)' % DLL)
        return 2

    os.makedirs(OUT, exist_ok=True)
    # 主进程先把三档素材备齐，避免多个子进程同时写同一个 raw 文件。
    made = prep()

    warm = WARM_FRAMES
    total = cycles * CYCLE
    if mode == 'sync':
        print('[bench] 模式=同步；节拍：1 检测 + %d 沿用 = 周期 %d；热机 %d 帧，每档测 %d 帧'
              % (PURE_PER_CYCLE, CYCLE, warm, total))

    if mode == 'async' and worker is None:
        return run_parent(tag, cycles, warm, total, made)

    dll = load_engine(mode)
    if worker is not None:
        # 内部子进程：只测这一档，写回分片，不产出报告。
        name, w, h, raw = made[worker]
        tmp = os.path.join(OUT, '_bench_out_%s_%d.raw' % (tag, worker))
        row = measure_one(name, w, h, raw, dll, tmp, mode, warm, total)
        if os.path.exists(tmp):
            os.remove(tmp)
        if row is None:
            return 3
        with open(part_file(tag, worker), 'w', encoding='utf-8') as f:
            json.dump(row, f, ensure_ascii=False)
        return 0

    tmp = os.path.join(OUT, '_bench_out.raw')
    report = []
    for name, w, h, raw in made:
        row = measure_one(name, w, h, raw, dll, tmp, mode, warm, total)
        if row is None:
            return 3
        report.append(row)
    if os.path.exists(tmp):
        os.remove(tmp)
    return render(report, tag, mode, cycles, warm)


if __name__ == '__main__':
    sys.exit(main())
