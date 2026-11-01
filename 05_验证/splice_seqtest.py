# -*- coding: utf-8 -*-
"""从 _bak_317 备份里把 LegacySeqTest 函数体摘出来，拼回新同步的测试副本。

sync_test_copy.py 的锚点（// 测试专用：多帧序列驱动）在 3.0.16 的副本里
已经不存在了，所以它没能自动搬运 —— 这里按函数名边界直接切。
"""
import io
import os

HERE = r'C:\legacy_e2e'
BAK = os.path.join(HERE, '_bak_317', 'legacy_engine.cpp')
CUR = os.path.join(HERE, 'legacy_engine.cpp')

bak = io.open(BAK, encoding='utf-8').read()
cur = io.open(CUR, encoding='utf-8').read()

if 'LegacySeqTest' in cur:
    print('当前副本已含 LegacySeqTest，无需处理')
    raise SystemExit(0)

i = bak.find('int __stdcall LegacySeqTest')
if i < 0:
    raise SystemExit('备份里也找不到 LegacySeqTest')
# 往前吃掉紧邻的注释行 / 空行，让函数带上下文
head = bak.rfind('\n\n', 0, i)
start = head + 2 if head > 0 else i
# 结束：extern "C" 收尾之前
j = bak.find('}  // extern "C"', i)
if j < 0:
    j = bak.rfind('}  // extern "C"')
if j < 0:
    raise SystemExit('备份里找不到 extern "C" 收尾')
seq = bak[start:j].rstrip('\n')

k = cur.rfind('}  // extern "C"')
if k < 0:
    raise SystemExit('当前副本找不到 extern "C" 收尾')
new = cur[:k].rstrip('\n') + '\n\n' + seq + '\n\n' + cur[k:]
io.open(CUR, 'w', encoding='utf-8', newline='').write(new)
print('已拼接 LegacySeqTest：%d 字节' % len(seq))
print(new[new.rfind('int __stdcall LegacySeqTest') - 120:][:300])
