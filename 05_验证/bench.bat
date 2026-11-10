@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl /nologo /O2 /EHsc /utf-8 /Fe:bench_median.exe bench_median.cpp
if errorlevel 1 exit /b 1
bench_median.exe
