# -*- coding: utf-8 -*-
"""diff_ema.py —— 时序 EMA（CoreEngine 0.7.2）的验收驱动

跑 ema_probe.exe 的矩阵：{档位} × {static, noise, motion} × {BEAUTY_EMA=0,1}，
然后逐帧比对 hash、统计输出帧间差，给出三条判据的 PASS/FAIL。

判据：
  1) motion：EMA=0 与 EMA=1 的输出 hash **逐帧完全相同** → 运动时零拖影。
     （beta=1 时只推进历史、不改亮度平面，走的还是原来的浮点路径。）
  2) static：EMA=1 从第 2 帧起 hash 不再变化 → 历史收敛、无漂移。
  3) noise：EMA=1 的 outDiff 低于 EMA=0 → 噪点闪烁被压掉，并报出降幅。

用法：
    python diff_ema.py            # 跑完整矩阵
    python diff_ema.py quick      # 只跑默认档位
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, '_probe_run')
EXE = os.path.join(RUN, 'ema_probe.exe')
RAW = os.path.join(RUN, 'face_1280x720.raw')
MODEL = os.path.join(HERE, 'models', 'yunet.onnx')

W, H, FRAMES = 1280, 720, 8

# 档位（P_ 顺序：blur, clarity, whiten, red, sharpen, globalSharp,
#                    threed, eyebright, pouch, nasolabial, delspot）
# expect：
#   'drop' 该档位有锐化 → EMA 应该把帧间差压下去
#   'same' 该档位没有锐化 → EMA 必须完全不生效（输出逐字节不变），
#          这条是用来证明「EMA 只动锐化那一层，不污染磨皮/美白/五官」的
PROFILES = {
    'all':      ('26,28,61,30,59,76,0,0,100,97,90', 'drop'),   # 真机实测档位
    'nosharp':  ('26,28,61,30,0,0,0,0,100,97,90',   'same'),   # 去掉两档锐化
    'sharponly': ('26,0,0,0,59,76,0,0,0,0,0',       'drop'),   # 只留磨皮 + 两档锐化
}

LINE = re.compile(r'^#(\d+)\s+inDiff=\s*([\d.]+)\s+outDiff=\s*([\d.]+)\s+hash=(\w+)')


def run(profile, mode, ema, frames=FRAMES):
    env = dict(os.environ)
    env['BEAUTY_FACE_MODEL'] = MODEL
    env['BEAUTY_EMA'] = str(ema)
    env['EMA_PROFILE'] = PROFILES[profile][0]
    p = subprocess.run([EXE, RAW, str(W), str(H), mode, str(frames)],
                       cwd=RUN, env=env, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr)
        raise SystemExit('[FAIL] ema_probe returncode=%d (%s/%s/ema=%d)'
                         % (p.returncode, profile, mode, ema))
    rows = []
    for ln in p.stdout.splitlines():
        m = LINE.match(ln.strip())
        if m:
            rows.append({'k': int(m.group(1)), 'inD': float(m.group(2)),
                         'outD': float(m.group(3)), 'hash': m.group(4)})
    if len(rows) != frames:
        raise SystemExit('[FAIL] expected %d frames, got %d (%s/%s/ema=%d)'
                         % (frames, len(rows), profile, mode, ema))
    return rows


def mean_out(rows):
    tail = [r['outD'] for r in rows if r['k'] >= 2]
    return sum(tail) / len(tail) if tail else 0.0


def main():
    quick = len(sys.argv) > 1 and sys.argv[1] == 'quick'
    profiles = ['all'] if quick else list(PROFILES.keys())
    ok = True

    print('=' * 78)
    print('时序 EMA 验收 —— %dx%d，%d 帧，输入 %s' % (W, H, FRAMES, os.path.basename(RAW)))
    print('=' * 78)

    for prof in profiles:
        pstr, expect = PROFILES[prof]
        print('\n### 档位 %s = %s   (期望 %s)' % (prof, pstr, expect))

        # ---- 1) motion：逐帧 hash 必须完全相同 -------------------------
        m0 = run(prof, 'motion', 0)
        m1 = run(prof, 'motion', 1)
        diff = [a['k'] for a, b in zip(m0, m1) if a['hash'] != b['hash']]
        if diff:
            ok = False
            print('  [FAIL] motion 有拖影：第 %s 帧 hash 不一致' % diff)
            for a, b in zip(m0, m1):
                if a['hash'] != b['hash']:
                    print('     #%d  ema0=%s  ema1=%s' % (a['k'], a['hash'], b['hash']))
        else:
            print('  [PASS] motion   %d/%d 帧 hash 与 EMA=0 完全相同 → 零拖影'
                  % (len(m0), len(m0)))
        print('         输入帧间差 inDiff≈%.2f（>8.0 即判为运动，beta→1）'
              % (sum(r['inD'] for r in m0 if r['k'] >= 1) / (len(m0) - 1)))

        # ---- 2) static：EMA=1 从第 2 帧起稳定 ---------------------------
        s1 = run(prof, 'static', 1)
        tail = {r['hash'] for r in s1 if r['k'] >= 2}
        if len(tail) != 1:
            ok = False
            print('  [FAIL] static  EMA=1 输出在 %d 帧后仍在变化（%d 种 hash）'
                  % (FRAMES, len(tail)))
        else:
            print('  [PASS] static   EMA=1 第 2 帧起 hash 恒定 → 历史收敛')

        # ---- 3) noise：锐化档要求降幅，无锐化档要求逐字节不变 -------------
        n0 = run(prof, 'noise', 0)
        n1 = run(prof, 'noise', 1)
        a, b = mean_out(n0), mean_out(n1)
        if expect == 'same':
            bad = [x['k'] for x, y in zip(n0, n1) if x['hash'] != y['hash']]
            if bad:
                ok = False
                print('  [FAIL] noise    无锐化档 EMA 竟然改了输出（第 %s 帧）' % bad)
            else:
                print('  [PASS] noise    %d/%d 帧逐字节不变 → EMA 只动锐化层'
                      % (len(n0), len(n0)))
        else:
            red = (1.0 - b / a) * 100.0 if a > 0 else 0.0
            if b >= a:
                ok = False
                print('  [FAIL] noise    outDiff %.3f → %.3f 没有下降' % (a, b))
            else:
                print('  [PASS] noise    outDiff %.3f → %.3f  降幅 %.1f%%'
                      % (a, b, red))

    print('\n' + '=' * 78)
    print('总体：%s' % ('全部 PASS' if ok else '有 FAIL，见上'))
    print('=' * 78)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
