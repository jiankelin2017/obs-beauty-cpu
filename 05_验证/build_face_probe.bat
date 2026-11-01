@echo off
rem Build face_probe.exe - verify self-written YuNet detector (ASCII only, wildcard for the Chinese dir)
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
    echo [face] source dir not found
    exit /b 1
)

cl /nologo /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /I "%HERE%deps\runtime\include" ^
   /Fo"%HERE%\" /Fe"%HERE%face_probe.exe" ^
   "%SRC%\face_probe.cpp" ^
   "%SRC%\beauty_face.cpp" ^
   "%SRC%\beauty_onnx.cpp" ^
   "%HERE%deps\runtime\onnxruntime.lib"
if errorlevel 1 (
    echo [face] BUILD FAILED
    exit /b 1
)
copy /Y "%HERE%deps\runtime\onnxruntime.dll" "%HERE%onnxruntime.dll" >nul
echo [face] BUILD OK
