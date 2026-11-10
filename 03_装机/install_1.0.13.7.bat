@echo off
rem ===========================================================================
rem  install_1.0.13.7.bat - OVERWRITE the installed CPU filter + UI dll with 1.0.13.7
rem
rem  1.0.13.7 = "still flashes at ~45 deg after 1.0.13.7".
rem              1.0.13.7 got three things right (detection gap, mask hold,
rem              EMA history) but left the real cause alone: the face geometry
rem              is swapped within a single frame.
rem              Reproduced in the async path (face_src 3 deg per frame, all
rem              three warp sliders at 100, measuring mean|out-in|):
rem                f16 48 deg meanD 0.98   f17 51 deg 1.16   f18 54 deg 1.61
rem              -> +39% in one frame. Two things change at once: phi jumps
rem              the real 45.7 deg, and fw/fh jumps from the AABB to the tight
rem              box (108x116 -> 107x142).
rem              Fix: a 6-frame geometry transition. startGeoFade() stores the
rem              pre-switch box (geoLast, written by buildMaskInto itself -
rem              NOT DetState::faces, which the render thread swaps in
rem              asynchronously) and applyGeoFade() blends centre, rw/rh, roll
rem              and all 5 keypoints over the next 6 frames. EMA is skipped
rem              during it; the transition maintains faceEmaPrev itself.
rem              Upright output is byte-identical (8/8 panel combos); the
rem              largest adjacent jump went from +0.46 to +0.19.
rem  Same drops as 1.0.13.0 otherwise; only the two dlls change.
rem
rem  Right-click -> "Run as administrator". This file CANNOT work without an
rem  elevated token: C:\ProgramData\obs-studio\plugins grants BUILTIN\Users
rem  (CI)(WD,AD) -- create-only, no write and no delete on existing files.
rem  A non-elevated copy fails with "Permission denied" (verified 2026-11-09).
rem
rem  What it does:
rem    0) refuse while obs64.exe is alive (the dlls are mapped read-only)
rem    1) back up whatever is installed now to _backup_136\ (if not there)
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
for /d %%d in ("%ROOT%\02_*") do if exist "%%d\build_1.0.13.7\obs-beauty.dll" set BUILD=%%d\build_1.0.13.7
if not defined BUILD (
    echo [install137] build_1.0.13.7 not found under %ROOT%\02_*
    pause
    exit /b 1
)

set PLUG=C:\ProgramData\obs-studio\plugins
set FDIR=%PLUG%\obs-beauty\bin\64bit
set UDIR=%PLUG%\obs-beauty-ui\bin\64bit

rem --- 0) OBS must be closed ------------------------------------------------
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | findstr /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install137] OBS is RUNNING. Close OBS completely, then run again.
    pause
    exit /b 1
)

rem --- 1) back up whatever is installed now --------------------------------
if not exist "%HERE%_backup_136\bin64" mkdir "%HERE%_backup_136\bin64"
if not exist "%HERE%_backup_136\ui64"  mkdir "%HERE%_backup_136\ui64"
if exist "%FDIR%\obs-beauty.dll"    copy /Y "%FDIR%\obs-beauty.dll"    "%HERE%_backup_136\bin64\" >nul
if exist "%UDIR%\obs-beauty-ui.dll" copy /Y "%UDIR%\obs-beauty-ui.dll" "%HERE%_backup_136\ui64\"  >nul

rem --- 2) overwrite --------------------------------------------------------
copy /Y "%BUILD%\obs-beauty.dll"    "%FDIR%\obs-beauty.dll"    >nul
if errorlevel 1 (
    echo [install137] FAILED to write filter dll - not elevated?
    pause
    exit /b 1
)
copy /Y "%BUILD%\obs-beauty-ui.dll" "%UDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 (
    echo [install137] FAILED to write ui dll - not elevated?
    pause
    exit /b 1
)

echo [install137] OK
certutil -hashfile "%FDIR%\obs-beauty.dll" MD5 | findstr /v ":"
certutil -hashfile "%UDIR%\obs-beauty-ui.dll" MD5 | findstr /v ":"
echo [install137] Compare these two MD5s with the ones in the build_1.0.13.7 folder.
echo [install137] Now start OBS; the init line must read v1.0.13.7.
pause
exit /b 0
