@echo off
rem ---------------------------------------------------------------------------
rem install_314.bat - install the freshly built 3.1.14 filter + panel DLLs.
rem
rem Why a .bat and not a plain copy: the OBS install lives under
rem   C:\Program Files\obs-studio\...  which needs an elevated token.
rem The agent that builds this project runs non-elevated, so the copy has to be
rem started by the user (right click -> Run as administrator).
rem
rem This file is pure ASCII on purpose: a UTF-8 .bat gets read as GBK by cmd.exe
rem and Chinese literals get mangled. All paths below are ASCII; the project root
rem is taken from %~dp0 at runtime, so the Chinese folder name never appears as a
rem literal here.
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
set HERE=%~dp0
set OUT=%HERE%build_output
set TGT_FILTER=C:\Program Files\obs-studio\obs-plugins\64bit\obs-beauty.dll
set TGT_UI=C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\obs-beauty-ui.dll
set BK=%HERE%installed_backup_prev

echo [install] source dir: %OUT%
if not exist "%OUT%\obs-beauty.dll"      ( echo [install] MISSING obs-beauty.dll & goto :fail )
if not exist "%OUT%\obs-beauty-ui_320.dll" ( echo [install] MISSING obs-beauty-ui_320.dll & goto :fail )

rem --- refuse to run while OBS holds the DLL ---
tasklist /FI "IMAGENAME eq obs64.exe" 2>nul | find /I "obs64.exe" >nul
if not errorlevel 1 (
    echo [install] OBS is still running. Close OBS first, then re-run.
    goto :fail
)

rem --- back up whatever is installed right now ---
if not exist "%BK%" mkdir "%BK%"
if exist "%TGT_FILTER%" copy /Y "%TGT_FILTER%" "%BK%\obs-beauty.dll" >nul
if exist "%TGT_UI%"     copy /Y "%TGT_UI%"     "%BK%\obs-beauty-ui.dll" >nul
echo [install] backed up current build to %BK%

rem --- copy the panel first, the filter last ---
rem The filter lives in Program Files and is the step that can fail (elevation),
rem so it goes last: if it fails we roll the panel back and end up with the
rem previous version on both sides instead of a mismatched pair.
copy /Y "%OUT%\obs-beauty-ui_320.dll" "%TGT_UI%" >nul
if errorlevel 1 ( echo [install] FAILED to write panel DLL & goto :fail )
copy /Y "%OUT%\obs-beauty.dll" "%TGT_FILTER%" >nul
if errorlevel 1 (
    echo [install] FAILED to write filter DLL - rolling the panel back
    if exist "%BK%\obs-beauty-ui.dll" copy /Y "%BK%\obs-beauty-ui.dll" "%TGT_UI%" >nul
    goto :fail
)

echo [install] installed:
for %%f in ("%TGT_FILTER%" "%TGT_UI%") do (
    echo    %%~ff  %%~zf bytes
)
echo [install] DONE. Start OBS and check the badge shows v3.1.14.
echo.
pause
exit /b 0

:fail
echo.
echo [install] ABORTED - nothing half-installed by this script beyond the backup.
pause
exit /b 1
