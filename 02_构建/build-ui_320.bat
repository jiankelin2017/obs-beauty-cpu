@echo off
rem Build obs-beauty-ui.dll 3.0.20 (compact layout: shorter title, no preset buttons, 460px width).
rem
rem NOTE: this file is pure ASCII on purpose. The source tree lives under a
rem       Chinese-named path; a UTF-8 .bat gets read as GBK by cmd.exe and the
rem       literal path is mangled (C1083). So the two directories are located
rem       with wildcards taken from the runtime path instead of being written
rem       out as text. Same trick as build_manual.bat.
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
for /d %%d in ("%ROOT%\00_*") do set SRC=%%d
for /d %%d in ("%ROOT%\04_*") do set DEP=%%d

if not defined SRC (
    echo [build-ui] source dir not found under %ROOT%
    exit /b 1
)
if not defined DEP (
    echo [build-ui] dependency dir not found under %ROOT%
    exit /b 1
)
if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build-ui] Qt not found at %QT%
    exit /b 1
)

set PATH=%VSBASE%\bin\Hostx64\x64;%QT%\bin;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared;%SDKBASE%\Include\%SDKVER%\winrt
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

set OUT=%HERE%build_output
if not exist "%OUT%" mkdir "%OUT%"

echo [build-ui] src=%SRC%
echo [build-ui] dep=%DEP%

cl /nologo /LD /O2 /EHsc /std:c++17 /Zc:__cplusplus /permissive- /W3 /utf-8 ^
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
