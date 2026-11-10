@echo off
rem Build mask_dump.exe against the CURRENT source tree.
rem
rem Why this file exists: build_cpu_bench.bat still locates the source dir by
rem the old "00_*" prefix, which became stale after the 2026-10-30 re-naming.
rem On top of that it omits beauty_warp.cpp, which beauty_core.cpp now calls.
rem Both are fixed here. Everything else is kept byte-identical in spirit so the
rem numbers stay comparable with the older exe.
rem
rem Output goes to _probe_run\v103 so the existing mask_dump.exe (core 0.7.3,
rem 2026-10-28) is left untouched.
rem
rem Pure ASCII + CRLF on purpose (see build_manual.bat): the source dir has a
rem Chinese name and a UTF-8 .bat gets read as GBK by cmd.exe.
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
for /d %%d in ("%ROOT%\01_*") do if exist "%%d\beauty_core.cpp" set SRC=%%d
if not defined SRC (
    echo [bench] source dir not found under %ROOT%
    exit /b 1
)

set OUT=%HERE%_probe_run\v103
if not exist "%OUT%" mkdir "%OUT%"
copy /y "%HERE%deps\runtime\onnxruntime.dll" "%OUT%\onnxruntime.dll" >nul

cl /nologo /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /I "%SRC%" ^
   /I "%HERE%deps\runtime\include" ^
   /Fo"%OUT%\\" /Fe"%OUT%\mask_dump.exe" ^
   "%HERE%mask_dump.cpp" ^
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
   opengl32.lib gdi32.lib user32.lib
if errorlevel 1 (
    echo [bench] BUILD FAILED
    exit /b 1
)
echo [bench] BUILD OK -^> %OUT%\mask_dump.exe
del /q "%OUT%\*.obj" 2>nul
del /q "%OUT%\*.lib" 2>nul
del /q "%OUT%\*.exp" 2>nul
