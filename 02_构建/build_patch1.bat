@echo off
rem ===========================================================================
rem  build_patch1.bat - build the CPU filter into a SCRATCH outdir
rem
rem  Purpose (2026-11-09): A/B one unreleased patch (band-path ROI crop) on the
rem  real OBS before deciding whether it ships as a released version. Output
rem  goes to 02_build\build_patch1 so build_1.0.3.0 and build_output (frozen
rem  3.1.x DLLs) are never touched.
rem
rem  Why not reuse build_manual.bat: its dir probing dies before it reaches cl
rem  under this shell (SRC ends up undefined). This file uses the same probe
rem  shape as 05_xx\build_cpu_bench_v103.bat, which is known to work.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path and
rem  cmd.exe reads .bat as GBK.
rem ===========================================================================
setlocal enabledelayedexpansion

set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
set SDKBASE=C:\Program Files (x86)\Windows Kits\10
set SDKVER=10.0.26100.0

set PATH=%VSBASE%\bin\Hostx64\x64;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared;%SDKBASE%\Include\%SDKVER%\winrt
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

set HERE=%~dp0
set ROOT=%HERE%..

set SRC=
for /d %%d in ("%ROOT%\01_*") do if exist "%%d\obs-beauty.cpp" set SRC=%%d
if not defined SRC (
    echo [patch1] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [patch1] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [patch1] offline-verify dir not found
    exit /b 1
)

set OUT=%HERE%build_patch1
if not exist "%OUT%" mkdir "%OUT%"

echo [patch1] src=%SRC%
echo [patch1] dep=%DEP%
echo [patch1] offdir=%OFFDIR%
echo [patch1] out=%OUT%

cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /I "%DEP%\obs-studio-32.1.1\libobs" ^
   /I "%OFFDIR%\deps\runtime\include" ^
   /Fo"%OUT%\\" /Fe"%OUT%\obs-beauty.dll" ^
   "%SRC%\obs-beauty.cpp" ^
   "%SRC%\beauty_core.cpp" ^
   "%SRC%\beauty_pool.cpp" ^
   "%SRC%\beauty_smooth.cpp" ^
   "%SRC%\beauty_freq.cpp" ^
   "%SRC%\beauty_guide.cpp" ^
   "%SRC%\beauty_onnx.cpp" ^
   "%SRC%\beauty_face.cpp" ^
   "%SRC%\beauty_region.cpp" ^
   "%SRC%\beauty_warp.cpp" ^
   "%SRC%\beauty_log.cpp" ^
   "%DEP%\obs-sdk\obs.lib" user32.lib gdi32.lib opengl32.lib
if errorlevel 1 (
    echo [patch1] BUILD FAILED
    exit /b 1
)
echo [patch1] BUILD OK -^> %OUT%\obs-beauty.dll
exit /b 0
