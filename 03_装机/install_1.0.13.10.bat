@echo off
rem ===========================================================================
rem  install_1.0.13.10.bat - OVERWRITE the installed CPU filter + UI dll with 1.0.13.10
rem
rem  1.0.13.10 = three review findings on top of 1.0.13.9. No visible change
rem              on the normal path: the pixel path is untouched.
rem
rem  C-1 (possible crash). The per-size reallocation in obs-beauty.cpp's
rem      render callback committed f->w/f->h BEFORE allocating, then returned
rem      early if any pointer came back NULL. The next frame's test
rem      "f->w != cx || f->h != cy || !f->tr" was then false forever, so the
rem      buffers were never retried and the code walked into
rem      memcpy(f->buf_in, ...) / gs_stage_texture(f->stage, ...) with a NULL
rem      pointer. 1080p is 8 MB per buffer, 4K is 33 MB, so this only fires
rem      under memory pressure - normal rendering never saw it.
rem      Fix: new beauty_filter_alloc() builds the whole new set in locals and
rem      frees/commits the old one only after every piece succeeded; on
rem      failure the struct is left untouched and the next frame retries.
rem
rem  C-2 / C-3 (hidden knobs). 115 BEAUTY_* env overrides used to be read
rem      directly by getenv in EVERY build, release included. The worst one was
rem      Fix: all of them now go through beauty_env() in beauty_env.h, and the
rem      RELEASE build defines BEAUTY_ENV_LOCK, so they are all inert (MSVC
rem      folds the branches away: the dll drops from 506,880 to 463,872 bytes).
rem
rem      CONSEQUENCE - read this before debugging: BEAUTY_ALIGN_DIFF=0,
rem      BEAUTY_ROLL_CHECK=0 and friends DO NOTHING in this build. To A/B with
rem      env variables install the diagnostic build instead:
rem        02_build\build_1.0.13.10_dev\obs-beauty.dll   (same version string)
rem      The two are told apart by the first log line of the session:
rem        env override: locked (release build)   <- this package
rem        env override: open (dev build)         <- diagnostic build
rem
rem  Same drops as 1.0.13.0 otherwise; only the two dlls change.
rem
rem  Right-click -> "Run as administrator". This file CANNOT work without an
rem  elevated token: C://ProgramData//obs-studio//plugins grants BUILTIN\Users
rem  (CI)(WD,AD) -- create-only, no write and no delete on existing files.
rem  A non-elevated copy fails with "Permission denied" (verified 2026-11-09).
rem
rem  What it does:
rem    0) refuse while obs64.exe is alive (the dlls are mapped read-only)
rem    1) back up whatever is installed now to _backup_139\ (if not there)
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
for /d %%d in ("%ROOT%\02_*") do if exist "%%d\build_1.0.13.10\obs-beauty.dll" set BUILD=%%d\build_1.0.13.10
if not defined BUILD (
    echo [install140] build_1.0.13.10 not found under %ROOT%\02_*
    pause
    exit /b 1
)

set PLUG=C:\ProgramData\obs-studio\plugins
set FDIR=%PLUG%\obs-beauty\bin\64bit
set UDIR=%PLUG%\obs-beauty-ui\bin\64bit

rem --- 0) OBS must be closed ------------------------------------------------
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | findstr /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install140] OBS is RUNNING. Close OBS completely, then run again.
    pause
    exit /b 1
)

rem --- 1) back up whatever is installed now --------------------------------
if not exist "%HERE%_backup_139\bin64" mkdir "%HERE%_backup_139\bin64"
if not exist "%HERE%_backup_139\ui64"  mkdir "%HERE%_backup_139\ui64"
if exist "%FDIR%\obs-beauty.dll"    copy /Y "%FDIR%\obs-beauty.dll"    "%HERE%_backup_139\bin64\" >nul
if exist "%UDIR%\obs-beauty-ui.dll" copy /Y "%UDIR%\obs-beauty-ui.dll" "%HERE%_backup_139\ui64\"  >nul

rem --- 2) overwrite --------------------------------------------------------
copy /Y "%BUILD%\obs-beauty.dll"    "%FDIR%\obs-beauty.dll"    >nul
if errorlevel 1 (
    echo [install140] FAILED to write filter dll - not elevated?
    pause
    exit /b 1
)
copy /Y "%BUILD%\obs-beauty-ui.dll" "%UDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 (
    echo [install140] FAILED to write ui dll - not elevated?
    pause
    exit /b 1
)

echo [install140] OK
certutil -hashfile "%FDIR%\obs-beauty.dll" MD5 | findstr /v ":"
certutil -hashfile "%UDIR%\obs-beauty-ui.dll" MD5 | findstr /v ":"
echo [install140] Compare these two MD5s with the ones in the build_1.0.13.10 folder.
echo [install140] Now start OBS; the init line must read v1.0.13.10.
pause
exit /b 0
