# async_detect_test.py —— 验证异步检测是否真的抹平「每 4 帧一次」的耗时尖峰
#
# 为什么要单独测：异步的收益不在平均值，而在**最慢那一帧**。
# 30fps 预算 33ms、60fps 预算 16.7ms —— 1080p 同步检测帧实测 18.6ms，
# 平均值只有 9.5ms 看起来很安全，但每一帧都必须过线才能不掉帧。
#
# 用法：
#   python async_detect_test.py            # 自己 fork 两个子进程跑 sync / async
#   python async_detect_test.py sync       # 只跑同步（子进程入口）
#   python async_detect_test.py async

import ctypes
import json
import os
import subprocess
import sys
import time

import numpy as np

import low_path_test as L

FRAMES = 24          # 6 个检测周期（kMaskEvery=4）
RES = '1080p'


def run_mode(mode):
    """在当前进程里跑 n 帧，返回每帧耗时 + 最终掩码诊断。"""
    os.environ['BEAUTY_ASYNC_DETECT'] = '1' if mode == 'async' else '0'
    dll = ctypes.WinDLL(L.DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_double, ctypes.c_int,
                                  ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int

    w, h = 1920, 1080
    inp = os.path.join(L.RES, RES + '.raw')
    out = os.path.join(L.OUT, '_ad_%s.raw' % mode)
    msg = ctypes.create_string_buffer(512)

    # 前 2 帧预热（建缓冲、起 worker），不计入统计
    for _ in range(2):
        dll.BeautyCoreRun(inp.encode(), out.encode(), w, h, 50.0, 0, 0.0, 0.0, 1,
                          msg, 512)

    # 计时口径：用**引擎自报的 ms=**，不是进程外的 wall clock。
    # BeautyCoreRun 每次调用要读 8MB raw、写 8MB raw，文件 I/O 约 15ms，
    # 会把信号完全盖掉（第一版就是这么测错的）。
    ms = []
    for _ in range(FRAMES):
        dll.BeautyCoreRun(inp.encode(), out.encode(), w, h, 50.0, 0, 0.0, 0.0, 1,
                          msg, 512)
        info = msg.value.decode('utf-8', 'replace')
        ms.append(float(info.split('ms=')[1].split()[0]))

    if os.path.exists(out):
        os.remove(out)
    return {'mode': mode, 'ms': ms, 'msg': msg.value.decode('utf-8', 'replace')}


def stat(ms):
    s = sorted(ms)
    n = len(s)
    return {'max': s[-1], 'p95': s[int(n * 0.95) - 1], 'median': s[n // 2],
            'mean': sum(s) / n}


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('sync', 'async'):
        print(json.dumps(run_mode(sys.argv[1])))
        return 0

    if not os.path.exists(os.path.join(L.RES, RES + '.raw')):
        print('[async] missing %s.raw' % RES)
        return 2

    here = os.path.abspath(__file__)
    res = {}
    for mode in ('sync', 'async'):
        p = subprocess.run([sys.executable, here, mode], capture_output=True,
                           text=True, cwd=os.path.dirname(here))
        if p.returncode != 0:
            print('[async] %s 子进程失败：%s' % (mode, p.stderr[-400:]))
            return 1
        res[mode] = json.loads(p.stdout.strip().splitlines()[-1])

    lines = ['# 异步检测验收（1080p，%d 帧）\n' % FRAMES,
             '> 自动生成：%s' % time.strftime('%Y-%m-%d %H:%M:%S'),
             '> 判据：异步的**最慢帧**应接近纯磨皮帧，且不再每 4 帧出现一次尖峰\n',
             '| 模式 | 中位 | 均值 | p95 | **最慢帧** | 超 16.7ms(60fps) 的帧数 |',
             '|---|---|---|---|---|---|']
    for mode in ('sync', 'async'):
        d = res[mode]
        st = stat(d['ms'])
        over = sum(1 for v in d['ms'] if v > 16.7)
        lines.append('| %s | %.2f | %.2f | %.2f | **%.2f** | %d / %d |'
                     % (mode, st['median'], st['mean'], st['p95'], st['max'],
                        over, len(d['ms'])))
    lines.append('')
    lines.append('逐帧耗时（ms）：')
    for mode in ('sync', 'async'):
        lines.append('- %s：%s' % (mode, ' '.join('%.1f' % v
                                                 for v in res[mode]['ms'])))
    lines.append('')
    lines.append('掩码诊断（最后一帧）：')
    for mode in ('sync', 'async'):
        lines.append('- %s：`%s`' % (mode, res[mode]['msg']))

    out_md = os.path.join(L.OUT, 'async_detect.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('\n'.join(lines))
    print('\n[async] -> %s' % out_md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
