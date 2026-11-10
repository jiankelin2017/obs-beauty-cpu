rem ===========================================================================
rem  build_1.0.13.12.bat - build BOTH CPU dlls for version 1.0.13.12
rem
rem  1.0.13.12 = code-review fixes D1 / D2. Unlike 1.0.13.11 (installer
rem  only), THIS version changes the filter source, so both DLLs are
rem  rebuilt and their bytes are NOT identical to 1.0.13.11.
rem
rem  D1 (obs-beauty.cpp): the param thread (beauty_filter_update) and the
rem  render thread (beauty_filter_render) shared enabled/mirror/v[9]/dirty
rem  with no synchronisation. Added a POD SRWLOCK param_lock (the struct is
rem  allocated with bzalloc/bfree, so a C++ mutex member is not safe).
rem  update() takes the exclusive lock for the whole write + dirty flag;
rem  render() takes one beauty_param_snapshot per frame under the same lock,
rem  consumes dirty in that critical section, and uses only the local copy.
rem
rem  D2 (beauty_onnx.cpp): CreateSessionOptions and
rem  GetAllocatorWithDefaultOptions returned OrtStatus* that was ignored, and
rem  alloc was used without a null check. Now both status values are handled,
rem  opts/alloc/inName are checked, and failures write err (existing fallback).
rem
rem  Release build: BEAUTY_ENV_LOCK=1, all 115 BEAUTY_* overrides are inert.
rem  Output goes to 02_build\build_1.0.13.12 so older out dirs stay untouched.
rem  Pure ASCII + CRLF on purpose: cmd.exe reads .bat as GBK.
rem ===========================================================================
setlocal enabledelayedexpansion

set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
set SDKBASE=C:\Program Files (x86)\Windows Kits\10
set SDKVER=10.0.26100.0
set QT=C:\Qt

set PATH=%VSBASE%\bin\Hostx64\x64;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared;%SDKBASE%\Include\%SDKVER%\winrt
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

set HERE=%~dp0
set ROOT=%HERE%..

set SRC=
for /d %%d in ("%ROOT%\01_*") do if exist "%%d\obs-beauty.cpp" set SRC=%%d
if not defined SRC (
    echo [build142] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [build142] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [build142] offline-verify dir not found
    exit /b 1
)

if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build142] Qt not found at %QT%
    exit /b 1
)

set OUT=%HERE%build_1.0.13.12
if not exist "%OUT%" mkdir "%OUT%"

echo [build142] src=%SRC%
echo [build142] dep=%DEP%
echo [build142] out=%OUT%

rem ---- 1) engine / filter dll ---------------------------------------------
cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS /DBEAUTY_ENV_LOCK=1 ^
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
    echo [build142] FILTER BUILD FAILED
    exit /b 1
)
echo [build142] FILTER OK -^> %OUT%\obs-beauty.dll

rem ---- 2) UI dll - Qt6, needs QT\bin on PATH ------------------------------
set PATH=%QT%\bin;%PATH%
cl /nologo /LD /O2 /EHsc /std:c++17 /Zc:__cplusplus /permissive- /W3 /utf-8 ^
   /DBEAUTY_UI_CPU_EDITION=1 ^
   /I "%DEP%\obs-studio-32.1.1\libobs" ^
   /I "%QT%\include" /I "%QT%\include\QtCore" /I "%QT%\include\QtGui" /I "%QT%\include\QtWidgets" ^
   /Fo"%OUT%\\" /Fe"%OUT%\obs-beauty-ui.dll" ^
   "%SRC%\obs-beauty-ui.cpp" ^
   "%DEP%\obs-sdk\obs.lib" "%DEP%\obs-sdk\obs-frontend-api.lib" ^
   "%QT%\lib\Qt6Widgets.lib" "%QT%\lib\Qt6Gui.lib" "%QT%\lib\Qt6Core.lib" ^
   user32.lib
if errorlevel 1 (
    echo [build142] UI BUILD FAILED
    exit /b 1
)
echo [build142] UI OK -^> %OUT%\obs-beauty-ui.dll
exit /b 0
