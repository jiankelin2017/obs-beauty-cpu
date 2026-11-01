@echo off
rem Build spawn_bench.exe —— 线程创建开销基准（纯 ASCII，避免 cmd 按 GBK 读 UTF-8）
setlocal

set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
set SDKBASE=C:\Program Files (x86)\Windows Kits\10
set SDKVER=10.0.26100.0

set PATH=%VSBASE%\bin\Hostx64\x64;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

cd /d "%~dp0"
cl /nologo /O2 /EHsc /std:c++17 /utf-8 spawn_bench.cpp /Fe:spawn_bench.exe
if errorlevel 1 exit /b 1
echo BUILD OK
