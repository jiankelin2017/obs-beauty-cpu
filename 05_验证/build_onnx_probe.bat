@echo off
rem Build onnx_probe.exe —— 验证 ONNX Runtime 封装（纯 ASCII，通配符定位中文目录）
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
set DEPS=
for /d %%d in ("%ROOT%\00_*") do set SRC=%%d
for /d %%d in ("%HERE%deps") do set DEPS=%%d
if not defined SRC (
    echo [onnx] source dir not found
    exit /b 1
)
if not exist "%HERE%deps\runtime\onnxruntime.lib" (
    echo [onnx] deps\runtime\onnxruntime.lib missing
    exit /b 1
)

cl /nologo /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /I "%HERE%deps\runtime\include" ^
   /Fo"%HERE%\" /Fe"%HERE%onnx_probe.exe" ^
   "%SRC%\onnx_probe.cpp" ^
   "%SRC%\beauty_onnx.cpp" ^
   "%HERE%deps\runtime\onnxruntime.lib"
if errorlevel 1 (
    echo [onnx] BUILD FAILED
    exit /b 1
)
rem 运行时需要 onnxruntime.dll 与 exe 同目录
copy /Y "%HERE%deps\runtime\onnxruntime.dll" "%HERE%onnxruntime.dll" >nul
echo [onnx] BUILD OK
