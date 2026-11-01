# -*- coding: utf-8 -*-
"""s3_fit.py —— surface3 参数扫描（对拍对象：真机 1080p 帧的 SDK 输出）。

口径与 cam_frame_ab.py 完全一致：四区域（额头/鼻翼/唇/脸颊）× 三频带
（细 |Y-box3| / 中 |box3-box7| / 阴影 |box7-box21|）的保留率，取四区域平均。

SDK 目标值来自 cam_frame_ab.py 在
    clipboard-2026-10-28T17-27-00-131Z-a93b903c.jpg
上的实跑（legacy 基线与 checkpoint 记录逐位一致）：
    50  档：细 76.1  中 80.7  阴 95.7
    100 档：细 65.1  中 62.5  阴 78.6

评分 = 0.5·|细差| + 0.3·|中差| + 0.2·|阴差|，两档取平均。
用法：
    python s3_fit.py              # 默认网格
    python s3_fit.py quick        # 小网格先看方向
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
EVAL = os.path.join(HERE, 's3_eval.py')

SDK = {50: (76.1, 80.7, 95.7), 100: (65.1, 62.5, 78.6)}
W = (0.5, 0.3, 0.2)


def run(cfg):
    env = dict(os.environ)
    env['BEAUTY_SMOOTH_MODEL'] = 'surface3'
    env['PYTHONIOENCODING'] = 'utf-8'
    for k, v in cfg.items():
        env[k] = str(v)
    p = subprocess.run([PY, EVAL], cwd=HERE, env=env,
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    for line in p.stdout.splitlines():
        if line.startswith('JSON '):
            return json.loads(line[5:])
    raise RuntimeError('no JSON (rc=%s)\n%s\n%s'
                       % (p.returncode, p.stdout[-2000:], p.stderr[-2000:]))


def score(res):
    s = 0.0
    detail = {}
    for lvl in (50, 100):
        got = res[str(lvl)]['avg']
        tgt = SDK[lvl]
        d = [got[i] - tgt[i] for i in range(3)]
        s += sum(W[i] * abs(d[i]) for i in range(3)) / 2.0
        detail[lvl] = d
    return s, detail


def main():
    quick = len(sys.argv) > 1 and sys.argv[1] == 'quick'
    grid = []
    thr1s = [1.5, 2.5, 3.5] if quick else [1.0, 2.0, 3.0, 4.0, 6.0]
    thr2s = [2.0, 4.0, 6.0] if quick else [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0]
    r2s = [8] if quick else [6, 8, 12]
    for t1 in thr1s:
        for t2 in thr2s:
            for r2 in r2s:
                grid.append({'BEAUTY_S3_R1': 2, 'BEAUTY_S3_IT1': 2,
                             'BEAUTY_S3_R2': r2, 'BEAUTY_S3_IT2': 2,
                             'BEAUTY_S3_THR1': t1, 'BEAUTY_S3_THR2': t2})

    rows = []
    for i, cfg in enumerate(grid):
        try:
            res = run(cfg)
        except Exception as e:  # noqa: BLE001
            print('[%d/%d] FAIL %s: %s' % (i + 1, len(grid), cfg, e))
            continue
        s, d = score(res)
        rows.append((s, cfg, d, res))
        print('[%d/%d] r2=%-2d thr1=%-4g thr2=%-4g  score=%6.2f  '
              '50(%+.1f %+.1f %+.1f) 100(%+.1f %+.1f %+.1f)  %sms'
              % (i + 1, len(grid), cfg['BEAUTY_S3_R2'],
                 cfg['BEAUTY_S3_THR1'], cfg['BEAUTY_S3_THR2'], s,
                 *d[50], *d[100], res['100']['ms']))

    rows.sort(key=lambda r: r[0])
    print('\n=== top 8 ===')
    for s, cfg, d, res in rows[:8]:
        print('score=%6.2f  r2=%-2d thr1=%-4g thr2=%-4g  '
              '50=%s  100=%s'
              % (s, cfg['BEAUTY_S3_R2'], cfg['BEAUTY_S3_THR1'],
                 cfg['BEAUTY_S3_THR2'],
                 res['50']['avg'], res['100']['avg']))
    if rows:
        with open(os.path.join(HERE, 's3_fit_last.json'), 'w',
                  encoding='utf-8') as f:
            json.dump([{'score': s, 'cfg': c, 'delta': d, 'res': r}
                       for s, c, d, r in rows], f, ensure_ascii=False, indent=1)
        print('\n写入 s3_fit_last.json（%d 组）' % len(rows))


if __name__ == '__main__':
    main()
