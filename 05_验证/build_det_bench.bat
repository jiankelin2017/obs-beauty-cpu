@echo off
rem ===========================================================================
rem  build_det_bench.bat - build det_bench.exe, the single-frame face detection
rem  probe used to diagnose the 1.0.5.0 head-roll compensation.
rem
rem  Same toolchain / probe pattern as build_cpu_bench_v103.bat (which is known
rem  to work); build_manual.bat and build-ui_320.bat both die before cl because of
rem  a cmd.exe parsing bug documented in 02_build\build_1.0.4.0.bat.
rem
rem  Pure ASCII + CRLF on purpose.
rem ===========================================================================
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
for /d %%d in ("%ROOT%\01_*") do if exist "%%d\beauty_face.cpp" set SRC=%%d
if not defined SRC (
    echo [det] source dir not found under %ROOT%
    exit /b 1
)

set OUT=%HERE%_probe_run\v103
if not exist "%OUT%" mkdir "%OUT%"

cl /nologo /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /I "%SRC%" ^
   /I "%HERE%deps\runtime\include" ^
   /Fo"%OUT%\\" /Fe"%OUT%\det_bench.exe" ^
   "%HERE%det_bench.cpp" ^
   "%SRC%\beauty_face.cpp" ^
   "%SRC%\beauty_onnx.cpp" ^
   "%SRC%\beauty_log.cpp" ^
   user32.lib
if errorlevel 1 (
    echo [det] BUILD FAILED
    exit /b 1
)
echo [det] BUILD OK -^> %OUT%\det_bench.exe
del /q "%OUT%\*.obj" 2>nul
del /q "%OUT%\*.lib" 2>nul
del /q "%OUT%\*.exp" 2>nul
exit /b 0
