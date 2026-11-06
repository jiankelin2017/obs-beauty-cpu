@echo off
rem ===========================================================================
rem  install_3.1.40.bat - install filter + panel for 3.1.40
rem
rem  ⚠️ DEPLOYMENT NOTE (2026-11-01, READ BEFORE RUNNING):
rem     The filter currently LIVE on this machine is the GPU build 3.1.76 at
rem         C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\obs-beauty.dll
rem     NOT at obs-plugins\64bit (that is where this script installs).
rem     OBS loads BOTH locations. If you want to switch back to the CPU build,
rem     first remove/quarantine the GPU DLL, otherwise two filters with the
rem     same id may coexist. The user asked to prepare the patch WITHOUT
rem     installing - this script has NOT been run.
rem
rem  WHAT CHANGED IN 3.1.40 (filter algorithm only; panel is a version-label
rem  bump from 3.1.39, layout untouched):
rem
rem    1) NO-FACE FRAMES NOW PASS THROUGH BYTE-FOR-BYTE.
rem       Before: once a session had EVER seen a face, losing the face
rem       (person walks out of frame) fell into the "no mask" fallback, where
rem       the smoothing kernel treats a null mask as FULL SKIN (m = 255) and
rem       the ROI is opened up to the whole frame. 1080p smoothing went from
rem       "ROI 12.6%, ~5-7 ms" to full-frame magnitude - and every one of
rem       those pixels was then discarded (tone/clarity/region/detail all sit
rem       behind haveMask; warp needs a non-empty faces_). Background and
rem       clothing got smoothed for nothing.
rem       Now: faceOk_ && everHadMask_ && lastFaces_==0 && no "err=" in
rem       faceErr_  ->  memcpy passthrough, engine ms = 0.00.
rem       Hysteresis is NOT new: kMaskHold=6 already keeps the last mask for
rem       6 missed detections; the 7th miss enters passthrough. Coming back
rem       into frame restores on the detection frame - no flicker.
rem       Rollback: BEAUTY_NOFACE_SKIP=0 restores 3.1.39 byte-for-byte.
rem
rem    2) OFFLINE A/B PROOF (05_验证\_noface_ab.py, 2026-11-01):
rem       face frame + 40 textured no-face frames through old (3.1.39) and
rem       new (3.1.40) core DLLs in one process each:
rem         - face frame          old vs new maxdiff = 0
rem         - 34 hold-period fr.  old vs new maxdiff = 0
rem         - after hold exh.     new == input (maxdiff 0, ms=0.00)
rem                                old != input (full-frame smoothing)
rem       Trap found on the way: the probe calls ensureReady() per frame and
rem       warmUp() resizes mask_ to 1920x1080, which makes updateMask take
rem       the "resolution changed" branch EVERY frame and clears
rem       everHadMask_ - the old fallback could not be reproduced without
rem       BEAUTY_NO_PREWARM=1. Production is unaffected (preheat runs once
rem       at filter load).
rem
rem  What it does, in order:
rem    1) backs up BOTH currently installed DLLs into backup_install_<date>\
rem    2) copies build_output\obs-beauty.dll    -> obs-plugins\64bit\
rem    3) copies build_output\obs-beauty-ui.dll -> ProgramData panel dir
rem    4) sanity-checks both copied files are real PE images (>100000 bytes)
rem
rem  Needs administrator rights (C:/Program Files). Self-elevates.
rem  OBS MUST BE CLOSED - the script refuses to run while obs64.exe is alive.
rem
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
set OUT=%ROOT%\02_构建\build_output

set NEW=%OUT%\obs-beauty.dll
set NEWUI=%OUT%\obs-beauty-ui.dll
if not exist "%NEW%" (
    echo [install] missing %NEW%  - run build_manual.bat first
    pause
    exit /b 1
)
if not exist "%NEWUI%" (
    echo [install] missing %NEWUI% - run build-ui_320.bat first
    pause
    exit /b 1
)

set OBSDIR=C:\Program Files\obs-studio\obs-plugins\64bit
set PLUGDIR=C:\ProgramData\obs-studio\plugins
set UIDIR=%PLUGDIR%\obs-beauty-ui\bin\64bit

rem --- 0) refuse to touch anything while OBS is live ------------------------
tasklist /fi "imagename eq obs64.exe" 2>nul | find /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install] OBS is RUNNING. Close OBS first, then run this again.
    echo [install] Nothing was changed.
    pause
    exit /b 1
)

rem --- 1) backup ------------------------------------------------------------
for /f "tokens=1-3 delims=/. " %%a in ('echo %date%') do set D=%%a%%b%%c
set BAK=%HERE%backup_install_%D%
if not exist "%BAK%" mkdir "%BAK%"
if exist "%OBSDIR%\obs-beauty.dll" (
    copy /Y "%OBSDIR%\obs-beauty.dll" "%BAK%\obs-beauty_prev-3.1.39.dll" >nul
    echo [backup] %BAK%\obs-beauty_prev-3.1.39.dll
)
if exist "%UIDIR%\obs-beauty-ui.dll" (
    copy /Y "%UIDIR%\obs-beauty-ui.dll" "%BAK%\obs-beauty-ui_prev-3.1.39.dll" >nul
    echo [backup] %BAK%\obs-beauty-ui_prev-3.1.39.dll
)

rem --- 2) filter DLL --------------------------------------------------------
copy /Y "%NEW%" "%OBSDIR%\obs-beauty.dll" >nul
if errorlevel 1 (
    echo [install] FAILED to copy the filter DLL
    pause
    exit /b 1
)
echo [install] filter   OK  %OBSDIR%\obs-beauty.dll
call :check_pe "%OBSDIR%\obs-beauty.dll" || exit /b 1

rem --- 3) panel DLL ---------------------------------------------------------
if not exist "%UIDIR%" mkdir "%UIDIR%"
copy /Y "%NEWUI%" "%UIDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 (
    echo [install] FAILED to copy the panel DLL
    pause
    exit /b 1
)
echo [install] panel    OK  %UIDIR%\obs-beauty-ui.dll
call :check_pe "%UIDIR%\obs-beauty-ui.dll" || exit /b 1

echo.
echo [install] done. Start OBS and check the log for:
echo            [obs-beauty] init OK (v3.1.40, engine=core/1.4.1, region=on ...)
echo            [obs-beauty] noface_skip=on  (BEAUTY_NOFACE_SKIP=0 rolls back)
echo            [obs-beauty-ui] module loaded v3.1.40
echo.
echo            New in 3.1.40: with nobody in frame the filter passes video
echo            through byte-for-byte (engine 0.00 ms) instead of smoothing
echo            the whole frame. Faces keep the exact 3.1.39 behaviour
echo            (offline A/B: maxdiff=0 on face frames and the whole
echo            mask-hold period).
echo.
echo            Performance line now ends with " noface_skip=N" - N counts
echo            passthrough frames inside the profiling window.
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
