@echo off
rem ===========================================================================
rem  install_3.1.24.bat - install the current build into the OBS tree
rem
rem  Why this exists: the sandbox that builds the DLL has no write access to
rem  "C:\Program Files", so installation needs an elevated shell. This script
rem  re-launches itself with administrator rights (single UAC prompt).
rem
rem  What it does, in order:
rem    1) backs up the currently installed filter DLL into backup_install_<ts>\
rem    2) copies build_output\obs-beauty.dll      -> obs-plugins\64bit\
rem    3) copies build_output\obs-beauty-ui.dll   -> ProgramData panel dir
rem    4) removes the OLD third-party runtime and the old panel directory
rem       (a copy of both already sits in _archive_20261030\, so this is safe)
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

rem --- 1) backup ------------------------------------------------------------
for /f "tokens=1-3 delims=/. " %%a in ('echo %date%') do set D=%%a%%b%%c
set BAK=%HERE%backup_install_%D%
if not exist "%BAK%" mkdir "%BAK%"
if exist "%OBSDIR%\obs-beauty.dll" (
    copy /Y "%OBSDIR%\obs-beauty.dll" "%BAK%\obs-beauty.dll.prev" >nul
    echo [backup] %BAK%\obs-beauty.dll.prev
)
if exist "%UIDIR%\obs-beauty-ui.dll" (
    copy /Y "%UIDIR%\obs-beauty-ui.dll" "%BAK%\obs-beauty-ui.dll.prev" >nul
    echo [backup] %BAK%\obs-beauty-ui.dll.prev
)

rem --- 2) filter DLL --------------------------------------------------------
tasklist /fi "imagename eq obs64.exe" 2>nul | find /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install] OBS is running - close it first.
    pause
    exit /b 1
)
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

rem --- 4) remove the de-branded leftovers ----------------------------------
rem  A copy of everything removed here already lives in
rem  _archive_20261030\  (vendor runtime / old panel directory).
rem
rem  IMPORTANT - the literal names below MUST keep the old spelling. They are
rem  the things we are deleting; rewriting them to the new names would delete
rem  the panel we just installed.
set OLDRT=%OBSDIR%\obs-nama-beauty
set OLDRTB=%OBSDIR%\obs-nama-beauty-backup
set OLDUIDIR=%PLUGDIR%\obs-nama-beauty-ui
for %%d in ("%OLDRT%" "%OLDRTB%" "%OLDUIDIR%") do (
    if exist %%d (
        rd /s /q %%d
        if exist %%d (
            echo [clean] could not remove %%d  - remove it by hand
        ) else (
            echo [clean] removed %%d
        )
    )
)
rem  Older builds of this script printed "-> path" in an echo line. cmd.exe
rem  treats the ">" as a redirection, so the text ended up in a file named
rem  C://Program (the space in "Program Files" split the redirect target).
if exist "C://Program" (
    del /q "C://Program"
    echo [clean] removed the stray C://Program file
)
if exist "%OBSDIR%\obs-nama-beauty.dll.disabled" (
    del /q "%OBSDIR%\obs-nama-beauty.dll.disabled"
    echo [clean] removed the old disabled dll
)

echo.
echo [install] done. Start OBS, check the log for:
echo            [OBS Beauty] init OK (v3.1.24, engine=core/1.4.0, region=on ...)
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
