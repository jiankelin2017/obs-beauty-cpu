@echo off
rem ===========================================================================
rem  install_1.0.13.11.bat - OVERWRITE the installed CPU filter + UI dll with 1.0.13.11
rem
rem  1.0.13.11 changes the INSTALLER only. The filter and the panel are the same
rem            source as 1.0.13.10: the dll sizes are identical (463872 / 218624
rem            bytes) and the only difference is the BEAUTY_BUILD_STR string.
rem            So there is nothing to see on screen - that is expected.
rem
rem  Why it exists: the NSIS uninstaller restores <InstallDir>\backup\*.bak when
rem      that file exists, and the installer only wrote a backup when none existed
rem      yet - so the backup was never refreshed. Measured with PHASE R: install
rem      1.0.13.9, upgrade to 1.0.13.10, uninstall  ->  a complete 1.0.13.9 plugin
rem      is left on the machine (505856 B) instead of being removed.
rem      Fix in obs-beauty.nsi: a backup happens only on a FIRST install (registry
rem      Version absent); an upgrade deletes stale .bak files instead. Measured
rem      after the fix: 0 files in backup\, and all four files gone after uninstall.
rem
rem  Same drops as 1.0.13.10 otherwise; only the two dlls change.
rem
rem  Right-click -> "Run as administrator". This file CANNOT work without an
rem  elevated token: C://ProgramData//obs-studio//plugins grants BUILTIN\Users
rem  (CI)(WD,AD) -- create-only, no write and no delete on existing files.
rem  A non-elevated copy fails with "Permission denied" (verified 2026-11-09).
rem
rem  What it does:
rem    0) refuse while obs64.exe is alive (the dlls are mapped read-only)
rem    1) back up whatever is installed now to _backup_1311\ (if not there)
rem    2) copy obs-beauty.dll      -> ...\plugins\obs-beauty\bin\64bit\
rem       copy obs-beauty-ui.dll   -> ...\plugins\obs-beauty-ui\bin\64bit\
rem    3) print MD5 of both, so the caller can confirm which build is live
rem
rem  Only two files change. onnxruntime.dll and models\yunet.onnx stay as-is.
rem  Keep this file PURE ASCII + CRLF: cmd.exe reads .bat as GBK.
rem ===========================================================================
setlocal enabledelayedexpansion

set HERE=%~dp0
set ROOT=%HERE%..
set BUILD=
for /d %%d in ("%ROOT%\02_*") do if exist "%%d\build_1.0.13.11\obs-beauty.dll" set BUILD=%%d\build_1.0.13.11
if not defined BUILD (
    echo [install141] build_1.0.13.11 not found under %ROOT%\02_*
    pause
    exit /b 1
)

set PLUG=C:\ProgramData\obs-studio\plugins
set FDIR=%PLUG%\obs-beauty\bin\64bit
set UDIR=%PLUG%\obs-beauty-ui\bin\64bit

rem --- 0) OBS must be closed ------------------------------------------------
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | findstr /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install141] OBS is RUNNING. Close OBS completely, then run again.
    pause
    exit /b 1
)

rem --- 1) back up whatever is installed now --------------------------------
if not exist "%HERE%_backup_1311\bin64" mkdir "%HERE%_backup_1311\bin64"
if not exist "%HERE%_backup_1311\ui64"  mkdir "%HERE%_backup_1311\ui64"
if exist "%FDIR%\obs-beauty.dll"    copy /Y "%FDIR%\obs-beauty.dll"    "%HERE%_backup_1311\bin64\" >nul
if exist "%UDIR%\obs-beauty-ui.dll" copy /Y "%UDIR%\obs-beauty-ui.dll" "%HERE%_backup_1311\ui64\"  >nul

rem --- 2) overwrite --------------------------------------------------------
copy /Y "%BUILD%\obs-beauty.dll"    "%FDIR%\obs-beauty.dll"    >nul
if errorlevel 1 (
    echo [install141] FAILED to write filter dll - not elevated?
    pause
    exit /b 1
)
copy /Y "%BUILD%\obs-beauty-ui.dll" "%UDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 (
    echo [install141] FAILED to write ui dll - not elevated?
    pause
    exit /b 1
)

echo [install141] OK
certutil -hashfile "%FDIR%\obs-beauty.dll" MD5 | findstr /v ":"
certutil -hashfile "%UDIR%\obs-beauty-ui.dll" MD5 | findstr /v ":"
echo [install141] Compare these two MD5s with the ones in the build_1.0.13.11 folder.
echo [install141] Now start OBS; the init line must read v1.0.13.11.
pause
exit /b 0
