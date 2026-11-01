@echo off
rem ===========================================================================
rem  install_3.1.37.bat - install filter + panel for 3.1.37
rem
rem  WHAT CHANGED IN 3.1.37 (panel only; the filter is rebuilt just to keep the
rem  same version number - its algorithm code is untouched):
rem
rem    1) FIXED SIZE IS GONE. 3.1.36 pinned the window with setFixedSize(460,529)
rem       so it could not be dragged at all. Now:
rem         - setMinimumSize(360, 420) instead of setFixedSize
rem         - the three places that force-resized the window are all removed
rem           (constructor / QEvent::Show / end of build_form). Deleting only
rem           the setFixedSize would NOT have been enough: re-activating the
rem           window or moving a slider re-applied 460x529 and snapped the
rem           user's size back.
rem
rem    2) NEW: window geometry is REMEMBERED.
rem         - file: APPDATA\obs-studio\plugin_config\obs-beauty-ui\ui.ini
rem           (path comes from obs_module_config_path, so OBS portable mode
rem           carries it along; nothing is written to the registry or to OBS's
rem           own global.ini)
rem         - stores saveGeometry() as base64 (size + position + maximized +
rem           which screen) plus plain w/h as a fallback
rem         - written 800 ms after the user stops dragging/resizing, and again
rem           on close, so a hard-killed OBS does not lose the size
rem         - on restore the geometry is validated: if it no longer intersects
rem           any screen by at least 80x30 (monitor unplugged, DPI changed) it
rem           is discarded and the window falls back to 460x529 centered
rem
rem    3) THE RESET BUTTON (bottom right) NOW ALSO RESETS THE WINDOW SIZE.
rem       That merge was an explicit user request. Clicking it resets the
rem       filter parameters AND puts the window back to 460x529 centered AND
rem       clears the stored geometry in ui.ini.
rem
rem    4) Form content is now anchored TOP instead of vertically centered, so
rem       dragging the window taller adds empty space at the bottom instead of
rem       floating the whole parameter block into the middle of the screen.
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
    copy /Y "%OBSDIR%\obs-beauty.dll" "%BAK%\obs-beauty_prev-3.1.37.dll" >nul
    echo [backup] %BAK%\obs-beauty_prev-3.1.37.dll
)
if exist "%UIDIR%\obs-beauty-ui.dll" (
    copy /Y "%UIDIR%\obs-beauty-ui.dll" "%BAK%\obs-beauty-ui_prev-3.1.37.dll" >nul
    echo [backup] %BAK%\obs-beauty-ui_prev-3.1.37.dll
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
echo            [obs-beauty] init OK (v3.1.37, engine=core/1.4.0, region=on ...)
echo            [obs-beauty-ui] module loaded v3.1.37
echo.
echo            The panel window is now RESIZABLE and remembers its size (default 460x529).
echo              - 5 tabs, first page shows 5 rows with NO scroll bar
echo              - bottom right: Reset (top) and Close (bottom), 108 x 44 each
echo              - version label sits at the RIGHT END of the "enable" row
echo              - drag any edge to resize; size and position are remembered
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
