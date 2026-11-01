# -*- coding: utf-8 -*-
"""参数 key 发现扫描。

对每个候选 key 单独注入 key=1.0，与基线逐像素比对：
  mean|dY| 全画面   > 1e-3  => 该 key 被 SDK 接受且生效
任何 key 让进程崩溃 => 记为 CRASH（同样是"SDK 认识这个 key"的证据）

帧数临时降到 6 帧以提速；结束后恢复。
结果增量写入 kd_results.csv，可中断续跑。
"""
import os
import subprocess
import sys
import csv
import time

import numpy as np

HERE = r'C:\legacy_e2e'
sys.path.insert(0, HERE)
import nz_probe_dlldir as nz  # noqa: E402

DLL = os.path.join(HERE, 'legacy_engine_test_316.dll')
PANEL = '0:50,4:50'          # 磨皮50 + 锐化50，让所有皮肤相关参数有可作用的基底
W, H = 1074, 604
META = os.path.join(HERE, 'flick', 'nz_in', 'meta.txt')
RESULT = os.path.join(HERE, 'kd_results.csv')
PYEXE = sys.executable


def set_frames(n):
    open(META, 'w').write('5 %d' % n)


def y_of(path):
    a = np.frombuffer(open(path, 'rb').read(), dtype=np.uint8).reshape(H, W, 4)
    return (a[:, :, 0].astype(np.float32) * 299 +
            a[:, :, 1].astype(np.float32) * 587 +
            a[:, :, 2].astype(np.float32) * 114) / 1000.0


def out_frame(tag, idx=-1):
    d = os.path.join(HERE, 'flick', 'nz_%s_out' % tag)
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.endswith('.raw'))
    if not files:
        return None
    return y_of(os.path.join(d, files[idx]))


def run(tag, extra):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write(extra)
    env = dict(os.environ)
    env['BEAUTY_EXTRA_PARAMS_FILE'] = p
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import nz_probe_dlldir as nz; "
            "nz.run(r'%s', '%s', '%s')" % (HERE, DLL, tag, PANEL))
    try:
        r = subprocess.run([PYEXE, '-c', code], env=env, cwd=HERE,
                           capture_output=True, text=True, timeout=120)
        return r.returncode
    except subprocess.TimeoutExpired:
        return -9


def main():
    keys = [l.strip() for l in open(os.path.join(HERE, 'kd_keys.txt'))
            if l.strip()]
    set_frames(6)
    done = {}
    if os.path.exists(RESULT):
        for row in csv.reader(open(RESULT)):
            if len(row) >= 4:
                done[row[0]] = row

    print('=== 基线 ===')
    run('kd_base', '')
    base = out_frame('kd_base')
    if base is None:
        print('基线失败，退出')
        return 1
    print('基线帧 OK')

    fh = open(RESULT, 'a', newline='')
    w = csv.writer(fh)
    if not done:
        w.writerow(['key', 'diff', 'status', 'tag'])

    active = []
    t0 = time.time()
    for i, key in enumerate(keys):
        if key in done:
            if done[key][2] == 'ACTIVE':
                active.append((key, float(done[key][1])))
            continue
        tag = 'kd%03d' % i
        rc = run(tag, '%s=1.0' % key)
        if rc != 0:
            fh.write('%s,0,CRASH,%s\n' % (key, tag))
            fh.flush()
            print('  [%3d/%3d] %-34s CRASH(rc=%s)' % (i + 1, len(keys), key, rc))
            continue
        im = out_frame(tag)
        if im is None:
            fh.write('%s,0,NOOUT,%s\n' % (key, tag))
            fh.flush()
            print('  [%3d/%3d] %-34s NOOUT' % (i + 1, len(keys), key))
            continue
        d = float(np.abs(im - base).mean())
        st = 'ACTIVE' if d > 1e-3 else 'noop'
        fh.write('%s,%.6f,%s,%s\n' % (key, d, st, tag))
        fh.flush()
        if st == 'ACTIVE':
            active.append((key, d))
            print('  [%3d/%3d] %-34s ACTIVE  %.4f  <<<' % (i + 1, len(keys), key, d))
        else:
            print('  [%3d/%3d] %-34s noop    %.6f' % (i + 1, len(keys), key, d))

    fh.close()
    set_frames(60)
    print('\n=== 汇总：生效的 key（按影响降序）===')
    for k, d in sorted(active, key=lambda x: -x[1]):
        print('  %-36s %.4f' % (k, d))
    print('耗时 %.1f 分钟' % ((time.time() - t0) / 60))
    return 0


if __name__ == '__main__':
    sys.exit(main())
