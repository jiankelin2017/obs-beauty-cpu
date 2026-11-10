# -*- coding: utf-8 -*-
"""dual_instance_check.py —— CoreEngine「双实例」离线对拍

要回答的问题
------------
OBS 里挂两个「美颜」滤镜实例时，两个实例走的是**同一个** IBeautyEngine 单例：
obs-beauty.cpp 每个实例 `beautyEngine().acquireSlot()`，而 beauty_core.cpp 里
`beautyEngine()` 是 `static IBeautyEngine* s`。

* 1.0.13.1：acquireSlot 恒返回 0，方向状态是 CoreEngine 成员 ⇒ 一份状态两个调用方。
  本脚本实测命中率 30/30 → 1/30（以下 diff 模式）。
* 1.0.13.2：检测态按 slot 切开（DetState），acquireSlot 发唯一号，
  process(slot,…) / 掩码导出都按 slot 取上下文 ⇒ 两个实例互不可见。

判据（不另写模拟，直接跑生产同一条 buildMaskInto）
--------------------------------------------------
buildMaskInto 开头的分辨率闸门：

    if (w != rotLastW || h != rotLastH) { autoMiss=0; autoCool=0; effRot=rotManual; … }

「换分辨率」= 方向结论清零 + 重新攒 20 次无脸（g_cfg.autoRotMiss=20）。
若 A 是「躺倒的源」（要自动探测到 90/270 才检出脸），而 B 的分辨率与 A 不同，
那么**只要状态是共享的**，B 每跑一次就把 A 的计数器清零，A 永远攒不到 20 次。

模式（**必须一模式一进程**：引擎状态跨调用保留，同进程连跑会互相污染）
    solo  : 60 次全喂 A                      —— A 能不能自己收敛
    same  : 30 次 A，然后 30 轮 (A, 无脸B同尺寸) —— 对照组：分辨率一样
    diff  : 30 次 A，然后 30 轮 (A, 无脸B异尺寸) —— 实验组：分辨率变了
    proc  : 走生产入口 process()，solo 与 diff 各一遍
    detect: 只确认素材站得住（跑满 25 次，让自动探测有触发机会）

时序 EMA（1.0.13.3）
    ema_solo : 只喂 A，同一帧 40 次，记每帧输出 md5
    ema_dual : 每喂 A 一次就插一次 B（异尺寸、无脸），同样记 A 的 md5
    ema_cmp  : 只读上面两份 CSV 比对 —— A 的 md5 序列必须逐帧相同

    判据的依据：细节层 EMA 的历史靠 `detailEmaGen + 1 == frameNo` 判断「有没有断帧」。
    frameNo 若是进程级共享，B 每跑一次就把它推进一格，A 下次进来必然判成断帧 →
    历史整片作废 → 明细层每帧从零起步。改了之后 frameNo 按 slot 各记一份，
    B 跑多少次都不影响 A 的序列。

真并发（1.0.13.4）
    mt_solo : 一条线程喂 A 40 次，记掩码 md5
    mt_dual : **两条线程同时**开跑（A 一次 B 一次，各自 40 次），同样记 A 的 md5
    mt_cmp  : 比对上面两份 —— A 的掩码必须逐帧相同

    为什么前面几种模式测不出这一条：solo / same / diff 都是**同一线程里交替**，
    检测器任何时刻只有一条线程在用，"串行" 是白送的。真实形态是两条渲染线程
    同时进来，而 detect() 的 640×640 中间图是成员缓冲（resized_ / input_）：
    一边 resize 重新分配，另一边还握着旧指针往里写 —— use-after-free。
    1.0.13.4 给 FaceDetector 加锁后这条才成立；之前的版本跑这个模式是非法的
    （可能崩在堆上，也可能只是偶尔错一帧）。

每个模式给 A、B 各领一个 slot（BeautyCoreAcquireSlot），这正是 OBS 里两个
滤镜实例的形态。
"""

import argparse
import ctypes
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
# 默认用本目录刚编出来的 beauty_core_test.dll；换个 DLL 复验（例如编一个「把锁
# 摘掉」的对照件，证明判据有牙）时用 BEAUTY_TEST_DLL 指过去即可。
DLL = os.environ.get('BEAUTY_TEST_DLL') or os.path.join(HERE, 'beauty_core_test.dll')
SRC = os.path.join(HERE, 'goldens', 'src', 'face_src.raw')
NOFACE = os.path.join(HERE, 'goldens', 'src', 'noface_gray.raw')
WORK = os.path.join(HERE, '_dual')

# 逐次预热（ensureReady 末尾无条件 warmUp）在这类批量台架上纯属浪费，
# 而且 warmUp 会把 0 号上下文的掩码缓冲按 1920x1080 重置。
# 源码里是「只看变量在不在」，设成 '1' 就等于关掉。
os.environ.setdefault('BEAUTY_NO_PREWARM', '1')
# 异步检测一开，「第 k 帧用哪份掩码」就取决于 worker 的调度，同一份输入重跑
# 两次的结果都可能不同（实测：maskdiff 0，但输出逐帧差 1 灰阶）。做**逐字节**
# 对拍必须把它关掉，否则量到的是线程时序，不是实例隔离。
os.environ.setdefault('BEAUTY_ASYNC_DETECT', '0')
# EMA 固定在「强平滑」档：beta 恒为 emaBetaStill，与运动量无关，
# 这样细节层的历史是否连续会直接体现在输出上（否则静态帧上 EMA 一帧就收敛，
# 判据对它完全不敏感 —— 这是第一版 ema 模式失败的原因）。
os.environ.setdefault('BEAUTY_EMA_STILL', '255')
os.environ.setdefault('BEAUTY_EMA_FULL', '256')
# 还得把「基准回填」强行打开并放大：默认 blurRefill=0.06、且要求实际磨皮强度
# I >= 0.3，探针只有 blur=50 一个参数，I 常常过不了这道门 —— 门一关，
# detailRefill 整段不跑，EMA 也就无从体现（第二版 ema 模式失败的原因）。
os.environ.setdefault('BEAUTY_BLUR_REFILL', '2.0')
os.environ.setdefault('BEAUTY_BLUR_REFILL_MIN_I', '0')
# 方向探测保持默认阈值 20，不要调小 —— 调小了就测不出「被清零」。
os.environ.pop('BEAUTY_INPUT_ROT', None)
os.environ.pop('BEAUTY_AUTO_ROT', None)


def load_dll():
    d = ctypes.WinDLL(DLL)
    d.BeautyCoreAcquireSlot.argtypes = [ctypes.c_char_p, ctypes.c_int]
    d.BeautyCoreAcquireSlot.restype = ctypes.c_int
    d.BeautyCoreMaskSlot.argtypes = [ctypes.c_int, ctypes.c_char_p,
                                     ctypes.c_int, ctypes.c_int,
                                     ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    d.BeautyCoreMaskSlot.restype = ctypes.c_int
    d.BeautyCoreRunSlot.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                    ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                    ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    d.BeautyCoreRunSlot.restype = ctypes.c_int
    return d


def acquire_slots(dll, n):
    slots = []
    for _ in range(n):
        msg = ctypes.create_string_buffer(256)
        s = dll.BeautyCoreAcquireSlot(msg, 256)
        if s < 0:
            raise SystemExit('acquireSlot failed: ' + msg.value.decode('utf-8', 'replace'))
        slots.append(s)
    return slots


def read_raw(path):
    buf = np.fromfile(path, np.uint8)
    if buf.size != 640 * 394 * 4:
        raise SystemExit('unexpected raw size: %d (%s)' % (buf.size, path))
    return buf.reshape(394, 640, 4).copy()


def resize_rgba(arr, w, h):
    im = Image.fromarray(arr[:, :, :3], 'RGB').resize((w, h), Image.BILINEAR)
    rgb = np.asarray(im, np.uint8)
    return np.dstack([rgb, np.full((h, w, 1), 255, np.uint8)])


def make_frames():
    # 只覆盖素材，不清整个目录 —— 每个模式各跑一个进程，CSV 要能留下来对照。
    os.makedirs(WORK, exist_ok=True)

    face = read_raw(SRC)
    noface = read_raw(NOFACE)

    # A：源被转了 90°（竖屏摄像头 / 场景项旋转的典型形态）。numpy 是 (h,w)，
    #    rot90 把 (394,640) 变成 (640,394) —— 即 394x640 的竖画布。
    a = np.ascontiguousarray(np.rot90(face, k=1))
    pa = os.path.join(WORK, 'A_rot90.raw')
    a.tofile(pa)

    # B 同尺寸：无脸帧缩到 394x640，与 A 的 w/h 完全一致 → 不触发分辨率闸门。
    b_same = resize_rgba(noface, 394, 640)
    pb_same = os.path.join(WORK, 'B_same.raw')
    b_same.tofile(pb_same)

    # B 异尺寸：同一个无脸帧缩到 512x315 → 每次调用都清掉方向状态。
    b_diff = resize_rgba(noface, 512, 315)
    pb_diff = os.path.join(WORK, 'B_diff.raw')
    b_diff.tofile(pb_diff)

    # 正立参考：原图（640x394），用来证明「这张脸本身检得出来」。
    p_flat = os.path.join(WORK, 'A_upright.raw')
    face.tofile(p_flat)

    return {
        'A': (pa, a.shape[1], a.shape[0]),
        'A_up': (p_flat, 640, 394),
        'B_same': (pb_same, 394, 640),
        'B_diff': (pb_diff, 512, 315),
    }


def _ints(text):
    px = faces = -1
    for tok in text.split():
        if tok.startswith('px='):
            px = int(tok[3:].strip(',()'))
        elif tok.startswith('faces='):
            faces = int(tok[6:].strip(',()'))
    return px, faces


def call_mask(dll, slot, raw, w, h, out_path):
    msg = ctypes.create_string_buffer(512)
    rc = dll.BeautyCoreMaskSlot(slot, raw.encode('utf-8'), w, h,
                                out_path.encode('utf-8'), msg, 512)
    text = msg.value.decode('utf-8', 'replace')
    px, faces = _ints(text)
    if rc != 0:
        px = 0
    return rc, px, faces, text


def call_run(dll, slot, raw, w, h, out_path):
    msg = ctypes.create_string_buffer(512)
    rc = dll.BeautyCoreRunSlot(slot, raw.encode('utf-8'), out_path.encode('utf-8'),
                               w, h, 50.0, 0, 0.0, 0.0, 1, msg, 512)
    text = msg.value.decode('utf-8', 'replace')
    _, faces = _ints(text)
    return rc, faces, text


def run_mask(mode, frames):
    dll = load_dll()
    sa, sb = acquire_slots(dll, 2)
    print('slot A=%d  slot B=%d' % (sa, sb))
    tmp = os.path.join(WORK, 'mask.bin')
    pa, aw, ah = frames['A']
    records = []

    def step(tag, i, slot, raw, w, h):
        rc, px, faces, _ = call_mask(dll, slot, raw, w, h, tmp)
        records.append((tag, i, px, faces, rc))

    warm = 60 if mode == 'solo' else 30
    for i in range(warm):
        step('warmA', i, sa, pa, aw, ah)

    if mode != 'solo':
        key = 'B_same' if mode == 'same' else 'B_diff'
        pb, bw, bh = frames[key]
        for i in range(30):
            step('A', i, sa, pa, aw, ah)
            step('B', i, sb, pb, bw, bh)
    return records


def run_detect(frames):
    dll = load_dll()
    sa, _ = acquire_slots(dll, 2)
    tmp = os.path.join(WORK, 'mask.bin')
    out = []
    for name in ('A_up', 'A'):
        raw, w, h = frames[name]
        first = None
        for k in range(25):
            rc, px, faces, text = call_mask(dll, sa, raw, w, h, tmp)
            if px > 0 and first is None:
                first = k + 1
            out.append((name, k, px, faces, rc))
        print('%-6s %dx%d -> 首次出掩码 %s' % (name, w, h,
                                             ('第 %d 次' % first) if first else '从未'))
    return out


def run_proc(mode, frames):
    """走生产入口 process()。同步路径每 5 帧才重算一次掩码，所以要多喂几帧。"""
    dll = load_dll()
    sa, sb = acquire_slots(dll, 2)
    print('slot A=%d  slot B=%d' % (sa, sb))
    tmp = os.path.join(WORK, 'proc.raw')
    pa, aw, ah = frames['A']
    records = []

    def step(tag, i, slot, raw, w, h):
        rc, faces, _ = call_run(dll, slot, raw, w, h, tmp)
        records.append((tag, i, 0, faces, rc))

    for i in range(150):
        step('warmA', i, sa, pa, aw, ah)
    if mode == 'proc_diff':
        pb, bw, bh = frames['B_diff']
        for i in range(20):
            step('A', i, sa, pa, aw, ah)
            step('B', i, sb, pb, bw, bh)
    return records


def make_ema_frames():
    """给 EMA 对拍造序列：同一张脸，按 0..3 循环加不同的整体亮度偏移。

    为什么要变：静态帧上细节层 EMA 一两帧就收敛，判据对它完全不敏感
    （第一版 ema 模式就是这么空转的）。
    """
    base = read_raw(SRC)
    out = []
    for k in range(4):
        a = np.clip(base[:, :, :3].astype(np.int16) + (k * 7 - 10), 0, 255).astype(np.uint8)
        p = os.path.join(WORK, 'A_var%d.raw' % k)
        np.ascontiguousarray(np.dstack([a, base[:, :, 3]]), np.uint8).tofile(p)
        out.append(p)
    return out


def run_ema(mode, frames):
    """同一序列喂 16 帧，记 A 每帧输出的 md5。

    ema_dual 里 A 每跑一帧就插一次 B。B 用**同尺寸无脸帧**：它会走完整的
    「检测失败 → 沿用旧掩码」链路，但不会把 B 自己的画面内容写进 A 的掩码，
    判据只落在「有记忆的状态有没有被对方推进」这一件事上。
    """
    import hashlib

    dll = load_dll()
    sa, sb = acquire_slots(dll, 2)
    print('slot A=%d  slot B=%d' % (sa, sb))
    seq = make_ema_frames()
    pb, bw, bh = frames['B_same']
    tmp = os.path.join(WORK, 'ema.raw')
    rows = []

    for i in range(16):
        rc, _, _ = call_run(dll, sa, seq[i % 4], 640, 394, tmp)
        if rc != 0:
            raise SystemExit('run A failed rc=%d at %d' % (rc, i))
        md5 = hashlib.md5(open(tmp, 'rb').read()).hexdigest()
        rows.append((i, md5))
        if mode == 'ema_dual':
            call_run(dll, sb, pb, bw, bh, tmp)
    return rows


def run_ema_cmp():
    """比对 ema_solo / ema_dual 两份序列。"""
    import csv as _csv

    def read(mode):
        p = os.path.join(WORK, 'ema_%s.csv' % mode)
        if not os.path.exists(p):
            raise SystemExit('缺少 %s，先跑 --mode %s' % (p, mode))
        with open(p, encoding='utf-8') as f:
            return [(int(r['step']), r['md5']) for r in _csv.DictReader(f)]

    solo = read('solo')
    dual = read('dual')
    n = min(len(solo), len(dual))
    diff = [i for i in range(n) if solo[i][1] != dual[i][1]]

    # 顺带证明序列确实在变：16 帧同一个 md5 说明 EMA 没被触发，判据空转。
    distinct = len(set(m for _, m in solo))
    print('\n=== mode=ema_cmp ===')
    print('[solo] %d 帧，不同输出 %d 种' % (len(solo), distinct))
    print('[dual] %d 帧' % len(dual))
    if distinct < 2:
        print('[WARN] 各帧输出完全相同 —— 细节/EMA 路径没被触发，结论无意义')
    if diff:
        print('[FAIL] A 的 md5 序列在第 %s 帧起不一致（共 %d 帧不同）'
              % (diff[:6], len(diff)))
        print('       solo[0]=%s' % solo[0][1])
        print('       dual[0]=%s' % dual[0][1])
    else:
        print('[PASS] 两个模式下 A 的 md5 序列逐帧相同（%d 帧）' % n)
    return diff


def run_mt(mode, frames, n=40):
    """两条线程**同时**跑 BeautyCoreMaskSlot，量 A 的掩码是否被 B 搅动。

    · 线程里各自领一个 slot，调用序与 diff 模式一样，区别只在「并发 vs 交替」；
    · 两边写不同的输出文件，避免互相覆盖；
    · 掩码导出接口内部会停掉异步 worker 并强制同步 —— 于是每次调用都在**调用者
      自己的线程**上跑 buildMaskInto，两线程 = 两条检测路径同时在用同一个
      FaceDetector，正是要打的那条路径。
    """
    import hashlib
    import threading

    dll = load_dll()
    sa, sb = acquire_slots(dll, 2)
    print('slot A=%d  slot B=%d' % (sa, sb))

    out_a = os.path.join(WORK, 'mt_A.bin')
    out_b = os.path.join(WORK, 'mt_B.bin')
    pa, aw, ah = frames['A']
    pb, bw, bh = frames['B_diff']

    def worker(slot, raw, w, h, out_path, sink):
        for i in range(n):
            rc, px, faces, _ = call_mask(dll, slot, raw, w, h, out_path)
            if rc != 0:
                sink.append(('FAIL', 0))
                continue
            sink.append((hashlib.md5(open(out_path, 'rb').read()).hexdigest(), px))

    ra, rb = [], []
    # 先把 A 的方向收敛段走完（自动探测要攒 20 次无脸才会转 90°，见 detect 模式），
    # 否则前 20 次必然空掩码，比对段全被这一段噪声占掉。
    warm = os.path.join(WORK, 'mt_warm.bin')
    for _ in range(25):
        call_mask(dll, sa, pa, aw, ah, warm)

    ta = threading.Thread(target=worker, args=(sa, pa, aw, ah, out_a, ra))
    if mode == 'mt_dual':
        tb = threading.Thread(target=worker, args=(sb, pb, bw, bh, out_b, rb))
        tb.start()
    ta.start()
    ta.join()
    if mode == 'mt_dual':
        tb.join()
    return ra, rb


def run_mt_cmp():
    """比对 mt_solo / mt_dual 两份 A 的掩码序列。"""
    import csv as _csv

    def read(mode):
        p = os.path.join(WORK, 'mt_%s.csv' % mode)
        if not os.path.exists(p):
            raise SystemExit('缺少 %s，先跑 --mode mt_%s' % (p, mode))
        with open(p, encoding='utf-8') as f:
            return [(int(r['step']), r['md5'], int(r['px'])) for r in _csv.DictReader(f)]

    solo = read('solo')
    dual = read('dual')
    n = min(len(solo), len(dual))
    # 收敛段已在跑之前预热过，这里整段都参与比对。
    skip = 0
    diff = [i for i in range(skip, n) if solo[i][1] != dual[i][1]]
    empty = [i for i in range(n) if solo[i][2] <= 0 or dual[i][2] <= 0]

    print('\n=== mode=mt_cmp ===')
    print('[solo] %d 次，命中 %d 次' % (len(solo), sum(1 for r in solo if r[2] > 0)))
    print('[dual] %d 次，命中 %d 次' % (len(dual), sum(1 for r in dual if r[2] > 0)))
    if empty:
        print('[FAIL] 有 %d 次没出掩码（首个 = 第 %d 次）' % (len(empty), empty[0] + 1))
    if diff:
        print('[FAIL] A 的掩码在第 %s 次起不一致（共 %d 次不同）'
              % (diff[:6], len(diff)))
        print('       solo=%s' % solo[diff[0]][1][:12])
        print('       dual=%s' % dual[diff[0]][1][:12])
    elif empty:
        pass
    else:
        print('[PASS] 并发跑 B 时 A 的掩码逐次相同（第 %d..%d 次，共 %d 次）'
              % (skip + 1, n, n - skip))
    return diff, empty


def summarize(mode, records):
    print('\n=== mode=%s ===' % mode)
    if not records:
        return
    warm = [r for r in records if r[0] == 'warmA']
    tail = [r for r in records if r[0] == 'A']
    good = (lambda r: r[3] > 0) if mode.startswith('proc') else (lambda r: r[2] > 0)

    if warm:
        idx = [i for i, r in enumerate(warm) if good(r)]
        print('[预热段] %d 次，命中 %d 次，首次命中 %s' %
              (len(warm), len(idx), ('第 %d 次' % (idx[0] + 1)) if idx else '从未'))
    if tail:
        idx = [i for i, r in enumerate(tail) if good(r)]
        print('[交替段] %d 次 A，命中 %d 次（%.0f%%）' %
              (len(tail), len(idx), 100.0 * len(idx) / len(tail) if tail else 0))
        print('         末 12 次 = %s' % [r[2] if not mode.startswith('proc') else r[3]
                                          for r in tail[-12:]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='solo',
                    choices=['solo', 'same', 'diff', 'detect', 'proc_solo', 'proc_diff',
                             'ema_solo', 'ema_dual', 'ema_cmp',
                             'mt_solo', 'mt_dual', 'mt_cmp'])
    args = ap.parse_args()

    frames = make_frames()

    if args.mode == 'ema_cmp':
        run_ema_cmp()
        return

    if args.mode == 'mt_cmp':
        run_mt_cmp()
        return

    if args.mode.startswith('mt_'):
        ra, _ = run_mt(args.mode, frames)
        csv = os.path.join(WORK, 'mt_%s.csv' % args.mode.split('_', 1)[1])
        with open(csv, 'w', encoding='utf-8', newline='') as f:
            f.write('step,md5,px\n')
            for i, (md5, px) in enumerate(ra):
                f.write('%d,%s,%d\n' % (i, md5, px))
        print('A 命中 %d/%d' % (sum(1 for _, px in ra if px > 0), len(ra)))
        print('CSV -> %s' % csv)
        return

    if args.mode.startswith('ema_'):
        rows = run_ema(args.mode, frames)
        csv = os.path.join(WORK, 'ema_%s.csv' % args.mode.split('_', 1)[1])
        with open(csv, 'w', encoding='utf-8', newline='') as f:
            f.write('step,md5\n')
            for i, md5 in rows:
                f.write('%d,%s\n' % (i, md5))
        print('CSV -> %s' % csv)
        return

    if args.mode == 'detect':
        records = run_detect(frames)
    elif args.mode.startswith('proc'):
        records = run_proc(args.mode, frames)
    else:
        records = run_mask(args.mode, frames)
    summarize(args.mode, records)

    csv = os.path.join(WORK, 'out_%s.csv' % args.mode)
    with open(csv, 'w', encoding='utf-8') as f:
        f.write('phase,step,px,faces,rc\n')
        for tag, i, px, faces, rc in records:
            f.write('%s,%d,%d,%d,%d\n' % (tag, i, px, faces, rc))
    print('CSV -> %s' % csv)


if __name__ == '__main__':
    main()
