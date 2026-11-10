# -*- coding: utf-8 -*-
"""ab_tone_fusion.py —— BEAUTY_TONE_FUSION=0/1 逐字节 A/B 对拍。

目的：证明「把三段色调并入 surface3RgbBand 合成段」没有拿画质换性能。
做法：同一份 beauty_core_test.dll，在**两个独立子进程**里分别注入开关
（静态局部变量只读一次环境变量，必须进程启动前设好），跑完全相同的
调用序列，逐个比输出 raw 的每一个字节。

任何一组不等价即判 FAIL，该优化必须回退。

覆盖：
  default   —— 整帧色调（默认），三档分辨率 × 单线程全帧/自动线程ROI × 两组档位
  rollback  —— BEAUTY_TONE_GLOBAL=0 回退模式，验证 roi + mask 选区一致
  legacy    —— BEAUTY_CLARITY_LEGACY=1，fusion 应完全不生效
  tone0     —— 三项色调全 0，验证早退路径

用法：python ab_tone_fusion.py
"""

import ctypes
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, 'beauty_core_test.dll')
RES = os.path.join(HERE, 'goldens', 'res')
OUT = os.path.join(HERE, 'goldens', 'masks', '_fusion')

SIZES = [('640x394', 640, 394), ('720p', 1280, 720), ('1080p', 1920, 1080)]
# (tag, threads, useRoi)
PERFS = [('full_1t', 1, 0), ('roi_auto', 0, 1)]
# (tag, whiten, red, clarity, blur)
TONES = [('toneA', 45.0, 20.0, 30.0, 50.0),
         ('toneB', 100.0, 60.0, 0.0, 85.0)]


def build_cases():
    groups = {}

    default = []
    for name, w, h in SIZES:
        raw = os.path.join(RES, name + '.raw')
        for ptag, th, roi in PERFS:
            for ttag, wh, rd, cl, blur in TONES:
                default.append(dict(tag='%s_%s_%s' % (name, ptag, ttag),
                                    raw=raw, w=w, h=h, threads=th, roi=roi,
                                    whiten=wh, red=rd, clarity=cl, blur=blur))
    groups['default'] = dict(env={}, cases=default)

    rollback = []
    for name, w, h in SIZES:
        rollback.append(dict(tag='%s_roi_auto_toneA' % name,
                             raw=os.path.join(RES, name + '.raw'),
                             w=w, h=h, threads=0, roi=1,
                             whiten=45.0, red=20.0, clarity=30.0, blur=50.0))
    groups['rollback'] = dict(env={'BEAUTY_TONE_GLOBAL': '0'}, cases=rollback)

    groups['legacy'] = dict(
        env={'BEAUTY_CLARITY_LEGACY': '1'},
        cases=[dict(tag='720p_legacy_toneA', raw=os.path.join(RES, '720p.raw'),
                    w=1280, h=720, threads=1, roi=0,
                    whiten=45.0, red=20.0, clarity=30.0, blur=50.0)])

    groups['tone0'] = dict(
        env={},
        cases=[dict(tag='720p_tone0', raw=os.path.join(RES, '720p.raw'),
                    w=1280, h=720, threads=1, roi=0,
                    whiten=0.0, red=0.0, clarity=0.0, blur=50.0)])
    return groups


def child_main(fusion, group, cases):
    """在已注入环境变量的子进程里跑完所有 case，结果写 JSON 文件。"""
    os.makedirs(OUT, exist_ok=True)
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreRun.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                  ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreRun.restype = ctypes.c_int
    dll.BeautyCoreSetPerf.argtypes = [ctypes.c_int, ctypes.c_int]
    dll.BeautyCoreSetPerf.restype = None
    dll.BeautyCoreSetTone.argtypes = [ctypes.c_double, ctypes.c_double]
    dll.BeautyCoreSetTone.restype = None
    dll.BeautyCoreSetClarityPanel.argtypes = [ctypes.c_double]
    dll.BeautyCoreSetClarityPanel.restype = None

    results = {}
    for c in cases:
        tag = c['tag']
        outp = os.path.join(OUT, 'ab_%s_f%s_%s.raw' % (group, fusion, tag))
        dll.BeautyCoreSetTone(c['whiten'], c['red'])
        dll.BeautyCoreSetClarityPanel(c['clarity'])
        dll.BeautyCoreSetPerf(c['threads'], c['roi'])
        msg = ctypes.create_string_buffer(512)
        rc = 0
        # 同步路径每 4 帧重算掩码，预热 5 次让两组调用序列完全对齐
        for _ in range(6):
            rc = dll.BeautyCoreRun(c['raw'].encode('utf-8'),
                                   outp.encode('utf-8'),
                                   c['w'], c['h'], c['blur'], 0,
                                   0.0, 0.0, 1, msg, 512)
        results[tag] = dict(path=outp, rc=int(rc),
                            sha=hashlib.sha256(open(outp, 'rb').read()).hexdigest()[:16],
                            msg=msg.value.decode('utf-8', 'replace'))
    with open(os.path.join(OUT, 'result_%s_f%s.json' % (group, fusion)),
              'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)


def parent_main():
    groups = build_cases()
    all_ok = True
    total = 0
    for gname, g in groups.items():
        payloads = {}
        for fusion in (0, 1):
            env = os.environ.copy()
            env['BEAUTY_TONE_FUSION'] = str(fusion)
            env['BEAUTY_ASYNC_DETECT'] = '0'
            env.update(g['env'])
            cmd = [sys.executable, os.path.abspath(__file__), '--child',
                   str(fusion), gname, json.dumps(g['cases'])]
            r = subprocess.run(cmd, env=env, capture_output=True,
                               text=True, timeout=900)
            if r.returncode != 0:
                print('[AB] child %s f=%d FAILED rc=%d' % (gname, fusion, r.returncode))
                print((r.stdout or '')[-1500:])
                print((r.stderr or '')[-1500:])
                return 2
            with open(os.path.join(OUT, 'result_%s_f%d.json' % (gname, fusion)),
                      encoding='utf-8') as fh:
                payloads[fusion] = json.load(fh)

        print('=== GROUP %s  env=%s  cases=%d ===' %
              (gname, g['env'] or '(default)', len(g['cases'])))
        for tag, a in payloads[0].items():
            b = payloads[1].get(tag)
            total += 1
            if not b:
                print('  %-34s MISSING_IN_FUSION' % tag)
                all_ok = False
                continue
            if a['rc'] != 0 or b['rc'] != 0:
                print('  %-34s RC f0=%d f1=%d' % (tag, a['rc'], b['rc']))
                all_ok = False
                continue
            da = np.fromfile(a['path'], np.uint8)
            db = np.fromfile(b['path'], np.uint8)
            ok = np.array_equal(da, db)
            diff = 0 if ok else int(np.abs(da.astype(np.int16) -
                                           db.astype(np.int16)).max())
            ndiff = 0 if ok else int(np.count_nonzero(da != db))
            print('  %-34s %s  maxdiff=%d  ndiff=%d  sha=%s' %
                  (tag, 'PASS' if ok else 'FAIL', diff, ndiff, a['sha']))
            if not ok:
                all_ok = False
    print('[AB] %d cases -> %s' % (total, 'ALL PASS' if all_ok else 'FAILED'))
    return 0 if all_ok else 1


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--child':
        child_main(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
    else:
        sys.exit(parent_main())
