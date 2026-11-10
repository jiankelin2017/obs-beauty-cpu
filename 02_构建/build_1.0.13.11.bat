rem ===========================================================================
rem  build_1.0.13.11.bat - build BOTH CPU dlls for version 1.0.13.11
rem
rem  1.0.13.11 = installer fix only. The filter/engine source is the same as
rem              1.0.13.10; the only difference inside the DLL is the
rem              BEAUTY_BUILD_STR string ("1.0.13.10" -> "1.0.13.11").
rem
rem  What changed: the NSIS script obs-beauty.nsi. The installer used to back up
rem  an existing file only when the backup did not exist yet (IfNot FileExists),
rem  so an existing backup was never refreshed; the uninstaller then restored
rem  <InstallDir>\backup\*.bak unconditionally. Measured result (PHASE R):
rem  install 1.0.13.9 -> install 1.0.13.10 -> uninstall leaves a full 1.0.13.9
rem  plugin on the machine (505,856 B) instead of removing the plugin.
rem
rem  Fix: decide "first install or upgrade" at INSTALL time from the registry
rem  Version value. Only a first install backs up the files it finds (those must
rem  belong to something else: the GPU build, or a hand-copied dll). An upgrade
rem  deletes $INSTDIR\backup\*.bak instead, so the uninstaller falls through to
rem  its Delete branch. The uninstall section itself was not touched.
rem
rem  Release build: BEAUTY_ENV_LOCK=1, all 115 BEAUTY_* overrides are inert.
rem  Use a _dev build for any A/B that drives BEAUTY_* variables.
rem
rem  Output goes to 02_build\build_1.0.13.11 so older out dirs stay untouched.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path
rem  and cmd.exe reads .bat as GBK.
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
    echo [build141] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [build141] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [build141] offline-verify dir not found
    exit /b 1
)

if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build141] Qt not found at %QT%
    exit /b 1
)

set OUT=%HERE%build_1.0.13.11
if not exist "%OUT%" mkdir "%OUT%"

echo [build141] src=%SRC%
echo [build141] dep=%DEP%
echo [build141] out=%OUT%

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
    echo [build141] FILTER BUILD FAILED
    exit /b 1
)
echo [build141] FILTER OK -^> %OUT%\obs-beauty.dll

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
    echo [build141] UI BUILD FAILED
    exit /b 1
)
echo [build141] UI OK -^> %OUT%\obs-beauty-ui.dll
exit /b 0
