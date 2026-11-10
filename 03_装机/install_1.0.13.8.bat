@echo off
rem ===========================================================================
rem  install_1.0.13.8.bat - OVERWRITE the installed CPU filter + UI dll with 1.0.13.8
rem
rem  1.0.13.8 = "still flashes at ~45 deg after 1.0.13.8".
rem              1.0.13.8 fixed the geometry transition, and that fix is real:
rem              with mask alignment disabled the geometry sweep is flat
rem              (meanD 1.3..1.7, no jump). The remaining jump is the MASK
rem              ALIGNMENT itself (3.1.10). Has a worker result landed? then
rem              process() writes heldFrame_ (the PREVIOUS frame); if not, it
rem              writes the current frame. Worker busy -> those alternate and
rem              the output flips between 'one frame late' and 'current'.
rem              Measured at 57->57 deg: meanD 7.09 -> 1.67 within one frame.
rem              Fix: alignment also requires 'the frame hardly moved' (mean
rem              |diff| over a 4x4 pixel grid < alignDiff, default 4 levels).
rem              Still -> align (mask stays pixel-exact). Moving -> do not:
rem              rather a mask one frame late than a frame repeated.
rem              Upright static output byte-identical (4 combos x 20 frames).
rem              BEAUTY_ALIGN_DIFF=0 restores the old 3.1.10 behaviour.
rem  Same drops as 1.0.13.0 otherwise; only the two dlls change.
rem
rem  Right-click -> "Run as administrator". This file CANNOT work without an
rem  elevated token: C:\ProgramData\obs-studio\plugins grants BUILTIN\Users
rem  (CI)(WD,AD) -- create-only, no write and no delete on existing files.
rem  A non-elevated copy fails with "Permission denied" (verified 2026-11-09).
rem
rem  What it does:
rem    0) refuse while obs64.exe is alive (the dlls are mapped read-only)
rem    1) back up whatever is installed now to _backup_137\ (if not there)
rem    2) copy obs-beauty.dll      -> ...\plugins\obs-beauty\bin\64bit\
rem       copy obs-beauty-ui.dll   -> ...\plugins\obs-beauty-ui\bin\64bit\
rem    3) print MD5 of both, so the caller can confirm which build is live
rem
rem  Keep this file PURE ASCII + CRLF: cmd.exe reads .bat as GBK.
rem ===========================================================================
setlocal enabledelayedexpansion

set HERE=%~dp0
set ROOT=%HERE%..
set BUILD=
for /d %%d in ("%ROOT%\02_*") do if exist "%%d\build_1.0.13.8\obs-beauty.dll" set BUILD=%%d\build_1.0.13.8
if not defined BUILD (
    echo [install138] build_1.0.13.8 not found under %ROOT%\02_*
    pause
    exit /b 1
)

set PLUG=C:\ProgramData\obs-studio\plugins
set FDIR=%PLUG%\obs-beauty\bin\64bit
set UDIR=%PLUG%\obs-beauty-ui\bin\64bit

rem --- 0) OBS must be closed ------------------------------------------------
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | findstr /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install138] OBS is RUNNING. Close OBS completely, then run again.
    pause
    exit /b 1
)

rem --- 1) back up whatever is installed now --------------------------------
if not exist "%HERE%_backup_137\bin64" mkdir "%HERE%_backup_137\bin64"
if not exist "%HERE%_backup_137\ui64"  mkdir "%HERE%_backup_137\ui64"
if exist "%FDIR%\obs-beauty.dll"    copy /Y "%FDIR%\obs-beauty.dll"    "%HERE%_backup_137\bin64\" >nul
if exist "%UDIR%\obs-beauty-ui.dll" copy /Y "%UDIR%\obs-beauty-ui.dll" "%HERE%_backup_137\ui64\"  >nul

rem --- 2) overwrite --------------------------------------------------------
copy /Y "%BUILD%\obs-beauty.dll"    "%FDIR%\obs-beauty.dll"    >nul
if errorlevel 1 (
    echo [install138] FAILED to write filter dll - not elevated?
    pause
    exit /b 1
)
copy /Y "%BUILD%\obs-beauty-ui.dll" "%UDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 (
    echo [install138] FAILED to write ui dll - not elevated?
    pause
    exit /b 1
)

echo [install138] OK
certutil -hashfile "%FDIR%\obs-beauty.dll" MD5 | findstr /v ":"
certutil -hashfile "%UDIR%\obs-beauty-ui.dll" MD5 | findstr /v ":"
echo [install138] Compare these two MD5s with the ones in the build_1.0.13.8 folder.
echo [install138] Now start OBS; the init line must read v1.0.13.8.
pause
exit /b 0
