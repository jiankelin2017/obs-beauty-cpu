@echo off
rem Build a standalone engine test DLL (no OBS dependency) for e2e verification.
rem Pure-ASCII paths only: cmd.exe reads .bat files in the OEM codepage, so any
rem non-ASCII byte in a quoted path breaks the quoting.
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (
    echo [test-build] vcvars64 failed
    exit /b 1
)
cd /d "%~dp0"
cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /Fe:legacy_engine_test.dll ^
   legacy_engine.cpp legacy_region.cpp beauty_log.cpp ^
   opengl32.lib gdi32.lib user32.lib
if errorlevel 1 (
    echo [test-build] FAILED
    exit /b 1
)
echo [test-build] OK -^> legacy_engine_test.dll
