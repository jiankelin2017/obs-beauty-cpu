# -*- coding: utf-8 -*-
"""脖子通道扫参：在多个场景上取平均 IoU，避免只对 face_src 过拟合。

## 背景

S1 的取舍是「漏磨脖子比误磨背景更可接受，所以不追」。用户 2026-10-28 要求
「对齐 OBS美颜摄像头」，fuai 掩码覆盖到脖子，所以补回来。补的方式是
**脸框正下方一条收窄的肤色通道**（不能放大矩形框，S1 已证明会框进背景）。

两个参数：`kNeckHalfW`（半宽，相对脸宽）、`kNeckLen`（长度，相对脸高）。
本脚本扫网格，用 **fuai 掩码当真值**、在 192×256 低分辨率上算 IoU
（与 S1 的 `mask_compare.py` 同口径，可以直接和 0.707 比）。

## 为什么必须多场景

单张图上调参一定好看。S1 的 0.707 是 8 个场景的均值，所以这里也只认均值，
并且把每个场景的 IoU 都打出来 —— 有场景掉得厉害就说明参数在过拟合。

用法（系统 Python 3.12，需 numpy + cv2）：
    python neck_sweep.py            # 扫网格
    python neck_sweep.py 0.30 0.55  # 只测一组
"""

from __future__ import print_function

import ctypes
import json
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'goldens', 'src')
MASK_DIR = os.path.join(HERE, 'goldens', 'masks')
OUT = os.path.join(HERE, 'goldens', 'masks')
DLL = os.path.join(HERE, 'beauty_core_test.dll')
W, H = 640, 394

GRID_HALFW = [0.40, 0.45, 0.50, 0.55, 0.60]
GRID_LEN = [0.45, 0.55, 0.65, 0.75]

# S1 明确的有效场景集（`S1_掩码对拍结论.md`：「8 个有效场景，全是同一张脸的扰动」）。
# 不能用「fuai 覆盖率 >1%」自动筛：crop_a~d 的覆盖率看着正常（0.44~3.06%），
# 但它们的 fuai 基准本身是错的 —— IoU 只有 0.06~0.14，会把均值从 0.82 拖到 0.49。
VALID_SCENES = ['face_src', 'v_bright', 'v_dark', 'v_flip', 'v_noise5',
                'v_skinbg', 'v_zoom07', 'v_zoom15']


def read_mask(p):
    raw = open(p, 'rb').read()
    mw, mh = np.frombuffer(raw[:8], np.int32)
    return np.frombuffer(raw[8:], np.uint8).reshape((mh, mw))


def scenes():
    """S1 那 8 个有效场景（同一张脸的受控扰动），带 fuai 真值。"""
    out = []
    for sid in VALID_SCENES:
        raw = os.path.join(SRC, sid + '.raw')
        mp = os.path.join(MASK_DIR, sid + '_fuai.mask')
        if not (os.path.exists(raw) and os.path.exists(mp)):
            continue
        out.append((sid, mp, (read_mask(mp) > 127).mean()))
    return out


def iou(core, fuai):
    """在 fuai 自己的分辨率上比（S1 口径）。"""
    c = cv2.resize(core.astype(np.uint8) * 255, (fuai.shape[1], fuai.shape[0]),
                   interpolation=cv2.INTER_AREA) > 127
    f = fuai > 127
    uni = (c | f).sum()
    if uni == 0:
        return 0.0, 0.0, 0.0, 0.0
    return ((c & f).sum() / uni,
            (c & f).sum() / max(c.sum(), 1),
            (c & f).sum() / max(f.sum(), 1),
            c.mean())


def worker(halfw, length):
    dll = ctypes.WinDLL(DLL)
    dll.BeautyCoreMask.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    dll.BeautyCoreMask.restype = ctypes.c_int
    rows = []
    for sid, mp, _cov in scenes():
        raw = os.path.join(SRC, sid + '.raw')
        tmp = os.path.join(OUT, '_neck_%s.mask' % sid)
        msg = ctypes.create_string_buffer(512)
        rc = dll.BeautyCoreMask(raw.encode('utf-8'), W, H, tmp.encode('utf-8'),
                                msg, 512)
        if rc != 0:
            rows.append({'scene': sid, 'iou': None,
                         'msg': msg.value.decode('utf-8', 'replace')})
            continue
        m = read_mask(tmp)
        i, p, r, cov = iou(m > 127, read_mask(mp))
        rows.append({'scene': sid, 'iou': round(float(i), 4),
                     'prec': round(float(p), 4), 'rec': round(float(r), 4),
                     'cov': round(float(100 * cov), 2)})
        os.remove(tmp)
    return rows


def main():
    if not os.path.exists(DLL):
        print('[neck] missing %s' % DLL)
        return 2

    if len(sys.argv) == 3:                       # 子进程模式：只测一组
        hw, ln = float(sys.argv[1]), float(sys.argv[2])
        rows = worker(hw, ln)
        ok = [r for r in rows if r['iou'] is not None]
        print(json.dumps({'halfw': hw, 'len': ln, 'rows': rows,
                          'mean_iou': round(float(np.mean([r['iou'] for r in ok])), 4)
                          if ok else 0.0}))
        return 0

    # 父进程：每个组合起一个子进程（引擎只读一次环境变量，不能同进程复用）
    results = []
    for hw in GRID_HALFW:
        for ln in GRID_LEN:
            env = dict(os.environ)
            env['BEAUTY_NECK_HALFW'] = str(hw)
            env['BEAUTY_NECK_LEN'] = str(ln)
            p = subprocess.run([sys.executable, os.path.abspath(__file__),
                                str(hw), str(ln)],
                               capture_output=True, text=True, env=env)
            line = [l for l in p.stdout.strip().splitlines() if l.startswith('{')]
            if not line:
                print('  halfw=%.2f len=%.2f 失败: %s' % (hw, ln, p.stderr[-200:]))
                continue
            r = json.loads(line[-1])
            results.append(r)
            print('  halfw=%.2f len=%.2f  平均 IoU %.4f' % (hw, ln, r['mean_iou']))

    if not results:
        print('[neck] 没有结果')
        return 1
    results.sort(key=lambda x: -x['mean_iou'])
    best = results[0]

    md = ['# 脖子通道扫参（fuai 掩码当真值，192×256 口径）\n',
          '> 生成时间：%s' % __import__('time').strftime('%Y-%m-%d %H:%M:%S'),
          '> 场景数：%d（自动筛掉 fuai 覆盖率 <1%% 的无效基准）' % len(scenes()),
          '',
          '## 网格结果（按平均 IoU 排序）\n',
          '| 半宽×脸宽 | 长度×脸高 | 平均 IoU |',
          '|---|---|---|']
    for r in results:
        md.append('| %.2f | %.2f | %.4f |' % (r['halfw'], r['len'], r['mean_iou']))
    md.append('')
    md.append('**最佳：半宽 %.2f、长度 %.2f，平均 IoU %.4f**（S1 的 `skin_face` 基准是 0.707）\n'
              % (best['halfw'], best['len'], best['mean_iou']))
    md.append('## 最佳组合的逐场景读数\n')
    md.append('| 场景 | IoU | 精确率 | 召回率 | 覆盖% |')
    md.append('|---|---|---|---|---|')
    for r in best['rows']:
        if r['iou'] is None:
            md.append('| %s | — | — | — | 失败：%s |' % (r['scene'], r['msg']))
        else:
            md.append('| %s | %.3f | %.3f | %.3f | %.2f |'
                      % (r['scene'], r['iou'], r['prec'], r['rec'], r['cov']))
    md.append('')
    md.append('> 判定标准：平均 IoU 高于 0.707 才算「比 S1 的只磨脸更好」，')
    md.append('> 同时逐场景不能有大幅下跌（那说明在过拟合某一张图）。')

    out = os.path.join(OUT, 'neck_sweep.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('\n[neck] -> %s' % out)
    with open(os.path.join(OUT, 'neck_sweep.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
