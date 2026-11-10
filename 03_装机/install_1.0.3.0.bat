@echo off
rem ===========================================================================
rem  install_1.0.3.0.bat - deploy CPU 1.0.3.0 filter + top-level menu UI
rem
rem  Target is the OBS GLOBAL plugin path (ProgramData), NOT obs-plugins\64bit.
rem
rem  RESOLVED 2026-11-07 (user decision C-1): obs-beauty.nsi, e2e_test.ps1
rem  and build_setup.ps1 now all use this same ProgramData global plugin
rem  path. The historical C:\Program Files\obs-studio\obs-plugins\64bit
rem  flat layout is retired. OBS requires <plugin-dir>\bin\64bit\<plugin-dir>.dll
rem  with the directory name matching the DLL basename.
rem  OBS scans <plugin-dir>/bin/64bit/<plugin-dir>.dll; the directory name MUST
rem  match the DLL basename, otherwise the plugin is silently skipped with no
rem  log line at all (see docs/guides/guide-ui.md section 3).
rem
rem  Layout installed:
rem    ...\plugins\obs-beauty\bin\64bit\obs-beauty.dll
rem    ...\plugins\obs-beauty\bin\64bit\onnxruntime.dll
rem    ...\plugins\obs-beauty\bin\64bit\models\yunet.onnx
rem    ...\plugins\obs-beauty-ui\bin\64bit\obs-beauty-ui.dll
rem
rem  The engine resolves the model relative to its OWN dll directory:
rem  <dll-dir>\models\yunet.onnx, falling back to <dll-dir>\yunet.onnx, and
rem  loads <dll-dir>\onnxruntime.dll (ORT API 20 / 1.20.x required).
rem  See beauty_core.cpp ensureReady() and beauty_onnx.cpp.
rem
rem  No UAC elevation is needed for a FRESH install: ProgramData\obs-studio\plugins
rem  grants BUILTIN\Users Write (create), but the inherited ACE has no DELETE,
rem  so REPLACING an existing dll needs an elevated token. This script refuses
rem  to overwrite; remove/quarantine the old plugin dirs first.
rem
rem  OBS MUST BE CLOSED: the dlls are mapped while OBS is alive.
rem  Keep this file PURE ASCII: cmd.exe reads .bat as GBK, so Chinese-named
rem  source dirs are resolved with wildcards instead of literal text.
rem ===========================================================================
setlocal enabledelayedexpansion

set HERE=%~dp0
set ROOT=%HERE%..

rem --- resolve Chinese-named source directories without non-ASCII literals ---
set BUILDDIR=
for /d %%d in ("%ROOT%\02_*") do set BUILDDIR=%%d
set VALDIR=
for /d %%d in ("%ROOT%\05_*") do set VALDIR=%%d
if not defined BUILDDIR ( echo [install] 02_* build dir not found under %ROOT% & exit /b 1 )
if not defined VALDIR   ( echo [install] 05_* validation dir not found under %ROOT% & exit /b 1 )

set SRCDIR=%BUILDDIR%\build_1.0.3.0
set FILTER_SRC=%SRCDIR%\obs-beauty.dll
set UI_SRC=%SRCDIR%\obs-beauty-ui.dll
set ORT_SRC=%VALDIR%\deps\runtime\onnxruntime.dll
set MODEL_SRC=%VALDIR%\models\yunet.onnx

for %%F in ("%FILTER_SRC%" "%UI_SRC%" "%ORT_SRC%" "%MODEL_SRC%") do (
    if not exist %%F (
        echo [install] missing source file: %%F
        exit /b 1
    )
)

set PLUG=C:\ProgramData\obs-studio\plugins
set FDIR=%PLUG%\obs-beauty\bin\64bit
set UDIR=%PLUG%\obs-beauty-ui\bin\64bit

rem --- 0) refuse while OBS is live ------------------------------------------
set FINDSTR=%SystemRoot%\System32\findstr.exe
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | "%FINDSTR%" /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install] OBS is RUNNING. Close OBS first, then run this again.
    echo [install] Nothing was changed.
    exit /b 1
)

rem --- 1) refuse to overwrite an existing install ----------------------------
if exist "%FDIR%\obs-beauty.dll" (
    echo [install] filter dll already exists: %FDIR%\obs-beauty.dll
    echo [install] Quarantine the old plugin directory first. Nothing was changed.
    exit /b 1
)
if exist "%UDIR%\obs-beauty-ui.dll" (
    echo [install] ui dll already exists: %UDIR%\obs-beauty-ui.dll
    echo [install] Quarantine the old plugin directory first. Nothing was changed.
    exit /b 1
)

rem --- 2) create layout ------------------------------------------------------
if not exist "%FDIR%\models" mkdir "%FDIR%\models"
if not exist "%UDIR%" mkdir "%UDIR%"
if errorlevel 1 (
    echo [install] FAILED to create target directories (check ProgramData ACL)
    exit /b 1
)

rem --- 3) copy four files ----------------------------------------------------
copy /Y "%FILTER_SRC%" "%FDIR%\obs-beauty.dll" >nul
if errorlevel 1 ( echo [install] FAILED: filter dll & exit /b 1 )
copy /Y "%ORT_SRC%"   "%FDIR%\onnxruntime.dll" >nul
if errorlevel 1 ( echo [install] FAILED: onnxruntime dll & exit /b 1 )
copy /Y "%MODEL_SRC%" "%FDIR%\models\yunet.onnx" >nul
if errorlevel 1 ( echo [install] FAILED: yunet model & exit /b 1 )
copy /Y "%UI_SRC%"    "%UDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 ( echo [install] FAILED: ui dll & exit /b 1 )

rem --- 4) sanity check: real PE images, model is non-trivial ----------------
call :check_pe "%FDIR%\obs-beauty.dll" 100000
if errorlevel 1 exit /b 1
call :check_pe "%UDIR%\obs-beauty-ui.dll" 100000
if errorlevel 1 exit /b 1
call :check_pe "%FDIR%\onnxruntime.dll" 100000
if errorlevel 1 exit /b 1
call :check_pe "%FDIR%\models\yunet.onnx" 100000
if errorlevel 1 exit /b 1

echo [install] OK. Four files deployed:
echo   %FDIR%\obs-beauty.dll
echo   %FDIR%\onnxruntime.dll
echo   %FDIR%\models\yunet.onnx
echo   %UDIR%\obs-beauty-ui.dll
echo [install] Hashes:
certutil -hashfile "%FDIR%\obs-beauty.dll" MD5
certutil -hashfile "%UDIR%\obs-beauty-ui.dll" MD5
echo [install] Restart OBS. The top-level menu appears as "Meiyan CPU" in the
echo [install] CPU edition build; open it and choose "Parameters..." to panel.
exit /b 0

:check_pe
for %%A in (%1) do if %%~zA LSS %2 (
    echo [install] sanity check FAILED: %1 is too small (%%~zA bytes)
    exit /b 1
)
exit /b 0
