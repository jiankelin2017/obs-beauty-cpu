# -*- coding: utf-8 -*-
"""3.1.40 无脸透传 —— 新旧引擎 A/B 验证。

素材：goldens/src/face_src.raw（有脸）+ goldens/real/noface_tex.raw（无脸）。
无脸帧从真机 1080p 帧（goldens/real/_as_in.raw）右上角裁的 640x394 背景
（墙 + 画框，实测 faces=0 best=0.033）。**必须用有纹理的无脸帧**：最早用
goldens/src/noface_gray.raw（均匀灰），而平滑一张均匀图输出等于输入，
C 区「旧版全帧磨皮 vs 新版透传」根本区分不出来（两边 maxdiff 都是 0）。
序列：1 张有脸帧 + 40 张无脸帧，同一进程连续跑（引擎状态跨调用保持）。

⚠️ 坑（2026-11-01 发现，花了半小时）：探针每次 BeautyCoreRun 都调 ensureReady()
→ warmUp()，而 warmUp 会把 mask_ 撑成 1920×1080。于是 updateMask 每帧都进
「换分辨率」分支：maskAge_=999、maskValid_=false、**everHadMask_=false**。
后果：旧代码的「曾经有脸 → 人走开 → 全帧兜底」根本复现不出来（每帧都当成
「从没得到过掩码」而透传），A/B 会误判「新旧行为相同」。生产路径没这个问题
—— obs-beauty.cpp 只在滤镜加载时调一次 preheat。
解法：BEAUTY_NO_PREWARM=1 让 warmUp 提前返回，mask_ 保持真实帧尺寸。

判定：
  A. 有脸帧（第 0 帧）新旧输出必须逐字节一致（maxdiff=0）—— 修 bug 不能动有脸路径；
  B. 丢检保持期（kMaskHold=6 次丢检，同步检测每 5 帧一次 ≈ 30 帧）内
     新旧输出必须逐字节一致 —— 保持期内仍用旧掩码磨；
  C. 保持耗尽后：旧版应继续全帧磨皮（输出 != 输入、ms>0），
     新版应逐字节透传（输出 == 输入、ms=0.00、faces=0）。
"""

import ctypes
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 640, 394
NEED = W * H * 4

OLD_DLL = os.path.join(HERE, 'beauty_core_test_3139.dll')
NEW_DLL = os.path.join(HERE, 'beauty_core_test.dll')
FACE = os.path.join(HERE, 'goldens', 'src', 'face_src.raw')
NOFACE = os.path.join(HERE, 'goldens', 'real', 'noface_tex.raw')

N_NOFACE = 40
BLUR = 50.0

# 见模块 docstring 的「坑」：否则 warmUp 每帧把 mask_ 撑成 1920x1080，
# everHadMask_ 每帧被清，旧代码的全帧兜底路径复现不出来。
os.environ['BEAUTY_NO_PREWARM'] = '1'


def load(p):
    return np.fromfile(p, np.uint8)


def run_seq(dll_path, outdir):
    dll = ctypes.WinDLL(dll_path)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    frames = [FACE] + [NOFACE] * N_NOFACE
    msgs = []
    for i, fin in enumerate(frames):
        fout = os.path.join(outdir, 'out_%02d.raw' % i)
        msg = ctypes.create_string_buffer(512)
        rc = dll.BeautyCoreRun(fin.encode('utf-8'), fout.encode('utf-8'),
                               W, H, BLUR, 0, 0.0, 0.0, 1, msg, 512)
        if rc != 0:
            print('  [%s] frame %d rc=%d msg=%s' % (os.path.basename(dll_path),
                                                    i, rc, msg.value))
        msgs.append(msg.value.decode('utf-8', 'replace'))
    return msgs


def ms_of(msg):
    for tok in msg.split():
        if tok.startswith('ms='):
            try:
                return float(tok[3:])
            except ValueError:
                pass
    return -1.0


def faces_of(msg):
    for tok in msg.split():
        if tok.startswith('faces='):
            try:
                return int(tok[6:])
            except ValueError:
                pass
    return -1


def main():
    old_dir = os.path.join(HERE, '_noface_ab', 'old')
    new_dir = os.path.join(HERE, '_noface_ab', 'new')
    print('== 旧版（3.1.39 行为，beauty_core_test_3139.dll）==')
    old_msgs = run_seq(OLD_DLL, old_dir)
    print('== 新版（3.1.40，beauty_core_test.dll）==')
    new_msgs = run_seq(NEW_DLL, new_dir)

    face = load(FACE)
    noface = load(NOFACE)

    print('')
    print('帧 | 旧ms  旧faces | 新ms  新faces | 旧vs新maxdiff | 新vs输入maxdiff | 判定')
    print('---+----------------+---------------+--------------+----------------+-----')
    ok = True
    # C 区（保持耗尽）起点：旧版诊断串出现 "no face x" 的第一帧。
    # 保持期内是 "detect lost, holding mask k/6" 或上次成功的 "mask=... px"。
    c_start = None
    for i, m in enumerate(old_msgs):
        if 'no face x' in m:
            c_start = i
            break
    if c_start is None:
        print('旧版始终没出现 "no face x" —— 保持期没耗尽，加大 N_NOFACE 再跑')
        return 1
    print('（保持耗尽帧 = %d，其后进入 C 区）' % c_start)
    for i in range(1 + N_NOFACE):
        o = load(os.path.join(old_dir, 'out_%02d.raw' % i))
        n = load(os.path.join(new_dir, 'out_%02d.raw' % i))
        src = face if i == 0 else noface
        d_on = int(np.abs(o.astype(np.int16) - n.astype(np.int16)).max())
        d_ni = int(np.abs(n.astype(np.int16) - src.astype(np.int16)).max())
        if i == 0:
            verdict = 'A 有脸帧一致' if d_on == 0 else 'A 失败!!'
        elif i < c_start:
            verdict = 'B 保持期内一致' if d_on == 0 else 'B 失败!!'
        else:
            if d_on == 0:
                verdict = 'C 新旧相同(未生效?)'
                ok = False
            elif d_ni == 0:
                verdict = 'C 新版透传 OK'
            else:
                verdict = 'C 新版未透传!!'
                ok = False
        if d_on != 0 and i < c_start:
            ok = False
        print('%2d | %5.2f  %d      | %5.2f  %d      | %13d | %14d | %s'
              % (i, ms_of(old_msgs[i]), faces_of(old_msgs[i]),
                 ms_of(new_msgs[i]), faces_of(new_msgs[i]),
                 d_on, d_ni, verdict))

    print('')
    if ok:
        print('结论：A/B/C 全部通过 —— 有脸帧与丢检保持期内新旧逐字节一致，'
              '保持耗尽帧（%d）起新版透传、旧版全帧磨皮。' % c_start)
        return 0
    print('结论：存在失败项，见上表。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
