@echo off
rem Manual MSVC build without vcvars64.bat (reg.exe is blocked in this sandbox)
rem NOTE: this file is pure ASCII on purpose. The source tree lives under a
rem       Chinese-named path; a UTF-8 .bat gets read as GBK by cmd.exe and the
rem       literal path is mangled (C1083). So the directories are located by
rem       CONTENT PROBING instead of by name.
rem
rem 2026-11-01: the old version matched directories by prefix ("00_*", "04_*",
rem       "06_*"). Those prefixes became stale after the 2026-10-30 re-naming
rem       (source -> 01_*, dependency -> under the new
rem       "reference files" folder, offline-verify -> 05_*), so the script
rem       inputs and failed with "source dir not found".
rem       Now each role is identified by a file that must exist inside it,
rem       so re-numbering the tree cannot break the build again.
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
set DEP=
set OFFDIR=

rem --- locate the source dir: the one holding obs-beauty.cpp --------------
for /d %%d in ("%ROOT%\01_*") do if exist "%%d\obs-beauty.cpp" set SRC=%%d
rem --- locate the dependency dir: holds obs-studio-32.1.1\libobs ---------
rem     it may sit at the tree root or one level down (e.g. under a
rem     "reference files" folder), so probe both depths.
for /d %%d in ("%ROOT%\*") do if exist "%%d\obs-studio-32.1.1\libobs" set DEP=%%d
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
rem --- locate the offline-verify dir: the one holding deps\runtime\include -
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d

rem CPU four-segment builds set BEAUTY_OUTDIR to a separate folder so the
rem frozen 3.1.40 DLLs in build_output are never overwritten.
rem With BEAUTY_OUTDIR unset this behaves exactly as before.
set OUT=%HERE%build_output
if defined BEAUTY_OUTDIR set OUT=%BEAUTY_OUTDIR%
if not exist "%OUT%" mkdir "%OUT%"

if not defined SRC (
    echo [build] source dir not found (looked for obs-beauty.cpp under %ROOT%)
    exit /b 1
)
if not defined DEP (
    echo [build] dependency dir not found (looked for obs-studio-32.1.1\libobs under %ROOT%)
    exit /b 1
)
if not defined OFFDIR (
    echo [build] offline-verify dir not found (looked for deps\runtime\include under %ROOT%)
    exit /b 1
)
echo [build] src=%SRC%
echo [build] dep=%DEP%
echo [build] offdir=%OFFDIR%

rem --- keep a copy of the currently installed build before overwriting ---
if exist "%OUT%\obs-beauty.dll" (
    if not exist "%OUT%\obs-beauty_prev.dll" (
        copy /Y "%OUT%\obs-beauty.dll" "%OUT%\obs-beauty_prev.dll" >nul
        echo [backup] saved previous build as obs-beauty_prev.dll
    )
)

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
    echo [build] FAILED
    exit /b 1
)
echo [build] OK -^> %OUT%\obs-beauty.dll
