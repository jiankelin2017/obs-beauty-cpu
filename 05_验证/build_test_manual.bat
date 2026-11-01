@echo off
rem Manual build of the standalone engine test DLL (no vcvars64.bat: reg.exe blocked)
setlocal
set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
set SDKBASE=C:\Program Files (x86)\Windows Kits\10
set SDKVER=10.0.26100.0

set PATH=%VSBASE%\bin\Hostx64\x64;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared;%SDKBASE%\Include\%SDKVER%\winrt
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

cd /d "%~dp0"
cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /Fe:legacy_engine_test_317.dll ^
   legacy_engine.cpp legacy_region.cpp beauty_log.cpp ^
   opengl32.lib gdi32.lib user32.lib
if errorlevel 1 (
    echo [test-build] FAILED
    exit /b 1
)
echo [test-build] OK -^> legacy_engine_test_317.dll
