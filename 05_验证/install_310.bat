@echo off
rem Install obs-beauty v3.0.10 (elevated installer, generated 2026-10-25)
setlocal
set SRC=C:\legacy_e2e\obs-beauty_310.dll
set DST=C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty.dll
set BAK=C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty-backup\obs-beauty.dll.20261025_195741.bak

echo [0] preflight: obs64.exe must not be running
tasklist /fi "imagename eq obs64.exe" 2>nul | find /i "obs64.exe" >nul
if not errorlevel 1 (
  echo [FAIL] obs64.exe is still running - close OBS and retry
  exit /b 2
)

echo [1/3] backup current DLL
if exist "%DST%" copy /y "%DST%" "%BAK%"
if not exist "%BAK%" echo [FAIL] backup was not created
if not exist "%BAK%" exit /b 1
echo   backup -^> %BAK%

echo [2/3] copy new DLL
copy /y "%SRC%" "%DST%"
if errorlevel 1 echo [FAIL] copy failed
if errorlevel 1 exit /b 1

echo [3/3] verify size + md5
for %%A in ("%SRC%") do set S1=%%~zA
for %%B in ("%DST%") do set S2=%%~zB
for /f "tokens=1" %%a in ('certutil -hashfile "%SRC%" MD5 ^| findstr /r "^[0-9a-f]*$"') do set H1=%%a
for /f "tokens=1" %%b in ('certutil -hashfile "%DST%" MD5 ^| findstr /r "^[0-9a-f]*$"') do set H2=%%b
echo   src %S1% bytes  md5 %H1%
echo   dst %S2% bytes  md5 %H2%

if not "%S1%"=="%S2%" echo [FAIL] size mismatch
if not "%S1%"=="%S2%" exit /b 1
if /i not "%H1%"=="%H2%" echo [FAIL] md5 mismatch
if /i not "%H1%"=="%H2%" exit /b 1

echo [OK] v3.0.10 installed and verified
exit /b 0
