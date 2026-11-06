#!/usr/bin/env python3
"""check_docs.py 0.1.0 —— 文档体系一致性自检（防腐化哨兵）

为什么需要它
------------
`check_upload.py` 管的是「上传内容干不干净」（索引 / 法务 / 隐私 / 体积），
完全不校验文档本身。治理完成后，最容易腐化的四件事是：
新增文档忘了登记 INDEX、归档件没写替代指向、改路径留下断链、命名跑偏。
本脚本把 `docs/INDEX.md` §0 的规则变成可执行的断言，作为「提交前双闸门」的第二个。

六条断言
--------
1. Active 文档头六字段齐全（版本 / 最后更新 / 适用代码版本 / 维护人 / 状态 / 替代文档）
2. 归档件首行 `ARCHIVED` + 替代指向可解析（历史待办措辞与通配路径按白名单放行）
3. `docs/INDEX.md` 与实际文件双向一致（漏登记 / 孤儿归档 / 状态标记）
4. 所有 `` `docs/....md` `` 反引号引用 0 断链
5. 命名规范：主目录 `类型-主题.md`；归档 `主题-YYYYMMDD.md`
6. 当前版数字表格（**只告警、不阻断**）；`design-cpu-performance.md` 首批保留的表格列白名单

用法
----
    python 05_验证/check_docs.py              # 全量检查
    python 05_验证/check_docs.py --staged     # 提交前模式：附列暂存区涉及的文档

退出码：0 = 无阻断项（可含告警）；1 = 存在必须修复的阻断项。
纯标准库、无第三方依赖；只读，不修改任何文件。

版本：0.1.0（新建脚本的起始版本；CPU 产品版本轴仍由 `01_源码/beauty_params.h` 单点维护）
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEAD_FIELDS = ('版本', '最后更新', '适用代码版本', '维护人', '状态', '替代文档')
MAIN_DIRS = ('docs/design', 'docs/guides', 'docs/reference', 'docs/adr')
TOP_ACTIVE = ('README.md', 'docs/CHANGELOG.md', 'docs/INDEX.md')
ARCH_DIR = 'docs/archive'

DOC_REF_RE = re.compile(r'`(docs/[A-Za-z0-9_\-/\.]+\.md)`')
ANY_MD_RE = re.compile(r'`([^`\s]+\.md)`')
MAIN_NAME_RE = re.compile(r'^(design|guide|reference|adr)-[a-z0-9\-]+\.md$')
ARCH_NAME_RE = re.compile(r'^[a-z0-9\-]+-\d{8}\.md$')
NUM_ROW_RE = re.compile(r'\d+(?:\.\d+)?\s*(?:%|ms|pp|倍)')
NUMERIC_WHITELIST = frozenset({'docs/design/design-cpu-performance.md'})


def read(rel):
    with open(os.path.join(ROOT, rel.replace('/', os.sep)), encoding='utf-8') as f:
        return f.read().replace('\r\n', '\n')


def exists(rel):
    return os.path.exists(os.path.join(ROOT, rel.replace('/', os.sep)))


def is_wild(p):
    return any(c in p for c in '*{}<>')


def index_rows(text, sec):
    """取 `## sec.` 段落内的表格数据行（跳过表头与分隔行）。"""
    lines = text.split('\n')
    start = None
    for i, line in enumerate(lines):
        if re.match(r'^## %d\. ' % sec, line):
            start = i + 1
            break
    if start is None:
        return []
    rows = []
    for line in lines[start:]:
        if line.startswith('## ') or line.strip() == '---':
            break
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 4:
            continue
        if cells[0] in ('主题', '字段', '日期', '规则', '当前版', '批次'):
            continue
        if re.match(r'^[\s\-:]+$', cells[0]):
            continue
        rows.append(cells)
    return rows


def path_of(cells):
    """表格第 2 列（路径列）里的第一个反引号内容。"""
    m = re.search(r'`([^`]+)`', cells[1])
    return m.group(1) if m else None


def collect_active():
    out = {p for p in TOP_ACTIVE if exists(p)}
    for d in MAIN_DIRS:
        full = os.path.join(ROOT, d.replace('/', os.sep))
        if not os.path.isdir(full):
            continue
        for f in os.listdir(full):
            if f.endswith('.md'):
                out.add('%s/%s' % (d, f))
    return out


def main():
    ap = argparse.ArgumentParser(description='文档体系一致性自检')
    ap.add_argument('--staged', action='store_true',
                    help='提交前模式：附列暂存区涉及的文档（断言仍为全量）')
    args = ap.parse_args()

    idx_text = read('docs/INDEX.md')
    sec1, sec2 = index_rows(idx_text, 1), index_rows(idx_text, 2)
    reg_active = [path_of(r) for r in sec1]
    reg_arch = [path_of(r) for r in sec2]
    actual_active = collect_active()
    arch_files = sorted(f for f in os.listdir(os.path.join(ROOT, 'docs', 'archive'))
                        if f.endswith('.md')) if os.path.isdir(os.path.join(ROOT, 'docs', 'archive')) else []

    print('检查目标：%s' % ('提交前（全量断言 + 暂存区清单）' if args.staged else '全量文档体系'))
    print('Active 文档：%d · 归档件：%d · INDEX 登记：%d / %d' %
          (len(actual_active), len(arch_files), len(sec1), len(sec2)))
    print()
    if args.staged:
        r = subprocess.run(['git', '-C', ROOT, 'diff', '--cached', '--name-only'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        staged = [l for l in (r.stdout or '').split('\n') if l.strip()]
        touched = [f for f in staged
                   if f.endswith('.md') or f.startswith('docs/') or f.startswith('05_验证/check_')]
        print('暂存区涉及的文档/脚本：%d 个' % len(touched))
        for f in touched:
            print('    ', f)
        print()

    problems = []

    # ---- 1. Active 文档头六字段 ----
    bad1 = []
    for p in sorted(r for r in reg_active if r and not is_wild(r)):
        if not exists(p):
            continue  # 由 [3] 报告
        head = read(p)[:1500]
        miss = [f for f in HEAD_FIELDS if ('| ' + f + ' |') not in head]
        if miss:
            bad1.append((p, miss))
    if bad1:
        print('[1] Active 文档头六字段 —— 失败')
        for p, miss in bad1:
            print('    缺字段 %s: %s' % (','.join(miss), p))
        problems.append('文档头缺失 %d 篇' % len(bad1))
    else:
        print('[1] Active 文档头六字段 —— 通过（%d/%d）' % (len(reg_active), len(reg_active)))

    # ---- 2. 归档件 ARCHIVED 头与替代指向 ----
    bad2 = []
    for f in arch_files:
        t = read('%s/%s' % (ARCH_DIR, f))
        head = t[:900]
        if not t.startswith('> **ARCHIVED'):
            bad2.append((f, '首行无 ARCHIVED 标注'))
            continue
        if not re.search(r'已废弃|ARCHIVED', head):
            bad2.append((f, '头内无废弃说明'))
        # 替代指向：只校验可解析的 docs/ 与 README.md 路径；通配与历史文件名放行
        has_target = False
        for p in ANY_MD_RE.findall(head):
            if is_wild(p):
                continue
            if p.startswith('docs/') or p == 'README.md':
                has_target = True
                if not exists(p):
                    bad2.append((f, '替代指向不存在: ' + p))
        if not has_target:
            # 「见根 README.md」等不带反引号的写法也算有指向，不误报
            if not re.search(r'见\s*根?\s*`?README', head):
                bad2.append((f, '头内无替代指向'))
    if bad2:
        print('[2] 归档件 ARCHIVED 头与替代指向 —— 失败')
        for f, why in bad2:
            print('    %s: %s' % (f, why))
        problems.append('归档头问题 %d 处' % len(bad2))
    else:
        print('[2] 归档件 ARCHIVED 头与替代指向 —— 通过（%d/%d）' % (len(arch_files), len(arch_files)))

    # ---- 3. INDEX 双向登记一致 ----
    reg_active_set = {p for p in reg_active if p and not is_wild(p)}
    reg_arch_set = {p for p in reg_arch if p and p.startswith(ARCH_DIR + '/')}
    actual_arch_set = {ARCH_DIR + '/' + f for f in arch_files}
    miss_active = sorted(actual_active - reg_active_set)
    ghost_active = sorted(p for p in reg_active_set - actual_active if not exists(p))
    miss_arch = sorted(actual_arch_set - reg_arch_set)
    ghost_arch = sorted(p for p in reg_arch_set - actual_arch_set if not exists(p))
    bad_state = [r[1] for r in sec1 if 'Active' not in r[3]] + \
                [r[1] for r in sec2 if 'Deprecated' not in r[3]]
    bad3 = miss_active + ghost_active + miss_arch + ghost_arch + bad_state
    if bad3:
        print('[3] INDEX 双向登记一致 —— 失败')
        for p in miss_active:
            print('    实际存在但 §1 未登记: %s' % p)
        for p in miss_arch:
            print('    归档件但 §2 未登记: %s' % p)
        for p in ghost_active + ghost_arch:
            print('    INDEX 登记了不存在的文件: %s' % p)
        for p in bad_state:
            print('    状态列标记不符: %s' % p)
        problems.append('INDEX 不一致 %d 项' % len(bad3))
    else:
        print('[3] INDEX 双向登记一致 —— 通过（Active %d = %d；归档 %d = %d）' %
              (len(actual_active), len(reg_active_set), len(actual_arch_set), len(reg_arch_set)))

    # ---- 4. docs/ 路径引用 0 断链 ----
    scan = ['README.md', 'docs/INDEX.md', 'docs/CHANGELOG.md']
    for d in MAIN_DIRS + (ARCH_DIR,):
        full = os.path.join(ROOT, d.replace('/', os.sep))
        if os.path.isdir(full):
            scan += ['%s/%s' % (d, f) for f in os.listdir(full) if f.endswith('.md')]
    refs = {}
    for p in scan:
        for r in DOC_REF_RE.findall(read(p)):
            refs.setdefault(r, set()).add(p)
    wild_refs = {r for r in refs if is_wild(r)}
    broken = sorted(r for r in refs if not is_wild(r) and not exists(r))
    if broken:
        print('[4] docs/ 路径引用 —— 失败（%d 条断链）' % len(broken))
        for r in broken:
            print('    MISSING %s  <- %s' % (r, ', '.join(sorted(refs[r])[:3])))
        problems.append('断链 %d 条' % len(broken))
    else:
        print('[4] docs/ 路径引用 —— 通过（%d 条，%d 条通配模板放行，0 断链）' %
              (len(refs), len(wild_refs)))

    # ---- 5. 命名规范 ----
    bad5 = []
    for d in MAIN_DIRS:
        full = os.path.join(ROOT, d.replace('/', os.sep))
        if not os.path.isdir(full):
            continue
        for f in os.listdir(full):
            if f.endswith('.md') and not MAIN_NAME_RE.match(f):
                bad5.append('%s/%s' % (d, f))
    for f in arch_files:
        if not ARCH_NAME_RE.match(f):
            bad5.append('%s/%s' % (ARCH_DIR, f))
    if bad5:
        print('[5] 命名规范 —— 失败')
        for p in bad5:
            print('    不符合规范: %s' % p)
        problems.append('命名违规 %d 个' % len(bad5))
    else:
        print('[5] 命名规范 —— 通过（主目录 %d / 归档 %d）' %
              (sum(1 for p in actual_active if p.startswith('docs/') and
                   p not in TOP_ACTIVE), len(arch_files)))

    # ---- 6. 当前版数字表格（WARN only，不阻断） ----
    warns = []
    for p in sorted(actual_active):
        if p not in NUMERIC_WHITELIST and p.startswith(('docs/design/', 'docs/guides/', 'docs/reference/')):
            for i, line in enumerate(read(p).split('\n'), 1):
                if line.startswith('|') and NUM_ROW_RE.search(line):
                    warns.append((p, i, line[:90]))
    if warns:
        print('[6] 当前版数字表格 —— %d 条告警（不阻断）' % len(warns))
        for p, i, line in warns[:20]:
            print('    %s:%d  %s' % (p, i, line))
    else:
        print('[6] 当前版数字表格 —— 通过（0 告警；白名单 %d 篇：%s）' %
              (len(NUMERIC_WHITELIST), ', '.join(sorted(NUMERIC_WHITELIST))))

    # ---- 汇总 ----
    print()
    if problems:
        print('=== 未通过：%s ===' % '；'.join(problems))
        return 1
    print('=== 全部通过：文档体系一致（%s） ===' %
          ('含 %d 条告警' % len(warns) if warns else '无告警'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
