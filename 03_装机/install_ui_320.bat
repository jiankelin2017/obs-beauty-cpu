@echo off
rem Install obs-beauty-ui 3.0.20 (compact layout: shorter title, no preset buttons, 460px width).
rem
rem Only the UI module is replaced. The filter DLL (obs-beauty.dll) and the
rem OBS native filter-properties page are NOT touched by this build.
rem
rem Target is the OBS global plugin path (ProgramData), not obs-plugins\64bit:
rem   C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\
rem
rem NOTE: pure ASCII on purpose (see build_manual.bat for the GBK/C1083 reason).
setlocal enabledelayedexpansion

set HERE=%~dp0
set ROOT=%HERE%..
rem for %%f in (path with a wildcard in a DIRECTORY component) does not glob --
rem only the filename part is expanded. Resolve the directory first with for /d.
set BUILD=
for /d %%d in ("%ROOT%\01_*") do set BUILD=%%d
set SRC=%BUILD%\build_output\obs-beauty-ui_320.dll

set DSTDIR=C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit
set DST=%DSTDIR%\obs-beauty-ui.dll
set BAKDIR=%DSTDIR%\ui-backup

if not defined BUILD (
    echo [install-ui] build dir not found under %ROOT%
    exit /b 1
)
if not exist "%SRC%" (
    echo [install-ui] built dll not found: %SRC%
    exit /b 1
)
if not exist "%DST%" (
    echo [install-ui] target not found: %DST%
    exit /b 1
)

rem --- self-elevate ------------------------------------------------------------
rem ProgramData\obs-studio is writable by Users only for CREATING files: the
rem inherited ACE is (CI)(WD,AD,WEA,WA) with no DELETE. Replacing an existing
rem dll therefore needs an elevated token (<user>s:F), otherwise the
rem move/overwrite fails with "access denied" even though the .tmp copy works.
set ELEV=0
net session >nul 2>&1
if not errorlevel 1 set ELEV=1
%SystemRoot%\System32\fltmc.exe >nul 2>&1
if not errorlevel 1 set ELEV=1
if "%ELEV%"=="0" (
  echo.
  echo [UAC] <user> rights are required to replace
  echo       %DST%
  echo [UAC] A Windows permission prompt will appear now - please click "Yes".
  echo.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs -Wait"
  exit /b 0
)

rem --- refuse to touch a running OBS: the dll is mapped and the copy would fail ---
rem Use the absolute path: inside a Git Bash session the MSYS find.exe comes first
rem on PATH and does not understand /i, which made this check silently useless.
set FINDSTR=%SystemRoot%\System32\findstr.exe
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | "%FINDSTR%" /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install-ui] OBS is running. Close OBS first, then run this again.
    exit /b 1
)

if not exist "%BAKDIR%" mkdir "%BAKDIR%"

rem --- timestamp for the backup name ---
set STAMP=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set STAMP=%STAMP: =0%

echo [install-ui] src = %SRC%
echo [install-ui] dst = %DST%
echo [install-ui] backup OK %BAKDIR%\obs-beauty-ui.dll.%STAMP%.bak

copy /Y "%DST%" "%BAKDIR%\obs-beauty-ui.dll.%STAMP%.bak" >nul
if errorlevel 1 (
    echo [install-ui] backup FAILED
    exit /b 1
)

copy /Y "%SRC%" "%DST%.tmp" >nul
if errorlevel 1 (
    echo [install-ui] copy to .tmp FAILED
    exit /b 1
)

move /Y "%DST%.tmp" "%DST%" >nul
if errorlevel 1 (
    echo [install-ui] replace FAILED
    exit /b 1
)

echo [install-ui] --- verify ---
for %%A in ("%SRC%") do echo [install-ui] src size=%%~zA
for %%A in ("%DST%") do echo [install-ui] dst size=%%~zA
certutil -hashfile "%DST%" MD5
echo [install-ui] done. Restart OBS, then open menu A - panel.
