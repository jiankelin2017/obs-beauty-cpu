#!/usr/bin/env python3
"""check_docs.py 0.3.1.2 —— 文档体系一致性自检（防腐化哨兵）

为什么需要它
------------
`check_upload.py` 管的是「上传内容干不干净」（索引 / 闭源资产 / 体积），
完全不校验文档本身。治理完成后，最容易腐化的事是：新增文档忘了登记 INDEX、
归档件没写替代指向、改路径留下断链、命名跑偏、升版本漏改头表、验证报告被删了引用还留着。
本脚本把 `docs/INDEX.md` §0 的规则变成可执行的断言，作为「提交前双闸门」的第二个。

九条断言
--------
1. Active 文档头六字段齐全（版本 / 最后更新 / 适用代码版本 / 维护人 / 状态 / 替代文档）
2. `docs/archive/` 下 38 篇归档件须有首行 `ARCHIVED` 标注与替代指向（2026-11-10 重建归档目录后恢复本断言）
3. `docs/INDEX.md` 与实际文件双向一致（漏登记 / 孤儿归档 / 状态标记；§1 管 Active，§2 管归档 38 行）
4. 所有 `` `docs/....md` `` 反引号引用 0 断链
5. 命名规范：主目录 `类型-主题.md`；归档 `主题-YYYYMMDD.md`
6. 当前版数字表格（**只告警、不阻断**）；0.1.1 起白名单清空，全部 design/guides/reference 纳入扫描
7. **版本轴一致性**：当前版唯一取自 `01_源码/beauty_params.h` 的 `BEAUTY_BUILD_STR`；
   Active 文档头表「版本 / 适用代码版本」须与之相同。按定义记「最后内容复核版本」的
   设计取证快照允许落后，但必须逐条登记在 `VERSION_AXIS_EXEMPT` 并写明理由，
   且该文档正文须含时效声明 —— 没有登记的落后版本一律阻断。
8. **`05_验证/` 引用 0 断链**：递归收集 `05_验证/**/*.md`，校验 Active 文档的路径引用、
   `05_验证/INDEX.md` 表格登记，以及 38 篇归档件里的历史引用。归档件正文按治理约束不改写，
   因此其中的失效取证路径须逐条登记在 `VERIFY_ARCHIVE_EXEMPT` 并写明理由与复核期限。
9. **总表「适用版本」列一致性**：`docs/INDEX.md` §1 的「适用版本」列须与当前版
   `BEAUTY_BUILD_STR` 相同；按 §1 定义记「最后一次内容复核版本」的设计取证快照允许落后，
   但必须登记在 `INDEX_AXIS_EXEMPT` 并写明理由，且正文须含时效声明。

例外表是**显性化**而非放行：每条都要写理由，脚本把用到的例外逐条打印；
已失效的例外（文档已跟升、文件已恢复、条目已不在 Active 集合）会提示移除，避免白名单堆积。

用法
----
    python 05_验证/check_docs.py              # 全量检查
    python 05_验证/check_docs.py --staged     # 提交前模式：附列暂存区涉及的文档 + 分叉提示

退出码：0 = 无阻断项（可含告警与已登记例外）；1 = 存在必须修复的阻断项。
纯标准库、无对照实现依赖；只读，不修改任何文件。

版本：0.3.1.3（2026-11-10 清理批：同步 `check_upload.py` 断言由五道减为三道的描述，
   **九条断言逻辑未变**，按四段式规则升构建位；此前 0.3.1.1 为归档重建批（38 篇逐字恢复、
   §2 重建 38 行登记），0.3.1 为整理批适配、0.3.0 新增第 9 条与 --staged 分叉提示、
   0.2.0 新增第 7 / 8 条；CPU 产品版本轴仍由 `01_源码/beauty_params.h` 单点维护，
   与脚本自身版本互不相干）
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
# 0.1.0：首批保留的 design-cpu-performance.md 历史数字表格曾列白名单。
# 0.1.1：单独清理批已把该文重写为零历史数字，白名单随之清空；
# 此后任何当前版 design/guides/reference 出现数字表格都会被第 6 条告警。
NUMERIC_WHITELIST = frozenset()

# ---- 0.2.0 新增：第 7 / 8 条断言用的正则与例外表 ----
VERIFY_REF_RE = re.compile(r'`(05_验证/[A-Za-z0-9_\-/\.]+\.md)`')
VERIFY_INDEX_ROW_RE = re.compile(r'^\|\s*`([^`\s]+\.md)`\s*\|', re.M)
SEMVER_RE = re.compile(r'\d+\.\d+\.\d+\.\d+')
BUILD_STR_RE = re.compile(r'^\s*#define\s+BEAUTY_BUILD_STR\s+"([^"]+)"', re.M)
TIMELINESS_MARKERS = ('未重测', '不回填', '时效', '未复核', '历史轴', '历史实测数字',
                      '适用版本', '最后一次内容复核', '定量读数只在')

# 例外登记模板（docs/INDEX.md §4 第 9 条）：每条理由须写明「登记日期 / 复核期限」，
# 并说明为何不能当场修复；[待跟进] 不得无限期挂账。下表 6 条属历史条目，
# 原始登记日期未记录，本轮不臆造回填，待逐条复核时补齐。

# 第 7 条例外：头表的「适用版本」按 docs/INDEX.md §1 说明，记的是「该文档最后一次
# 内容复核时的 CPU 轴版本」，不是当前产品轴。下列文档属设计取证快照，允许落后；
# 每条理由都会打印，脚本还会验证正文确有时效声明，防止例外被滥用。
VERSION_AXIS_EXEMPT = {
    'docs/design/design-cpu-performance.md':
        '架构/开关有效；历史轴实测数字未重测，§2.5~§2.11 才按 1.0.13.0 补写',
    'docs/design/design-face-mask.md':
        '拆分批只搬走原 §13–§15，未重新复核机制；头表明示「适用版本不回填」',
    'docs/design/design-head-roll.md':
        '定量读数只在 05_验证/ 取证文件；正文声明时效，未在 1.0.13.10 重测',
    'docs/design/design-quality-findings.md':
        '§1–§7 是历史轴归档头登记的结论；状态列注明历史实测数字不进本文',
    'docs/design/design-smoothing.md':
        '架构/开关有效；状态列注明历史轴实测数字未重测',
    'docs/design/design-tone-detail.md':
        '机制/开关有效；状态列注明历史轴实测数字未重测',
}

# 第 8 条例外：2026-11-10 归档重建批恢复 38 篇归档件，其中两篇的历史取证引用
# 指向未留存的 `05_验证/ab20261109_band_roi_obs.md`。归档件正文按治理约束不改写，
# 故按 §4 第 9 条例外登记模板，逐条写明登记日期、复核期限与不能当场修复的原因。
VERIFY_ARCHIVE_EXEMPT = {
    '05_验证/ab20261109_band_roi_obs.md':
        '登记 2026-11-10 / 复核期限 2026-12-10：归档件 changelog-history-20261109.md '
        '与 index-batchlog-20261109.md 的历史引用；该取证文件在整理批未留存，'
        '按「归档件正文不改写」约束保留原引用，不得据此当作当前结论',
}

# 第 9 条例外：§1「适用版本」列按 docs/INDEX.md 第 68 行定义记「最后一次内容复核
# 版本」，设计取证快照允许落后。集合沿用第 7 条例外中的 design 子集（理由共用），
# 避免两张表漂移；每条仍逐条打印，正文时效声明由第 9 条现场校验。
INDEX_AXIS_EXEMPT = {p: why for p, why in VERSION_AXIS_EXEMPT.items()
                     if p.startswith('docs/design/')}


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


def current_version():
    """当前 CPU 版本唯一出处：01_源码/beauty_params.h 的 BEAUTY_BUILD_STR。"""
    m = BUILD_STR_RE.search(read('01_源码/beauty_params.h'))
    return m.group(1) if m else None


def head_version(text, field):
    """取头表字段里的第一个四段版本号；字段缺失或没写版本号返回 None。"""
    m = re.search(r'^\|\s*' + field + r'\s*\|\s*([^|]+)\|', text[:1500], re.M)
    if not m:
        return None
    v = SEMVER_RE.search(m.group(1))
    return v.group(0) if v else None


def verify_md_files():
    """递归收集 05_验证/ 下全部 .md（含 goldens/ 等子目录），返回仓库相对路径集合。"""
    out = set()
    for root, _dirs, files in os.walk(os.path.join(ROOT, '05_验证')):
        for f in files:
            if f.endswith('.md'):
                out.add(os.path.relpath(os.path.join(root, f), ROOT).replace(os.sep, '/'))
    return out


def main():
    ap = argparse.ArgumentParser(description='文档体系一致性自检')
    ap.add_argument('--staged', action='store_true',
                    help='提交前模式：附列暂存区涉及的文档 + 工作区/暂存区分叉提示（断言仍为全量）')
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

        # 工作区 / 暂存区分叉提示（0.3.0）：只告警，不改变退出码。
        # 本脚本的断言读工作区磁盘，check_upload.py --staged 读 git 索引；
        # 两者分叉时合规闸门验的可能是改前内容。见 docs/INDEX.md §4 第 8 条。
        r2 = subprocess.run(['git', '-C', ROOT, 'diff', '--name-only'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
        diverged = [l.strip() for l in (r2.stdout or '').splitlines()
                    if l.strip() and (l.strip().endswith('.md') or
                                     l.strip().startswith('05_验证/check_'))]
        if diverged:
            print('[提示] 工作区与暂存区分叉（%d 个文档/闸门脚本，只告警不阻断）：' % len(diverged))
            for f in diverged:
                print('    ', f)
            print('      `check_docs.py --staged` 断言读工作区，`check_upload.py --staged` 读暂存区；')
            print('      提交前请按 `docs/INDEX.md` §4 第 8 条三步清单处理（必要时重新 git add）。')
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
        tail = ('；白名单 %d 篇：%s' % (len(NUMERIC_WHITELIST),
                                    ', '.join(sorted(NUMERIC_WHITELIST)))) \
               if NUMERIC_WHITELIST else '；白名单已清空，全部当前版纳入扫描'
        print('[6] 当前版数字表格 —— 通过（0 告警%s）' % tail)

    # ---- 7. 版本轴一致性（唯一出处：beauty_params.h） ----
    axis_exempt_used = []
    cur = current_version()
    if not cur:
        print('[7] 版本轴一致性 —— 失败：读不到 BEAUTY_BUILD_STR')
        problems.append('版本轴单点缺失')
    else:
        bad7, stale7 = [], []
        for p in sorted(actual_active):
            t = read(p)
            for field in ('版本', '适用代码版本'):
                v = head_version(t, field)
                if v == cur or p in VERSION_AXIS_EXEMPT:
                    continue
                bad7.append('%s 的「%s」= %s，应为 %s' % (p, field, v or '无', cur))
        # 例外必须真的用得上，且正文确有时效声明
        for p, why in sorted(VERSION_AXIS_EXEMPT.items()):
            if p not in actual_active:
                stale7.append('%s 已不在 Active 集合' % p)
                continue
            t = read(p)
            if head_version(t, '版本') == cur and head_version(t, '适用代码版本') == cur:
                stale7.append('%s 已跟升，例外可移除' % p)
                continue
            if not any(k in t for k in TIMELINESS_MARKERS):
                bad7.append('%s 登记了版本轴例外，但正文没有任何时效声明' % p)
            axis_exempt_used.append((p, why))
        if bad7:
            print('[7] 版本轴一致性 —— 失败（当前版 %s）' % cur)
            for s in bad7:
                print('    ' + s)
            problems.append('版本轴不一致 %d 项' % len(bad7))
        else:
            print('[7] 版本轴一致性 —— 通过（当前版 %s；严格 %d 篇，已登记例外 %d 篇）' %
                  (cur, len(actual_active) - len(axis_exempt_used), len(axis_exempt_used)))
            for p, why in axis_exempt_used:
                print('    例外 %-46s %s' % (p, why))
        for s in stale7:
            print('    [提示] 例外表条目已失效：%s' % s)

    # ---- 8. 05_验证/ 引用 0 断链 ----
    verify_exempt_used = set()
    vfiles = verify_md_files()
    scan8 = sorted(actual_active) + ['05_验证/INDEX.md']
    arch8 = sorted('%s/%s' % (ARCH_DIR, f) for f in arch_files)
    bad8, n_active_refs = [], 0
    for p in scan8:
        for r in VERIFY_REF_RE.findall(read(p)):
            n_active_refs += 1
            if r not in vfiles:
                bad8.append('MISSING %s  <- %s' % (r, p))
    # 05_验证/INDEX.md 表格登记的裸文件名
    n_index_rows = 0
    for leaf in VERIFY_INDEX_ROW_RE.findall(read('05_验证/INDEX.md')):
        n_index_rows += 1
        if '05_验证/' + leaf not in vfiles:
            bad8.append('INDEX 登记了不存在的文件: %s' % leaf)
    # 归档件：历史引用按定义保留，断链须逐条登记理由
    n_arch_refs = 0
    for p in arch8:
        for r in VERIFY_REF_RE.findall(read(p)):
            n_arch_refs += 1
            if r in vfiles:
                continue
            if r in VERIFY_ARCHIVE_EXEMPT:
                verify_exempt_used.add(r)
            else:
                bad8.append('归档件 MISSING %s  <- %s（未登记历史例外）' % (r, p))
    for r in sorted(VERIFY_ARCHIVE_EXEMPT):
        if r in vfiles:
            print('    [提示] 历史例外条目已失效，可移除：%s' % r)
    if bad8:
        print('[8] 05_验证/ 引用 —— 失败（%d 条断链）' % len(bad8))
        for s in bad8:
            print('    ' + s)
        problems.append('验证目录断链 %d 条' % len(bad8))
    else:
        print('[8] 05_验证/ 引用 —— 通过（%d 个 md；Active %d 条 + INDEX 登记 %d 条 + '
              '归档 %d 条，0 断链；历史例外 %d 条）' %
              (len(vfiles), n_active_refs, n_index_rows, n_arch_refs,
               len(verify_exempt_used)))
        for r in sorted(verify_exempt_used):
            print('    历史例外 %-46s %s' % (r, VERIFY_ARCHIVE_EXEMPT[r]))

    # ---- 9. 总表「适用版本」列一致性（0.3.0 新增） ----
    index_exempt_used = []
    bad9, stale9 = [], []
    sec1_ver = {}
    for cells in sec1:
        p = path_of(cells)
        if not p or len(cells) < 5:
            continue
        m = SEMVER_RE.search(cells[4])
        sec1_ver[p] = m.group(0) if m else None
    if not cur:
        bad9.append('读不到 BEAUTY_BUILD_STR，无法校验 §1 适用版本列')
    else:
        for p, v in sorted(sec1_ver.items()):
            if v == cur:
                continue
            if p in INDEX_AXIS_EXEMPT:
                t = read(p) if exists(p) else ''
                if not any(k in t for k in TIMELINESS_MARKERS):
                    bad9.append('%s 登记了总表版本例外，但正文没有任何时效声明' % p)
                index_exempt_used.append((p, INDEX_AXIS_EXEMPT[p]))
                continue
            bad9.append('%s 的 §1「适用版本」= %s，应为 %s' % (p, v or '无', cur))
    for p in sorted(INDEX_AXIS_EXEMPT):
        if p not in sec1_ver:
            stale9.append('%s 已不在 §1 登记' % p)
        elif sec1_ver[p] == cur:
            stale9.append('%s 已跟升，例外可移除' % p)
    if bad9:
        print('[9] 总表适用版本列一致性 —— 失败（当前版 %s）' % (cur or '未知'))
        for s in bad9:
            print('    ' + s)
        problems.append('总表适用版本不一致 %d 项' % len(bad9))
    else:
        print('[9] 总表适用版本列一致性 —— 通过（当前版 %s；§1 登记 %d 行，'
              '严格 %d 行，已登记例外 %d 行）' %
              (cur, len(sec1_ver), len(sec1_ver) - len(index_exempt_used),
               len(index_exempt_used)))
        for p, why in sorted(index_exempt_used):
            print('    总表例外 %-46s %s' % (p, why))
    for s in stale9:
        print('    [提示] 总表版本例外条目已失效：%s' % s)

    # ---- 汇总 ----
    print()
    if problems:
        print('=== 未通过：%s ===' % '；'.join(problems))
        return 1
    detail = []
    if warns:
        detail.append('%d 条告警' % len(warns))
    if axis_exempt_used:
        detail.append('%d 篇版本轴例外' % len(axis_exempt_used))
    if verify_exempt_used:
        detail.append('%d 条历史断链例外' % len(verify_exempt_used))
    if index_exempt_used:
        detail.append('%d 篇总表版本例外' % len(index_exempt_used))
    print('=== 全部通过：文档体系一致（%s） ===' %
          ('；'.join(detail) if detail else '无告警'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
