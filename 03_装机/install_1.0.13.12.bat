rem ===========================================================================
rem  install_1.0.13.12.bat - OVERWRITE the installed CPU filter + UI dll with 1.0.13.12
rem
rem  1.0.13.12 changes the FILTER SOURCE (code-review fixes D1 / D2):
rem    D1 removes a data race between the param thread and the render thread;
rem  The pixel path is unchanged, but the DLL bytes differ from 1.0.13.12.
rem
rem  Right-click -> "Run as administrator". This file CANNOT work without an
rem  elevated token: C:\ProgramData\obs-studio\plugins grants BUILTIN\Users
rem  (CI)(WD,AD) -- create-only, no write and no delete on existing files.
rem
rem  What it does:
rem    0) refuse while obs64.exe is alive (the dlls are mapped read-only)
rem    1) back up whatever is installed now to _backup_1312\ (if not there)
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
for /d %%d in ("%ROOT%\02_*") do if exist "%%d\build_1.0.13.12\obs-beauty.dll" set BUILD=%%d\build_1.0.13.12
if not defined BUILD (
    echo [install142] build_1.0.13.12 not found under %ROOT%\02_*
    pause
    exit /b 1
)

set PLUG=C:\ProgramData\obs-studio\plugins
set FDIR=%PLUG%\obs-beauty\bin\64bit
set UDIR=%PLUG%\obs-beauty-ui\bin\64bit

rem --- 0) OBS must be closed ------------------------------------------------
tasklist /fi "imagename eq obs64.exe" /nh 2>nul | findstr /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [install142] OBS is RUNNING. Close OBS completely, then run again.
    pause
    exit /b 1
)

rem --- 1) back up whatever is installed now --------------------------------
if not exist "%HERE%_backup_1312\bin64" mkdir "%HERE%_backup_1312\bin64"
if not exist "%HERE%_backup_1312\ui64"  mkdir "%HERE%_backup_1312\ui64"
if exist "%FDIR%\obs-beauty.dll"    copy /Y "%FDIR%\obs-beauty.dll"    "%HERE%_backup_1312\bin64\" >nul
if exist "%UDIR%\obs-beauty-ui.dll" copy /Y "%UDIR%\obs-beauty-ui.dll" "%HERE%_backup_1312\ui64\"  >nul

rem --- 2) overwrite --------------------------------------------------------
copy /Y "%BUILD%\obs-beauty.dll"    "%FDIR%\obs-beauty.dll"    >nul
if errorlevel 1 (
    echo [install142] FAILED to write filter dll - not elevated?
    pause
    exit /b 1
)
copy /Y "%BUILD%\obs-beauty-ui.dll" "%UDIR%\obs-beauty-ui.dll" >nul
if errorlevel 1 (
    echo [install142] FAILED to write ui dll - not elevated?
    pause
    exit /b 1
)

echo [install142] OK
certutil -hashfile "%FDIR%\obs-beauty.dll" MD5 | findstr /v ":"
certutil -hashfile "%UDIR%\obs-beauty-ui.dll" MD5 | findstr /v ":"
echo [install142] Compare these two MD5s with the ones in the build_1.0.13.12 folder.
echo [install142] Now start OBS; the init line must read v1.0.13.12.
pause
exit /b 0
