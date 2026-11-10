@echo off
rem ===========================================================================
rem  install_1.0.13.5.bat - OVERWRITE the installed CPU filter + UI dll with 1.0.13.5
rem
rem  1.0.13.5 = the warp displacement field is built in the FACE's own frame.
rem              The slim-face and chin sliders were deforming the wrong part
rem              of the face on sources rotated by 90/270 (the ones the
rem              auto-orientation compensation kicks in for): after the box
rem              is inverse-rotated, f.w is the face HEIGHT and f.h is the
rem              face WIDTH, but the fields kept using the image axes, so
rem              "compress toward the midline" squeezed the face's long
rem              axis and "compress below the mouth" landed beside the ear.
rem              Upright sources are byte-identical (8/8 panel combos).
rem  Same drops as 1.0.13.0 otherwise; only the two dlls change.
rem
rem  Right-click -> "Run as administrator". This file CANNOT work without an
rem  elevated token: C:\ProgramData\obs-studio\plugins grants BUILTIN\Users
rem  (CI)(WD,AD) -- create-only, no write and no delete on existing files.
rem  A non-elevated copy fails with "Permission denied" (verified 2026-11-09).
rem
rem  What it does:
rem    0) refuse while obs64.exe is alive (the dlls are mapped read-only)
rem    1) back up whatever is installed now to _backup_134\ (if not there)
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
for /d %%d in ("%ROOT%\02_*") do if exist "%%d\build_1.0.13.5\obs-beauty.dll" set BUILD=%%d\build_1.0.13.5
if not defined BUILD (
    echo [install135] build_1.0.13.5 not found under %ROOT%\02_*
    pause
    exit /b 1
)

set PLUG=C:\ProgramData\obs-studio\plugins
set FDIR=%PLUG%\obs-beauty\bin\64bit
set UDIR=%PLUG%\obs-beauty-ui\bin\64bit

rem --- 0) OBS must be closed ------------------------------------------------
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | findstr /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install135] OBS is RUNNING. Close OBS completely, then run again.
    pause
    exit /b 1
)

rem --- 1) back up whatever is installed now --------------------------------
if not exist "%HERE%_backup_134\bin64" mkdir "%HERE%_backup_134\bin64"
if not exist "%HERE%_backup_134\ui64"  mkdir "%HERE%_backup_134\ui64"
if exist "%FDIR%\obs-beauty.dll"    copy /Y "%FDIR%\obs-beauty.dll"    "%HERE%_backup_134\bin64\" >nul
if exist "%UDIR%\obs-beauty-ui.dll" copy /Y "%UDIR%\obs-beauty-ui.dll" "%HERE%_backup_134\ui64\"  >nul

rem --- 2) overwrite --------------------------------------------------------
copy /Y "%BUILD%\obs-beauty.dll"    "%FDIR%\obs-beauty.dll"    >nul
if errorlevel 1 (
    echo [install135] FAILED to write filter dll - not elevated?
    pause
    exit /b 1
)
copy /Y "%BUILD%\obs-beauty-ui.dll" "%UDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 (
    echo [install135] FAILED to write ui dll - not elevated?
    pause
    exit /b 1
)

echo [install135] OK
certutil -hashfile "%FDIR%\obs-beauty.dll" MD5 | findstr /v ":"
certutil -hashfile "%UDIR%\obs-beauty-ui.dll" MD5 | findstr /v ":"
echo [install135] Compare these two MD5s with the ones in the build_1.0.13.5 folder.
echo [install135] Now start OBS; the init line must read v1.0.13.5.
pause
exit /b 0
