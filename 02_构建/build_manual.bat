@echo off
rem Manual MSVC build without vcvars64.bat (reg.exe is blocked in this sandbox)
rem NOTE: this file is pure ASCII on purpose. The source tree lives under a
rem       Chinese-named path; a UTF-8 .bat gets read as GBK by cmd.exe and the
rem       literal path is mangled (C1083). So the two directories are located
rem       with wildcards taken from the runtime path instead of being written
rem       out as text.
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
for /d %%d in ("%ROOT%\00_*") do set SRC=%%d
for /d %%d in ("%ROOT%\04_*") do set DEP=%%d
for /d %%d in ("%ROOT%\06_*") do set OFFDIR=%%d
set OUT=%HERE%build_output
if not exist "%OUT%" mkdir "%OUT%"

if not defined SRC (
    echo [build] source dir not found under %ROOT%
    exit /b 1
)
if not defined DEP (
    echo [build] dependency dir not found under %ROOT%
    exit /b 1
)
echo [build] src=%SRC%
echo [build] dep=%DEP%

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
