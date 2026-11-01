# -*- coding: utf-8 -*-
"""s3_eval.py —— surface3 单组参数评估（由 s3_fit.py 用子进程调用）。

环境变量（全部可选）：
    BEAUTY_SMOOTH_MODEL=surface3   （父进程设置）
    BEAUTY_S3_R1/IT1/R2/IT2/THR1/THR2/K/E0/ESAT/ETHR/EYEK
    （3.1.14 起 ELO 是 E0 的别名；EHI/EOFF 已废弃，不再解析）
    S3_SRC                         素材路径（默认同 cam_frame_ab.py）
输出：一行 `JSON {...}`，含 50/100 档的四区域×三频带保留率。

为什么用子进程：g_cfg 在 ensureReady 里只读一次环境变量，同进程改不了。
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cam_frame_ab as A  # noqa: E402

SRC = os.environ.get('S3_SRC', A.DEFAULT_SRC)


def main():
    import cv2
    img = cv2.imread(SRC, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit('读不出来: %s' % SRC)
    h, w = img.shape[:2]
    box, score = A.detect_face(img)
    rms = A.masks(w, h, box)
    raw = os.path.join(A.TMP, '_s3_eval_src.raw')
    base_img = A.to_rgba_raw(img, raw)
    base = A.levels(base_img, rms)

    out = {'src': os.path.basename(SRC), 'w': w, 'h': h,
           'face': [round(float(v), 1) for v in box]}
    for lvl in (50.0, 100.0):
        co, ms = A.run_core(raw, w, h, lvl,
                            os.path.join(A.TMP, '_s3_eval_core.raw'))
        lv = A.levels(co, rms)
        out[str(int(lvl))] = {
            'avg': [round(100.0 * sum(lv[n][i] / base[n][i]
                                      for n, _ in rms) / len(rms), 2)
                    for i in range(3)],
            'regions': {n: [round(100.0 * lv[n][i] / base[n][i], 2)
                            for i in range(3)] for n, _ in rms},
            'ms': round(ms, 2),
        }
    print('JSON ' + json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
