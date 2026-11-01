@echo off
rem ===========================================================================
rem  install_3.1.38.bat - install filter + panel for 3.1.38
rem
rem  WHAT CHANGED IN 3.1.38 (panel only; the filter is rebuilt just to keep the
rem  same version number - its algorithm code is untouched):
rem
rem    1) EVERY CONTROL IS NOW THE SAME HEIGHT (28 logical px).
rem       Before this build the panel showed four different heights at once:
rem         combo box      28.6   (theme: height)
rem         tab pill       31     (padding)
rem         number box     28.6   (theme: height + max-height)
rem         bottom buttons 51     (theme: height + max-height + padding
rem                                + margin-top/bottom)
rem       The cause was NOT our C++ code. OBS's own theme (Yami.obt) computes a
rem       separate height for each widget class, and our panel stylesheet only
rem       overrode padding - so height and margin kept coming from the theme.
rem       On top of that the code carried a SECOND set of numbers
rem       (setFixedHeight(32), setFixedSize(108,44)). A stylesheet height beats
rem       setFixedHeight, so those numbers applied PARTIALLY: width 74 did take
rem       effect (measured 74), height 32 did not (measured 28.6). One
rem       setFixedSize() call, half applied - that is why nothing ever lined up.
rem
rem    2) HOW IT IS FIXED
rem         - height is defined in ONE place: kCtrlH = 26 in the stylesheet,
rem           giving 28 logical px total (26 + 1px border on each side)
rem         - height / min-height / max-height / margin / padding are all
rem           written out, so the theme cannot contribute anything
rem         - all height numbers are DELETED from the C++ code; only widths
rem           remain (combo 74, buttons 74 / 108)
rem         - the checkbox has no border, so it uses kCtrlH+2 to match
rem         - tab pills can only be sized via padding (QTabBar::tab ignores
rem           min-height); measured 27, i.e. 1px shorter than the controls
rem
rem    3) THE OFFLINE PROBE WAS LYING, AND NOW IT DOES NOT
rem       The probe used to paint its own fake theme with no height/margin, so
rem       it could never reproduce the real heights - every "probe looks fine,
rem       installed build looks wrong" round since 3.1.26 came from this.
rem       It now mirrors Yami.obt (height + max-height + margin on buttons,
rem       combo boxes and spin boxes) and prints the measured height of every
rem       widget class; a build only passes when min == max within each class.
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
rem ===========================================================================
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
    copy /Y "%OBSDIR%\obs-beauty.dll" "%BAK%\obs-beauty_prev-3.1.38.dll" >nul
    echo [backup] %BAK%\obs-beauty_prev-3.1.38.dll
)
if exist "%UIDIR%\obs-beauty-ui.dll" (
    copy /Y "%UIDIR%\obs-beauty-ui.dll" "%BAK%\obs-beauty-ui_prev-3.1.38.dll" >nul
    echo [backup] %BAK%\obs-beauty-ui_prev-3.1.38.dll
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
echo            [obs-beauty] init OK (v3.1.38, engine=core/1.4.0, region=on ...)
echo            [obs-beauty-ui] module loaded v3.1.38
echo.
echo            All controls are now the SAME HEIGHT (28 logical px): combos, number boxes,
rem            the refresh button and the two bottom-right buttons.
echo              - 5 tabs, first page shows 5 rows with NO scroll bar
echo              - bottom right: Reset (top) and Close (bottom), 108 x 44 each
echo              - version label sits at the RIGHT END of the "enable" row
echo              - drag any edge to resize; size and position are remembered (3.1.37)
echo            Geometry file: APPDATA\obs-studio\plugin_config\obs-beauty-ui\ui.ini
echo            Delete it to forget the size. Reset button also restores 460x529.
echo            Log lines to look for: "window geometry default|restored: WxH at (X,Y)".
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
