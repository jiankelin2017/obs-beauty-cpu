# -*- coding: utf-8 -*-
"""用当前 DLL 在 1074x604 素材上按原协议复跑模式 0/1，验证效果是否仍在。"""
import os, subprocess, sys
HERE = r'C:\nama_e2e'
sys.path.insert(0, HERE)
import sweep_mode as sm
DLL = os.path.join(HERE, 'nama_engine_test_317.dll')
for tag, mode in (('rc_m0', 0), ('rc_m1', 1)):
    p = os.path.join(HERE, 'extra_%s.txt' % tag)
    open(p, 'w').write('')
    env = dict(os.environ)
    env['NAMA_EXTRA_PARAMS_FILE'] = p
    env['NAMA_SMOOTH_MODE'] = str(mode)
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import nz_probe_dlldir as nz; nz.run(r'%s', '%s', '0:50,4:50')"
            % (HERE, DLL, tag))
    r = subprocess.run([sys.executable, '-c', code], env=env, cwd=HERE,
                       capture_output=True, text=True, timeout=600)
    print(tag, 'rc=%d' % r.returncode, r.stdout.strip()[-80:], r.stderr[-150:])
base = sm.measure('rc_m0'); cur = sm.measure('rc_m1')
if base and cur:
    print('m0 平坦 %.3f 边缘 %.3f 细节 %.3f 闪动 %.3f' % (base['flatHi'], base['edgeC'], base['detail'], base['flick']))
    print('m1 平坦 %.3f 边缘 %.3f 细节 %.3f 闪动 %.3f' % (cur['flatHi'], cur['edgeC'], cur['detail'], cur['flick']))
    print('变化 平坦 %+.2f%% 边缘 %+.2f%% 细节 %+.2f%% 闪动 %+.2f%%' % (
        (cur['flatHi']/base['flatHi']-1)*100, (cur['edgeC']/base['edgeC']-1)*100,
        (cur['detail']/base['detail']-1)*100, (cur['flick']/base['flick']-1)*100))
