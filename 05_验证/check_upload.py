#!/usr/bin/env python3
"""check_upload.py —— 上传前自检：确认 GitHub 上传内容合规且纯净

为什么需要它
------------
`.gitignore` 是唯一的排除闸门，而 `.gitignore` 是**否定式**规则：
没被排除的文件默认会被上传。因此「上传内容是否干净」不能靠人眼扫目录，
必须**以 git 自己的索引为准**做一次断言式检查。

本脚本做四件事：

1. **索引一致性** —— 已跟踪但工作区已删的文件（会随上传推送出去）
2. **法务红线** —— 闭源商业资产（CNamaSDK / fuai / auth_package / *.bundle）
3. **隐私红线** —— 含真人面部的位图、原始帧数据（.raw）
4. **体积红线** —— 单文件超过 1 MB（大文件应走 GitHub Release 附件）

用法
----
    python check_upload.py              # 检查当前索引
    python check_upload.py --staged     # 检查暂存区（提交前用）
    python check_upload.py --fix        # 检查并自动移除已删文件的索引条目

退出码：0 = 全部通过；1 = 存在违规项。
"""
import argparse
import os
import subprocess
import sys

# ---- 红线定义 --------------------------------------------------------
# 闭源商业资产：FaceUnity（相芯科技）NamaSDK 系，无再分发权
CLOSED_SOURCE_PATTERNS = [
    'CNamaSDK', 'fuai.dll', 'auth_package', '.bundle',
    'ai_face_processor', 'face_beautification',
]
# 隐私：含真人面部的位图
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
# 帧数据
RAW_EXT = '.raw'
# 单文件体积上限（大文件走 Release 附件）
MAX_FILE_BYTES = 1024 * 1024


def git(*args):
    r = subprocess.run(['git'] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return r.returncode, r.stdout.strip()


def list_files(mode):
    """mode='index' 取索引；mode='staged' 取暂存区相对 HEAD 的变更。"""
    if mode == 'index':
        _, out = git('ls-files')
        return [l for l in out.split('\n') if l]
    _, out = git('diff', '--cached', '--name-only', '--diff-filter=ACMR')
    return [l for l in out.split('\n') if l]


def main():
    ap = argparse.ArgumentParser(description='上传前合规自检')
    ap.add_argument('--staged', action='store_true', help='检查暂存区而非索引')
    ap.add_argument('--fix', action='store_true',
                    help='自动把「已跟踪但工作区已删」的文件从索引移除')
    args = ap.parse_args()

    mode = 'staged' if args.staged else 'index'
    files = list_files(mode)
    if not files:
        print('没有待检查的文件。')
        return 0

    print('检查目标：%s' % ('暂存区' if args.staged else 'git 索引'))
    print('文件总数：%d' % len(files))
    print()

    problems = []

    # ---- 1. 索引一致性：已跟踪但工作区已删 ----
    gone = []
    for f in files:
        if args.staged:
            continue
        if not os.path.exists(f):
            gone.append(f)
    if gone:
        print('[1] 索引一致性 —— 失败')
        for f in gone:
            print('    已跟踪但工作区已删（会随上传推送）: %s' % f)
        problems.append('索引残留 %d 个已删除文件' % len(gone))
        if args.fix:
            for f in gone:
                git('rm', '--cached', '--quiet', '--', f)
            print('    已自动从索引移除 %d 个' % len(gone))
    else:
        print('[1] 索引一致性 —— 通过（无已删文件残留）')

    # ---- 2. 法务红线：闭源商业资产 ----
    legal = [f for f in files
             if any(p.lower() in f.lower() for p in CLOSED_SOURCE_PATTERNS)]
    if legal:
        print('[2] 法务红线 —— 失败')
        for f in legal:
            print('    闭源商业资产: %s' % f)
        problems.append('闭源资产 %d 个' % len(legal))
    else:
        print('[2] 法务红线 —— 通过（无闭源商业资产）')

    # ---- 3. 隐私红线：真人面部位图 / 帧数据 ----
    priv = [f for f in files
            if f.lower().endswith(IMAGE_EXTS + (RAW_EXT,))]
    if priv:
        print('[3] 隐私红线 —— 失败')
        for f in priv[:20]:
            print('    含真人面部/帧数据: %s' % f)
        if len(priv) > 20:
            print('    ... 共 %d 个' % len(priv))
        problems.append('隐私素材 %d 个' % len(priv))
    else:
        print('[3] 隐私红线 —— 通过（无位图/帧数据）')

    # ---- 4. 体积红线 ----
    big = []
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            sz = os.path.getsize(f)
        except OSError:
            continue
        if sz > MAX_FILE_BYTES:
            big.append((sz, f))
    if big:
        print('[4] 体积红线 —— 失败（单文件 > 1 MB）')
        for sz, f in sorted(big, reverse=True):
            print('    %10d B  %s' % (sz, f))
        problems.append('超限文件 %d 个' % len(big))
    else:
        print('[4] 体积红线 —— 通过（无单文件 > 1 MB）')

    # ---- 汇总 ----
    print()
    if problems:
        print('=== 未通过：%s ===' % '；'.join(problems))
        return 1
    print('=== 全部通过：上传内容合规且纯净 ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
