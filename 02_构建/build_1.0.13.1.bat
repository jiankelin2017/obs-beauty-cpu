@echo off
rem ===========================================================================
rem  build_1.0.13.1.bat - build BOTH CPU dlls for version 1.0.13.1
rem
rem  1.0.13.1 = smooth low-frequency box: 3-channel fused horizontal pass (B1)
rem            + SSE vertical pass 4 columns at a time (B2). Bit-exact vs 1.0.12.0,
rem            switch BEAUTY_BOX_FUSE=0 falls back to the old per-plane path.
rem  1.0.13.1 additionally carries the code-review hotfix C1/C2 (rotation angle
rem            state). That part is NOT bit-exact: only frames where a rotation
rem            fallback actually fires change.
rem  Output goes to 02_build\build_1.0.13.1 so 1.0.7.0 / 1.0.5.0 / 1.0.4.0 / 1.0.3.0
rem  and build_output are never touched (old out dirs left as-is on purpose).
rem
rem  Why both compiles are INLINED here instead of calling build_manual.bat /
rem  build-ui_320.bat:
rem    Those two scripts die with rc=1 before ever reaching cl. Root cause proven
rem    2026-11-09 with a six-line repro: an echo message that CONTAINS PARENS
rem    inside an "if not defined X (...)" block makes cmd.exe end the whole
rem    batch with errorlevel 1 no matter what the condition actually is.
rem        set FOO=1
rem        if not defined FOO (
rem            echo msg (with parens)
rem            exit /b 1
rem        )
rem        echo REACHED-END      <- never printed, rc=1
rem    The same block with a paren-free message prints REACHED-END and rc=0.
rem    Both legacy scripts carry "(looked for ... under %ROOT%)" in that block,
rem    so they can never build. Keep every message below paren-free.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path and
rem  cmd.exe reads .bat as GBK.
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
    echo [build113] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [build113] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [build113] offline-verify dir not found
    exit /b 1
)

if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build113] Qt not found at %QT%
    exit /b 1
)

set OUT=%HERE%build_1.0.13.1
if not exist "%OUT%" mkdir "%OUT%"

echo [build113] src=%SRC%
echo [build113] dep=%DEP%
echo [build113] out=%OUT%

rem ---- 1) engine / filter dll ---------------------------------------------
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
    echo [build113] FILTER BUILD FAILED
    exit /b 1
)
echo [build113] FILTER OK -^> %OUT%\obs-beauty.dll

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
    echo [build113] UI BUILD FAILED
    exit /b 1
)
echo [build113] UI OK -^> %OUT%\obs-beauty-ui.dll
exit /b 0
