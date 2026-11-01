# -*- coding: utf-8 -*-
"""一次性迁移脚本：把源码里的第三方标识符全部换成自有命名。

执行顺序（长串在前，避免部分替换）：
  1) 头/源文件名与 include
  2) 类型/类名（BeautySettings 单独处理 → BeautySettings）
  3) 宏与环境变量（NAMA_* → BEAUTY_*）
  4) 函数名（legacy_log_* → beauty_log_*）
  5) 残余的 legacy_ → legacy_

跑完打印每个文件被改了多少处，便于核对。
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # D:\插件\OBS美颜
DIRS = [os.path.join(ROOT, '00_源码'), os.path.join(ROOT, '01_构建'),
        os.path.join(ROOT, '06_离线验证')]
EXTS = ('.cpp', '.h', '.bat', '.py')

EXPLICIT = [
    # ---- 文件 / include ----
    ('legacy_engine.h', 'legacy_engine.h'),
    ('legacy_engine.cpp', 'legacy_engine.cpp'),
    ('legacy_region.h', 'legacy_region.h'),
    ('legacy_region.cpp', 'legacy_region.cpp'),
    ('beauty_log.h', 'beauty_log.h'),
    ('beauty_log.cpp', 'beauty_log.cpp'),
    ('ref_golden.dll', 'ref_golden.dll'),
    ('ref_golden', 'ref_golden'),
    ('obs-beauty-ui', 'obs-beauty-ui'),
    ('legacy_engine_test', 'legacy_engine_test'),
    ('RefGoldenRun', 'RefGoldenRun'),
    ('RefGoldenRelease', 'RefGoldenRelease'),
    # ---- 类型 ----
    ('BeautySettings', 'BeautySettings'),
    ('LegacyEngine', 'LegacyEngine'),
    ('LegacyAdapter', 'LegacyAdapter'),
    ('LegacyRegion', 'LegacyRegion'),
    # ---- 日志函数 ----
    ('beauty_set_log_fn', 'beauty_set_log_fn'),
    ('beauty_log_info', 'beauty_log_info'),
    ('beauty_log_error', 'beauty_log_error'),
    ('beauty_log_warning', 'beauty_log_warning'),
    ('beauty_log_debug', 'beauty_log_debug'),
    ('beauty_logv', 'beauty_logv'),
    ('beauty_log_fn', 'beauty_log_fn'),
]


def scan(path):
    try:
        return io.open(path, encoding='utf-8').read()
    except UnicodeDecodeError:
        return None


def main():
    total = 0
    for d in DIRS:
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if not os.path.isfile(p) or not name.endswith(EXTS):
                continue
            s = scan(p)
            if s is None:
                print('SKIP (not utf-8): %s' % p)
                continue
            orig = s
            for a, b in EXPLICIT:
                s = s.replace(a, b)
            # 剩余 CamelCase 的 LegacyXxx → LegacyXxx
            s = re.sub(r'\bNama([A-Z]\w*)', r'Legacy\1', s)
            # 宏 / 环境变量
            s = re.sub(r'\bNAMA_([A-Z_]+)', r'BEAUTY_\1', s)
            # 残余小写标识符
            s = re.sub(r'\bnama_', 'legacy_', s)
            if s != orig:
                io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
                n = sum(1 for a, b in zip(orig.split('\n'), s.split('\n')) if a != b)
                total += 1
                print('%-46s %d 行改动' % (name, n))
    print('---- 共修改 %d 个文件' % total)

    # 文件重命名
    src = DIRS[0]
    pairs = [('legacy_engine.h', 'legacy_engine.h'),
             ('legacy_engine.cpp', 'legacy_engine.cpp'),
             ('legacy_region.h', 'legacy_region.h'),
             ('legacy_region.cpp', 'legacy_region.cpp'),
             ('beauty_log.h', 'beauty_log.h'),
             ('beauty_log.cpp', 'beauty_log.cpp')]
    for a, b in pairs:
        pa, pb = os.path.join(src, a), os.path.join(src, b)
        if os.path.exists(pa):
            if os.path.exists(pb):
                print('!! 目标已存在，跳过: %s' % b)
            else:
                os.rename(pa, pb)
                print('renamed %s -> %s' % (a, b))
    return 0


if __name__ == '__main__':
    sys.exit(main())
