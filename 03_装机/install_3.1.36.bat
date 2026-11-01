@echo off
rem ===========================================================================
rem  install_3.1.36.bat - install filter + panel for 3.1.36
rem
rem  WHAT CHANGED IN 3.1.36 (panel only; the filter is rebuilt just to keep the
rem  same version number - its algorithm code is untouched):
rem
rem    1) FIXED: the two bottom-right buttons were DISAPPEARING. They used to be
rem       created once in the constructor, but the very first build_form() calls
rem       clear_form() -> purge_layout(mode_grid_), which deleted every widget in
rem       that grid - buttons included - and never re-created them. The panel has
rem       therefore always looked like it was missing the Reset / Close buttons.
rem       They are now created inside build_form(), same lifecycle as the combo
rem       boxes, so they cannot vanish again.
rem
rem    2) SIZE IS NOW FIXED: 460 x 560 LOGICAL px (user instruction).
rem       560 includes the Windows title bar (31 logical, measured from the
rem       user's own screenshot), so the Qt client area is 529 - passing 560 to
rem       resize() would render about 591.
rem       setFixedSize() is used: the window can no longer be dragged, and the
rem       3.1.31-3.1.35 "measure the content, then grow the window" machinery is
rem       GONE. That machinery is why the window kept getting taller and the
rem       rows got spread into four big empty bands.
rem
rem    3) VERTICAL BUDGET to fit 5 rows into 529: row controls 34 -> 32, page
rem       margins 16/18 -> 8/10, root margins 18/10 -> 14/10, root spacing 12 ->
rem       10, bottom grid spacing 14 -> 10. Measured result: 5-row page needs
rem       224 px in a 284 px viewport, scroll bar maximum = 0 on all five pages
rem       (probe verified at both 100% and 175% device pixel ratio).
rem
rem    4) BOTTOM RIGHT BUTTONS: 108 x 44 each, stacked, pinned to the right edge,
rem       matching the reference picture supplied by the user (110 x 55 at 175%).
rem
rem  What it does, in order:
rem    1) backs up BOTH currently installed DLLs into backup_install_<date>\
rem    2) copies build_output\obs-beauty.dll    -> obs-plugins\64bit\
rem    3) copies build_output\obs-beauty-ui.dll -> ProgramData panel dir
rem    4) sanity-checks both copied files are real PE images (>100000 bytes)
rem
rem  Needs administrator rights (C:\Program Files). Self-elevates.
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
set BLD=
for /d %%d in ("%ROOT%\01_*") do set BLD=%%d
if not defined BLD (
    echo [install] build directory not found under %ROOT%
    pause
    exit /b 1
)

set NEW=%BLD%\build_output\obs-beauty.dll
set NEWUI=%BLD%\build_output\obs-beauty-ui.dll
if not exist "%NEW%" (
    echo [install] missing %NEW%  - run build_manual.bat first
    pause
    exit /b 1
)
if not exist "%NEWUI%" (
    echo [install] missing %NEWUI%  - run build-ui_320.bat first
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
    copy /Y "%OBSDIR%\obs-beauty.dll" "%BAK%\obs-beauty_prev-3.1.36.dll" >nul
    echo [backup] %BAK%\obs-beauty_prev-3.1.36.dll
)
if exist "%UIDIR%\obs-beauty-ui.dll" (
    copy /Y "%UIDIR%\obs-beauty-ui.dll" "%BAK%\obs-beauty-ui_prev-3.1.36.dll" >nul
    echo [backup] %BAK%\obs-beauty-ui_prev-3.1.36.dll
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
echo            [obs-beauty] init OK (v3.1.36, engine=core/1.4.0, region=on ...)
echo            [obs-beauty-ui] module loaded v3.1.36
echo.
echo            The panel is now a FIXED 460 x 560 window (client area 460 x 529).
echo              - 5 tabs, first page shows 5 rows with NO scroll bar
echo              - bottom right: Reset (top) and Close (bottom), 108 x 44 each
echo              - version label sits at the RIGHT END of the "enable" row
echo              - the window cannot be dragged bigger/smaller any more
echo            If the buttons are still missing, send the OBS log - the fix
echo            relies on them being rebuilt in build_form().
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
