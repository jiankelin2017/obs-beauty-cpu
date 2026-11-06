#!/usr/bin/env python3
"""src_fingerprint.py —— 源码树指纹（可复现，与编译时间戳无关）

为什么需要它
------------
DLL 的 md5 **不可复现**：MSVC 默认在 PE 头嵌入 TimeDateStamp，
同一份源码连编两次 md5 不同（体积分毫不差）。因此 md5 只能证明
「已装件 == 这一次构建」，**不能**证明「源码一致」。

本工具给出另一个判据：对 **01_源码 下参与编译的全部 .cpp/.h**
按「去掉注释与空白后的规范化文本」算 SHA-256。

- 去掉注释与空白 ⇒ 改注释、改排版、动空行**不会**改变指纹
  （本次 2026-11-01 整理改的 17 行全是文档路径注释，指纹应保持不变）
- 保留全部预处理指令、字符串字面量、标识符 ⇒ 任何逻辑改动**必然**改变指纹

用法
----
    python src_fingerprint.py                # 打印当前源码指纹
    python src_fingerprint.py --json          # JSON 输出
    python src_fingerprint.py --record FILE   # 写入/更新指纹记录文件
    python src_fingerprint.py --check FILE    # 与记录文件比对，退出码 0=一致 1=不一致
    python src_fingerprint.py --dir 路径      # 指定源码目录（默认 ../01_源码）

判读
----
指纹一致 ⇒ 源码的**有效内容**未变。指纹不一致 ⇒ 源码有实质改动，
必须重编、重装机，并更新 02_文档 与 README 里的指纹登记。
"""
import argparse
import hashlib
import json
import os
import re
import sys

# 与 02_构建\build_manual.bat / build-ui_320.bat 的 cl 命令保持一致
FILTER_SOURCES = [
    'obs-beauty.cpp', 'beauty_core.cpp', 'beauty_pool.cpp', 'beauty_smooth.cpp',
    'beauty_freq.cpp', 'beauty_guide.cpp', 'beauty_onnx.cpp', 'beauty_face.cpp',
    'beauty_region.cpp', 'beauty_warp.cpp', 'beauty_log.cpp',
]
# 滤镜 + 面板共用的头
HEADERS = [
    'beauty_core.h', 'beauty_smooth.h', 'beauty_freq.h', 'beauty_region.h',
    'beauty_face.h', 'beauty_guide.h', 'beauty_onnx.h', 'beauty_pool.h',
    'beauty_warp.h', 'beauty_log.h', 'beauty_params.h',
]
# 面板源码（面板单独编译，build-ui_320.bat）
UI_SOURCES = ['obs-beauty-ui.cpp']

_BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.S)
_LINE_COMMENT = re.compile(r'//[^\n]*')
_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"')


def normalize(text):
    """去注释与空白，但**保留字符串字面量**的内容。

    字符串里可能出现 // 或 /* ，必须先保护起来，
    否则 "http://x" 会被当成行注释起点。
    """
    saved = []

    def stash(m):
        saved.append(m.group(0))
        return '\x00STR%d\x00' % (len(saved) - 1)

    text = _STRING_LITERAL.sub(stash, text)
    text = _BLOCK_COMMENT.sub(' ', text)
    text = _LINE_COMMENT.sub(' ', text)
    # 还原字符串
    for i, s in enumerate(saved):
        text = text.replace('\x00STR%d\x00' % i, s)
    # 去掉所有空白
    return re.sub(r'\s+', '', text)


def digest_dir(src_dir, files):
    """对给定文件集合算规范化指纹。

    文件顺序固定 ⇒ 结果与文件系统枚举顺序无关。
    """
    h = hashlib.sha256()
    parts = []
    for name in files:
        path = os.path.join(src_dir, name)
        if not os.path.exists(path):
            parts.append('MISSING:%s' % name)
            h.update(('MISSING:%s' % name).encode('utf-8'))
            continue
        with open(path, 'rb') as f:
            raw = f.read()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        norm = normalize(text)
        fh = hashlib.sha256(norm.encode('utf-8')).hexdigest()
        parts.append('%s=%s' % (name, fh[:16]))
        h.update(('%s=%s' % (name, fh)).encode('utf-8'))
    return h.hexdigest(), parts


def main():
    ap = argparse.ArgumentParser(description='源码树可复现指纹')
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument('--dir', default=os.path.join(here, '..', '01_源码'),
                    help='源码目录（默认 ../01_源码）')
    ap.add_argument('--json', action='store_true', help='JSON 输出')
    ap.add_argument('--record', metavar='FILE', help='写入/更新指纹记录文件')
    ap.add_argument('--check', metavar='FILE', help='与记录文件比对')
    args = ap.parse_args()

    src = os.path.abspath(args.dir)
    if not os.path.isdir(src):
        print('error: source dir not found: %s' % src, file=sys.stderr)
        return 2

    filt_files = FILTER_SOURCES + HEADERS
    ui_files = UI_SOURCES + HEADERS

    fp_filter, parts_filter = digest_dir(src, filt_files)
    fp_ui, parts_ui = digest_dir(src, ui_files)
    # 全量（含面板）指纹
    fp_all, parts_all = digest_dir(src, sorted(set(filt_files + UI_SOURCES)))

    record = {
        'filter': fp_filter,
        'ui': fp_ui,
        'all': fp_all,
        'files': parts_all,
    }

    if args.check:
        if not os.path.exists(args.check):
            print('error: record file not found: %s' % args.check, file=sys.stderr)
            return 2
        with open(args.check, 'r', encoding='utf-8') as f:
            old = json.load(f)
        ok = True
        for k in ('filter', 'ui', 'all'):
            same = old.get(k) == record[k]
            ok = ok and same
            print('%-8s %s  %s' % (k, 'MATCH' if same else 'DIFF',
                                    record[k][:32]))
            if not same:
                print('         recorded: %s' % str(old.get(k))[:32])
        return 0 if ok else 1

    if args.record:
        with open(args.record, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=1)
        print('recorded -> %s' % args.record)

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=1))
    else:
        print('源码指纹 (规范化 SHA-256，已去注释与空白)')
        print('  filter : %s' % fp_filter)
        print('  ui     : %s' % fp_ui)
        print('  all    : %s' % fp_all)
        print()
        print('逐文件:')
        for p in parts_all:
            print('  %s' % p)
    return 0


if __name__ == '__main__':
    sys.exit(main())
