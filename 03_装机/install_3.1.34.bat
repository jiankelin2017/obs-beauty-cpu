@echo off
rem ===========================================================================
rem  install_3.1.34.bat - install filter + panel for 3.1.34
rem
rem  WHAT CHANGED IN 3.1.34 (panel only; the filter is rebuilt just to keep the
rem  same version number, its code is unchanged since 3.1.31):
rem    1) WINDOW SIZE, final: 536 x 611 LOGICAL px.
rem       At 125% Windows scaling that renders as 670 x 764 PHYSICAL px, whose
rem       height/width ratio is 1.1403 - the user's screenshot content area is
rem       810 x 923 physical, ratio 1.1395. Match to 0.07%.
rem       History: 3.1.32 used 670x750 LOGICAL - a unit mistake, since that
rem       number is physical px, so the real window came out 838x938 physical,
rem       25% too big. 3.1.33 fixed the unit (536x600) but was 11 px short,
rem       making the row spacing tighter than the screenshot. 3.1.34 derives
rem       the height from the screenshot ratio: 670 x (923/810) = 763.5 -> 764.
rem    2) version label sits at the RIGHT END of the "enable beauty" row
rem    3) bottom area is a 2x2 grid:
rem          blur algorithm [combo]      Reset
rem          blur mode      [combo]      Close
rem    4) combo boxes use QComboBox::AdjustToContents, so sizeHint equals the
rem       measured width of the LONGEST option - option text is never clipped
rem       (before: "bilateral filter" showed as "bilateralfi" + arrow)
rem    5) parameter rows are spread to fill the page; row height is read from
rem       the real widget height() (sizeHint is ~2px small per row before
rem       polish), so no page gets a scroll bar
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
    copy /Y "%OBSDIR%\obs-beauty.dll" "%BAK%\obs-beauty_3.1.33.dll.prev" >nul
    echo [backup] %BAK%\obs-beauty_3.1.33.dll.prev
)
if exist "%UIDIR%\obs-beauty-ui.dll" (
    copy /Y "%UIDIR%\obs-beauty-ui.dll" "%BAK%\obs-beauty-ui_3.1.33.dll.prev" >nul
    echo [backup] %BAK%\obs-beauty-ui_3.1.33.dll.prev
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
echo            [obs-beauty] init OK (v3.1.34, engine=core/1.4.0, region=on ...)
echo            [obs-beauty-ui] module loaded v3.1.34
echo.
echo            Panel should now be a FIXED window: 536x611 LOGICAL px,
echo            which renders as 670x764 PHYSICAL px at 125% Windows scaling
echo            (height/width 1.1403, matching the screenshot ratio 1.1395).
echo              - 5 tabs: Beauty / Sharpen / Face / Shape / Advanced
echo              - tab labels are Chinese in the UI (English here because this
echo                .bat must stay pure ASCII)
echo              - version label sits at the RIGHT END of the "enable" row
echo              - bottom is a 2x2 grid: blur algorithm + Reset on row 1,
echo                blur mode + Close on row 2
echo              - combo boxes show the FULL option text, no clipped letters
echo              - first page: 5 rows evenly spread, NO scroll bar
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
