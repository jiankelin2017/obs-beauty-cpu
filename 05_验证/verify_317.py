# -*- coding: utf-8 -*-
"""3.0.17 最终验证：四档磨皮模式 × 关键参数组合。"""
import os
import re
import subprocess
import sys

HERE = r'C:\legacy_e2e'
sys.path.insert(0, HERE)
import sweep_mode as sm  # noqa: E402

DLL = os.path.join(HERE, 'legacy_engine_test_317.dll')

GROUPS = [
    ('v317_m0_blur50', '0:50,4:50', 0),
    ('v317_m1_blur50', '0:50,4:50', 1),
    ('v317_m2_blur50', '0:50,4:50', 2),
    ('v317_m3_blur50', '0:50,4:50', 3),
    ('v317_m1_blur80', '0:80,4:50', 1),
    ('v317_m1_cl60',   '0:50,1:60,4:50', 1),
]


def run(tag, panel, mode):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write('')
    env = dict(os.environ)
    env['BEAUTY_EXTRA_PARAMS_FILE'] = p
    env['BEAUTY_SMOOTH_MODE'] = str(mode)
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import nz_probe_dlldir as nz; nz.run(r'%s', '%s', '%s')"
            % (HERE, DLL, tag, panel))
    r = subprocess.run([sys.executable, '-c', code], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0
    ms = ''
    m = re.search(r'proc=([\d.]+)', r.stdout or '')
    if not m:
        m = re.search(r'([\d.]+)ms', r.stdout or '')
    if m:
        ms = m.group(1)
    print('  %-16s %s  %s' % (tag, 'OK' if ok else 'FAIL', ('proc=%sms' % ms) if ms else ''))
    return ok


def main():
    open(os.path.join(HERE, 'flick', 'nz_in', 'meta.txt'), 'w').write('5 10')
    done = []
    for tag, panel, mode in GROUPS:
        if run(tag, panel, mode):
            done.append(tag)

    rows = [r for r in (sm.measure(t) for t in done) if r]
    base = next((r for r in rows if r['tag'] == 'v317_m0_blur50'), None)
    hdr = ('%-17s %-9s %-9s %-9s %-9s %-9s %-8s'
           % ('组', '平坦高频', '边缘对比', '总细节', '闪动', '背景', '帧耗时ms'))
    print('\n=== 指标 ===')
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print('%-17s %-9.3f %-9.3f %-9.3f %-9.3f %-9.4f'
              % (r['tag'], r['flatHi'], r['edgeC'], r['detail'],
                 r['flick'], r['bg']))

    if base:
        print('\n=== 相对「人像磨皮」的变化 ===')
        for r in rows:
            if r['tag'] == base['tag']:
                continue
            print('%-17s 平坦 %+6.2f%%  边缘 %+6.2f%%  细节 %+6.2f%%  闪动 %+6.2f%%'
                  % (r['tag'],
                     (r['flatHi'] / base['flatHi'] - 1) * 100,
                     (r['edgeC'] / base['edgeC'] - 1) * 100,
                     (r['detail'] / base['detail'] - 1) * 100,
                     (r['flick'] / base['flick'] - 1) * 100))
    open(os.path.join(HERE, 'flick', 'nz_in', 'meta.txt'), 'w').write('5 60')


if __name__ == '__main__':
    main()
