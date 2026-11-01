@echo off
rem ===========================================================================
rem  install_3.1.28.bat - install the 3.1.28 filter into the OBS tree
rem
rem  DIFFERENCE FROM install_3.1.26.bat: this one installs **only the filter**.
rem  3.1.28 changes are all filter-side:
rem    - new 3 "shape" sliders (thin face / big eye / chin), default 0
rem    - ALL parameter long descriptions removed (no hover tooltips at all)
rem  The panel source was NOT touched, so obs-beauty-ui.dll stays at 3.1.26
rem  and must NOT be replaced - the panel reads its parameter list from the
rem  filter at runtime, so the new "shape" tab appears without a new panel
rem  binary, and the removed tooltips disappear on their own.
rem
rem  What it does, in order:
rem    1) backs up the currently installed filter DLL into backup_install_<ts>\
rem    2) copies build_output\obs-beauty.dll -> obs-plugins\64bit\
rem    3) sanity-checks that the copied file is a real PE image (>100000 bytes)
rem
rem  Needs administrator rights (C:\Program Files). Self-elevates.
rem  Keep this file pure ASCII: a UTF-8 .bat is read as GBK by cmd.exe and any
rem  literal path would be mangled into C1083-style garbage.
rem ===========================================================================
setlocal enabledelayedexpansion

net session >nul 2>&1
if errorlevel 1 (
    echo [install] administrator rights required - requesting elevation...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set HERE=%~dp0
set ROOT=%HERE%..
set BLD=
for /d %%d in ("%ROOT%\01_*") do set BLD=%%d
if not defined BLD (
    echo [install] build directory not found under %ROOT%
    pause
    exit /b 1
)

set NEW=%BLD%\build_output\obs-beauty.dll
if not exist "%NEW%" (
    echo [install] missing %NEW%  - run build_manual.bat first
    pause
    exit /b 1
)

set OBSDIR=C:\Program Files\obs-studio\obs-plugins\64bit
set UIDIR=C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit

rem --- 1) backup ------------------------------------------------------------
for /f "tokens=1-3 delims=/. " %%a in ('echo %date%') do set D=%%a%%b%%c
set BAK=%HERE%backup_install_%D%
if not exist "%BAK%" mkdir "%BAK%"
if exist "%OBSDIR%\obs-beauty.dll" (
    copy /Y "%OBSDIR%\obs-beauty.dll" "%BAK%\obs-beauty_3.1.26.dll.prev" >nul
    echo [backup] %BAK%\obs-beauty_3.1.26.dll.prev
)

rem --- 2) filter DLL --------------------------------------------------------
tasklist /fi "imagename eq obs64.exe" 2>nul | find /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install] OBS is running - close it first.
    pause
    exit /b 1
)
copy /Y "%NEW%" "%OBSDIR%\obs-beauty.dll" >nul
if errorlevel 1 (
    echo [install] FAILED to copy the filter DLL
    pause
    exit /b 1
)
echo [install] filter   OK  %OBSDIR%\obs-beauty.dll
call :check_pe "%OBSDIR%\obs-beauty.dll" || exit /b 1

rem --- 3) panel untouched ---------------------------------------------------
if exist "%UIDIR%\obs-beauty-ui.dll" (
    echo [install] panel    LEFT AS IS  %UIDIR%\obs-beauty-ui.dll
) else (
    echo [install] WARN: panel DLL not found - the top menu will be missing.
)

echo.
echo [install] done. Start OBS, check the log for:
echo            [obs-beauty] init OK (v3.1.28, engine=core/1.4.0, region=on ...)
echo            [obs-beauty-ui] module loaded v3.1.26  (panel is intentionally 3.1.26)
pause
exit /b 0

rem --- sanity check: the installed file must be a real PE image -------------
:check_pe
set "SZ=0"
for %%f in ("%~1") do set "SZ=%%~zf"
if !SZ! LSS 100000 (
    echo [install] ERROR: %~1 is only !SZ! bytes - the copy did not work.
    echo [install] Copy the DLL by hand from the build_output folder and retry.
    pause
    exit /b 1
)
exit /b 0
