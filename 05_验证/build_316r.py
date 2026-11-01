# -*- coding: utf-8 -*-
"""用归档里的 3.0.16 源码，走与 3.0.17 完全相同的注入流程重建测试副本，
输出 legacy_engine_test_316r.dll，用来判断"模式0 与 3.0.16 的微小差异"
到底来自我的改动，还是来自测试副本重建。

按 build_test_manual.bat 的编译命令执行（不依赖 vcvars64）。
"""
import io
import os
import shutil
import subprocess
import sys

HERE = r'C:\legacy_e2e'
ARCH = r'D:\插件\LegacyBeauty_v3.0.16_FINAL\00_源码'
WORK = os.path.join(HERE, '_b316r')

MSVC = r'C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231'
SDK = r'C:\Program Files (x86)\Windows Kits\10'


def build():
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    for f in ('legacy_engine.cpp', 'legacy_engine.h', 'legacy_region.cpp',
              'legacy_region.h', 'beauty_log.cpp', 'beauty_log.h'):
        shutil.copy2(os.path.join(ARCH, f), os.path.join(WORK, f))

    # 注入测量钩子（用同一份脚本，锚点相同）
    r = subprocess.run([sys.executable, os.path.join(HERE, 'inject_test_hook.py')],
                       cwd=WORK, capture_output=True, text=True)
    print('[hook]', (r.stdout or r.stderr).strip().replace('\n', ' | '))

    # 补 LegacySeqTest（从 3.0.17 副本里搬，函数体与引擎无关）
    cur = io.open(os.path.join(HERE, 'legacy_engine.cpp'), encoding='utf-8').read()
    i = cur.find('int __stdcall LegacySeqTest')
    j = cur.rfind('}  // extern "C"')
    seq = cur[i:j].rstrip('\n')
    p = os.path.join(WORK, 'legacy_engine.cpp')
    t = io.open(p, encoding='utf-8').read()
    k = t.rfind('}  // extern "C"')
    io.open(p, 'w', encoding='utf-8', newline='').write(
        t[:k].rstrip('\n') + '\n\n' + seq + '\n\n' + t[k:])

    h = io.open(os.path.join(WORK, 'legacy_engine.h'), encoding='utf-8').read()
    decl = '''__declspec(dllexport) int __stdcall LegacySeqTest(const char* engineDir,
                                               const char* inDir, const char* outDir,
                                               int width, int height, int count,
                                               double blur, double whiten,
                                               char* msgBuf, int msgCap);
'''
    kk = h.rindex('#ifdef __cplusplus')
    io.open(os.path.join(WORK, 'legacy_engine.h'), 'w', encoding='utf-8',
            newline='').write(h[:kk].rstrip('\n') + '\n\n' + decl + '\n' + h[kk:])
    print('[seq] 已补 LegacySeqTest')

    bat = os.path.join(WORK, 'build316r.bat')
    io.open(bat, 'w', encoding='ascii', newline='').write(
        '@echo off
'
        'setlocal
'
        'set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
'
        'set SDKBASE=C:\Program Files (x86)\Windows Kits\10
'
        'set SDKVER=10.0.26100.0
'
        'set PATH=%VSBASE%\bin\Hostx64\x64;%PATH%
'
        'set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared;%SDKBASE%\Include\%SDKVER%\winrt
'
        'set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64
'
        'cd /d "%~dp0"
'
        'cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS '
        '/Fe:C:\legacy_e2e\legacy_engine_test_316r.dll '
        'legacy_engine.cpp legacy_region.cpp beauty_log.cpp '
        'opengl32.lib gdi32.lib user32.lib
'
        'if errorlevel 1 (echo [316r] FAILED & exit /b 1)
'
        'echo [316r] OK
')
    r = subprocess.run(['cmd', '/c', bat], cwd=WORK, capture_output=True, text=True)
    out = os.path.join(HERE, 'legacy_engine_test_316r.dll')
    ok = os.path.exists(out)
    print('[build]', 'OK ->' if ok else 'FAIL')
    if not ok:
        print(r.stdout[-1200:])
    return ok
