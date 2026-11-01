# -*- coding: utf-8 -*-
"""多帧验收：对 raw2/*.png 逐帧跑「产品金标(加密 bundle, bt=-1) + 掩码(明文 bundle) + 自研引擎」。
输出逐帧指标表与 CSV。
"""
import os, re, subprocess, sys, glob, json, csv

HERE = r'D:\插件\OBS美颜\06_离线验证'
OUT = r'C:\btwork\live_check'
PY = sys.executable
TAGS = [(p, 'm%02d' % i) for i, p in enumerate(sorted(glob.glob(os.path.join(OUT, 'raw2', 'raw_*.png'))))]
W, H = 1920, 1080
CORE_ARGS = ['--model', 'surface3', '--band', '1', '--bt', '8.3', '--gold-bt', '-1']


def run(args, env=None):
    e = os.environ.copy()
    e.update(env or {})
    p = subprocess.run(args, cwd=HERE, env=e, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def num(pat, txt, cast=float, default=None):
    m = re.search(pat, txt)
    return cast(m.group(1)) if m else default


rows = []
for png, tag in TAGS:
    print('=' * 70)
    print(tag, os.path.basename(png))
    # 1) 金标（加密 bundle）
    rc, out = run([PY, 'real_frame_eval.py', '--png', png, '--w', str(W), '--h', str(H),
                   '--tag', tag, '--mk', '--gold-bt', '-1'], {'GOLDEN_ENGINE_DIR': r'C:\btwork\engine'})
    faces = num(r'faces=(\d+)', out, int, 0)
    cov = num(r'coverage=([\d.]+)', out, float, 0.0)
    print('  金标 faces=%d coverage=%.4f' % (faces, cov))
    if not os.path.exists(os.path.join(HERE, 'goldens', 'real', '%s_gold_btM1.raw' % tag)):
        print('  !! 金标缺失，跳过');  continue
    # 2) 掩码（明文 bundle）
    rc, out2 = run([PY, 'mk_mask.py', '--engine', r'C:\btwork_plain\engine',
                    '--raw', os.path.join(HERE, 'goldens', 'real', '%s_in.raw' % tag),
                    '--out', os.path.join(HERE, 'goldens', 'real', '%s_fuai.mask' % tag),
                    '--w', str(W), '--h', str(H)])
    print('  掩码', out2.strip().splitlines()[-1][:90] if out2.strip() else 'rc=%d' % rc)
    # 3) 对拍
    rc, out3 = run([PY, 'real_frame_eval.py', '--tag', tag, '--w', str(W), '--h', str(H)] + CORE_ARGS)
    if rc != 0:
        print('  对拍失败 rc=%d\n%s' % (rc, out3[-500:]))
        continue
    m = {
        'tag': tag,
        'faces': faces, 'coverage': cov,
        'rmse_mask': num(r'肤色掩码内\s+([\d.]+)', out3),
        'chg_mask': [float(x) for x in re.findall(r'肤色掩码内\s+[\d.]+\s+([\d.]+)', out3)][:1],
        'sdk_chg': num(r'SDK 改动量\s*:\s*([\d.]+)', out3),
        'our_chg': num(r'我们改动量\s*:\s*([\d.]+)', out3),
        'corr': num(r'空间相关\s*:\s*([\d.]+)', out3),
    }
    m['chg_mask'] = m['chg_mask'][0] if m['chg_mask'] else None
    m['ratio'] = (m['our_chg'] / m['sdk_chg']) if m['sdk_chg'] else None
    print('  RMSE=%.3f 我们改动=%.3f SDK改动=%.3f 比=%.3f 相关=%.3f'
          % (m['rmse_mask'], m['our_chg'], m['sdk_chg'], m['ratio'], m['corr']))
    rows.append(m)

if rows:
    csvp = os.path.join(OUT, 'multi_frame.csv')
    with open(csvp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    def avg(k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return sum(v) / len(v) if v else float('nan')
    print('\n===== 汇总 %d 帧 =====' % len(rows))
    print('RMSE 均值 %.3f | 我们 %.3f | SDK %.3f | 比 %.3f | 相关 %.3f'
          % (avg('rmse_mask'), avg('our_chg'), avg('sdk_chg'), avg('ratio'), avg('corr')))
    print('CSV ->', csvp)
