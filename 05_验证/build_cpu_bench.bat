@echo off
rem Build cpu_bench.exe - measures per-frame cost of the full-frame path vs the
rem mask-ROI path, i.e. how much CPU the 3.1.4 preheat fix saves.
rem
rem Pure ASCII + CRLF on purpose (see build_manual.bat): the source dir has a
rem Chinese name and a UTF-8 .bat gets read as GBK by cmd.exe.
rem
rem Output goes to _probe_run because CoreEngine resolves onnxruntime.dll
rem relative to the exe dir (selfDir()); the DLL is copied there.
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
    echo [bench] source dir not found under %ROOT%
    exit /b 1
)

set OUT=%HERE%_probe_run
if not exist "%OUT%" mkdir "%OUT%"
copy /y "%HERE%deps\runtime\onnxruntime.dll" "%OUT%\onnxruntime.dll" >nul

cl /nologo /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /I "%SRC%" ^
   /I "%HERE%deps\runtime\include" ^
   /Fo"%OUT%\\" /Fe"%OUT%\cpu_bench.exe" ^
   "%HERE%cpu_bench.cpp" ^
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
    echo [bench] BUILD FAILED
    exit /b 1
)
echo [bench] BUILD OK -^> %OUT%\cpu_bench.exe
del /q "%OUT%\*.obj" 2>nul
del /q "%OUT%\*.lib" 2>nul
del /q "%OUT%\*.exp" 2>nul
