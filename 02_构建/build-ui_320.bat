@echo off
rem Build obs-beauty-ui.dll. The version is NOT fixed here: it comes from
rem BEAUTY_UI_VERSION in obs-beauty-ui.cpp. This script is version-agnostic,
rem so do not hard-code any version number in these notes (it drifts).
rem
rem NOTE: this file is pure ASCII on purpose. The source tree lives under a
rem       Chinese-named path; a UTF-8 .bat gets read as GBK by cmd.exe and the
rem       literal path is mangled (C1083). So the directories are located by
rem       CONTENT PROBING instead of by name. Same trick as build_manual.bat.
rem
rem 2026-11-01: was matching by prefix ("00_*", "04_*"), which went stale
rem       after the 2026-10-30 re-naming of the whole tree (source -> 01_*,
rem       dependency -> under the new "reference files" folder). Now each role
rem       identified by a file that must exist inside it, so re-numbering
rem       the tree cannot break the build again.
rem
rem The version string lives in the source itself (BEAUTY_UI_VERSION in
rem obs-beauty-ui.cpp). It is NOT passed on the command line, so there is
rem exactly one place to bump.
setlocal enabledelayedexpansion

set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
set SDKBASE=C:\Program Files (x86)\Windows Kits\10
set SDKVER=10.0.26100.0
set QT=C:\Qt

set HERE=%~dp0
set ROOT=%HERE%..
set SRC=
set DEP=

rem --- locate the source dir: the one holding obs-beauty-ui.cpp ----------
for /d %%d in ("%ROOT%\01_*") do if exist "%%d\obs-beauty-ui.cpp" set SRC=%%d
rem --- locate the dependency dir: holds obs-studio-32.1.1\libobs ---------
rem     it may sit at the tree root or one level down, so probe both depths.
for /d %%d in ("%ROOT%\*") do if exist "%%d\obs-studio-32.1.1\libobs" set DEP=%%d
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e

if not defined SRC (
    echo [build-ui] source dir not found (looked for obs-beauty-ui.cpp under %ROOT%)
    exit /b 1
)
if not defined DEP (
    echo [build-ui] dependency dir not found (looked for obs-studio-32.1.1\libobs under %ROOT%)
    exit /b 1
)
if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build-ui] Qt not found at %QT%
    exit /b 1
)

set PATH=%VSBASE%\bin\Hostx64\x64;%QT%\bin;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared;%SDKBASE%\Include\%SDKVER%\winrt
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

rem CPU four-segment builds set BEAUTY_OUTDIR to a separate folder so the
rem frozen 3.1.40 DLLs in build_output are never overwritten.
rem With BEAUTY_OUTDIR unset this behaves exactly as before.
set OUT=%HERE%build_output
if defined BEAUTY_OUTDIR set OUT=%BEAUTY_OUTDIR%
if not exist "%OUT%" mkdir "%OUT%"

echo [build-ui] src=%SRC%
echo [build-ui] dep=%DEP%

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
    echo [build-ui] FAILED
    exit /b 1
)
echo [build-ui] OK -^> %OUT%\obs-beauty-ui.dll
