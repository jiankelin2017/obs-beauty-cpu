@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 ( echo vcvars64 failed & exit /b 1 )
cd /d "%~dp0"
cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
   /Fe:legacy_engine_test_b3.dll ^
   legacy_engine_b3.cpp legacy_region.cpp beauty_log.cpp ^
   opengl32.lib gdi32.lib user32.lib
if errorlevel 1 ( echo [b3] FAILED & exit /b 1 )
echo [b3] OK -^> legacy_engine_test_b3.dll
