@echo off
rem Build beauty_core_test_spawn.dll —— 自研引擎（CoreEngine）的离线对拍 DLL。
rem
rem Pure ASCII on purpose: the sibling source dir has a Chinese name, and a
rem UTF-8 .bat gets read as GBK by cmd.exe (mangles the path -> C1083).
rem Source dir is located with a wildcard, same trick as build_manual.bat.
setlocal enabledelayedexpansion

set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
set SDKBASE=C:\Program Files (x86)\Windows Kits\10
set SDKVER=10.0.26100.0

set PATH=%VSBASE%\bin\Hostx64\x64;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

set HERE=%~dp0
set ROOT=%HERE%..
set SRC=
for /d %%d in ("%ROOT%\00_*") do set SRC=%%d
if not defined SRC (
    echo [core-test] source dir not found under %ROOT%
    exit /b 1
)

cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /DBEAUTY_POOL_LEGACY_SPAWN /D_CRT_SECURE_NO_WARNINGS ^
   /I "%HERE%deps\runtime\include" ^
   /Fo"%HERE%\" /Fe"%HERE%beauty_core_test_spawn.dll" ^
   "%SRC%\core_probe.cpp" ^
   "%SRC%\beauty_core.cpp" ^
   "%SRC%\beauty_pool.cpp" ^
   "%SRC%\beauty_smooth.cpp" ^
   "%SRC%\beauty_freq.cpp" ^
   "%SRC%\beauty_guide.cpp" ^
   "%SRC%\beauty_onnx.cpp" ^
   "%SRC%\beauty_face.cpp" ^
   "%SRC%\beauty_region.cpp" ^
   "%SRC%\beauty_log.cpp" ^
   opengl32.lib gdi32.lib user32.lib
if errorlevel 1 (
    echo [core-test] BUILD FAILED
    exit /b 1
)
echo [core-test] BUILD OK -^> %HERE%beauty_core_test_spawn.dll
