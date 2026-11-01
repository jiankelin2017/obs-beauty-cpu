@echo off
setlocal EnableExtensions

rem ============================================================================
rem  OBS Beauty OBS Plugin - uninstaller
rem
rem  Removes exactly what BeautySetup.exe installs:
rem    1. <OBS>\obs-plugins\64bit\obs-beauty.dll
rem    2. <OBS>\obs-plugins\64bit\obs-beauty\   (SDK runtime + bundles)
rem    3. %ProgramData%\obs-studio\plugins\obs-beauty-ui\
rem    4. the two "obs-beauty*" module entries in
rem       %APPDATA%\obs-studio\plugin_manager\modules.json
rem
rem  Nothing else is touched: the OBS core plugins, obsplus and
rem  obs-multi-rtmp stay exactly as they are.
rem
rem  Usage:   uninstall.bat [OBS_DIR]
rem           OBS_DIR                  optional, auto-detected from the registry
rem           BEAUTY_UNINST_OBS          env override for OBS_DIR
rem           BEAUTY_UNINST_UI           env override for the UI directory
rem           BEAUTY_UNINST_MODJSON      env override for modules.json
rem           BEAUTY_UNINST_DRYRUN=1     print every action, delete nothing
rem           BEAUTY_UNINST_NOELEVATE=1  skip the UAC re-launch (test builds only)
rem
rem  Auto-elevates: the Program Files part needs admin rights.
rem  NOTE: keep this file pure ASCII with CRLF line endings.
rem ============================================================================

echo.
echo ============================================================
echo    OBS Beauty Filter + Top Menu Panel  -  Uninstaller
echo ============================================================
echo.

rem ---------------------------------------------- remember the OBS directory
rem An elevated re-launch loses the command line, so the directory is
rem carried through the environment instead.
if "%~1"=="" goto :no_arg
if not defined BEAUTY_UNINST_OBS set "BEAUTY_UNINST_OBS=%~1"
:no_arg

rem ---------------------------------------------- self elevation
rem "net session" only succeeds with a full admin token; under a filtered
rem UAC token it fails, which is exactly the test we need here.
net session >nul 2>&1
if errorlevel 1 if not defined BEAUTY_UNINST_NOELEVATE (
    echo [i] <user> rights are needed for the Program Files part.
    echo     A UAC prompt will appear...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    if errorlevel 1 (
        echo [ERROR] Could not start the elevated copy.
        echo         Right-click this file and choose "Run as administrator".
        echo.
        pause
        exit /b 1
    )
    exit /b 0
)

rem ---------------------------------------------- locate OBS
echo [1/6] Locating OBS...
if not defined BEAUTY_UNINST_OBS (
    for /f "tokens=2,*" %%K in ('reg query "HKLM\SOFTWARE\OBS Studio" /ve 2^>nul ^| "%SystemRoot%\System32\find.exe" /i "REG_SZ"') do set "BEAUTY_UNINST_OBS=%%L"
)
if not defined BEAUTY_UNINST_OBS for /f "tokens=2,*" %%K in ('reg query "HKLM\SOFTWARE\WOW6432Node\OBS Studio" /ve 2^>nul ^| "%SystemRoot%\System32\find.exe" /i "REG_SZ"') do set "BEAUTY_UNINST_OBS=%%L"
if not defined BEAUTY_UNINST_OBS set "BEAUTY_UNINST_OBS=C:\Program Files\obs-studio"
if not defined BEAUTY_UNINST_UI set "BEAUTY_UNINST_UI=%ProgramData%\obs-studio\plugins\obs-beauty-ui"
echo         OBS root: %BEAUTY_UNINST_OBS%
echo         UI root:  %BEAUTY_UNINST_UI%

set "PLUGDIR=%BEAUTY_UNINST_OBS%\obs-plugins\64bit"
set "FILTERDLL=%PLUGDIR%\obs-beauty.dll"
set "RTDIR=%PLUGDIR%\obs-beauty"
if not defined BEAUTY_UNINST_MODJSON (
    set "MODJSON=%APPDATA%\obs-studio\plugin_manager\modules.json"
) else (
    set "MODJSON=%BEAUTY_UNINST_MODJSON%"
)

rem ---------------------------------------------- guard: OBS must be closed
echo [2/6] Checking that OBS is not running...
rem NOTE: find/tasklist are called with their full path - a Git Bash on PATH
rem would otherwise shadow find.exe with the MSYS build, which returns a
rem bogus status.
"%SystemRoot%\System32\tasklist.exe" /fi "imagename eq obs64.exe" 2>nul | "%SystemRoot%\System32\find.exe" /i "obs64.exe" >nul
if not errorlevel 1 (
    echo.
    echo [ERROR] OBS is running right now and would keep the files locked.
    echo         Close OBS completely, then run this uninstaller again.
    echo.
    pause
    exit /b 1
)
echo         OBS is not running.

rem ---------------------------------------------- inventory
echo [3/6] Inventory of the files to be removed...
set "FCOUNT=0"
if exist "%RTDIR%" for /r "%RTDIR%" %%F in (*) do set /a FCOUNT+=1
echo         filter DLL: %FILTERDLL%
if exist "%FILTERDLL%" (echo           ^(present^)) else (echo           ^(not installed^))
echo         SDK dir:    %RTDIR%
if exist "%RTDIR%" (echo           ^(present, %FCOUNT% files^)) else (echo           ^(not installed^))
echo         UI dir:     %BEAUTY_UNINST_UI%
if exist "%BEAUTY_UNINST_UI%" (echo           ^(present^)) else (echo           ^(not installed^))
echo         registry:   %MODJSON%
if exist "%MODJSON%" (echo           ^(present, 2 entries to remove^)) else (echo           ^(nothing to do^))

if not exist "%FILTERDLL%" if not exist "%RTDIR%" if not exist "%BEAUTY_UNINST_UI%" (
    echo.
    echo [i] Nothing is installed - nothing to do.
    echo.
    pause
    exit /b 0
)

echo.
echo ============================================================
echo    The items above will be DELETED.
echo    modules.json is backed up next to itself first.
echo    OBS itself and every other plugin stay untouched.
echo ============================================================
echo.
choice /c YN /m "Delete the OBS Beauty plugin now"
if errorlevel 2 (
    echo.
    echo Cancelled by the user. Nothing was deleted.
    echo.
    pause
    exit /b 0
)

rem ---------------------------------------------- delete
echo.
echo [4/6] Removing files...
if defined BEAUTY_UNINST_DRYRUN (
    echo [DRY-RUN] del /f /q "%FILTERDLL%"
    echo [DRY-RUN] rmdir /s /q "%RTDIR%"
    echo [DRY-RUN] rmdir /s /q "%BEAUTY_UNINST_UI%"
) else (
    if exist "%FILTERDLL%" del /f /q "%FILTERDLL%"
    if errorlevel 1 echo [WARN] could not delete %FILTERDLL%
    if exist "%RTDIR%" rmdir /s /q "%RTDIR%"
    if errorlevel 1 echo [WARN] could not delete %RTDIR%
    if exist "%BEAUTY_UNINST_UI%" rmdir /s /q "%BEAUTY_UNINST_UI%"
    if errorlevel 1 echo [WARN] could not delete %BEAUTY_UNINST_UI%
)

rem ---------------------------------------------- plugin registry
echo [5/6] Cleaning the OBS plugin registry...
if defined BEAUTY_UNINST_DRYRUN (
    echo [DRY-RUN] copy "%MODJSON%" "%MODJSON%.pre-uninstall.bak"
    echo [DRY-RUN] remove the 2 obs-beauty* entries from modules.json
) else (
    if exist "%MODJSON%" (
        copy /y "%MODJSON%" "%MODJSON%.pre-uninstall.bak" >nul
        rem NOTE: ReadAllText with an explicit UTF8 - Get-Content defaults to the
        rem ANSI code page and would mangle the Chinese display names.
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%MODJSON%'; $j=[System.IO.File]::ReadAllText($p,[System.Text.Encoding]::UTF8) | ConvertFrom-Json; $keep=@($j | Where-Object { $_.module_name -ne 'obs-beauty' -and $_.module_name -ne 'obs-beauty-ui' }); [System.IO.File]::WriteAllText($p, ($keep | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding($false)))"
        if errorlevel 1 echo [WARN] registry cleanup failed - stale entries are harmless, OBS simply ignores them
    ) else (
        echo [i] no modules.json found, nothing to clean
    )
)

rem ---------------------------------------------- verify
echo [6/6] Verifying...
if defined BEAUTY_UNINST_DRYRUN (
    echo [DRY-RUN] verification skipped - no file was touched
    goto :verify_done
)
set "VERR=0"
if exist "%FILTERDLL%" echo [FAIL] still present: %FILTERDLL%
if exist "%FILTERDLL%" set "VERR=1"
if exist "%RTDIR%" echo [FAIL] still present: %RTDIR%
if exist "%RTDIR%" set "VERR=1"
if exist "%BEAUTY_UNINST_UI%" echo [FAIL] still present: %BEAUTY_UNINST_UI%
if exist "%BEAUTY_UNINST_UI%" set "VERR=1"
if "%VERR%"=="0" (echo [OK] every plugin file is gone) else (echo [WARN] some files survived - close OBS and run this again)
:verify_done

if defined BEAUTY_UNINST_DRYRUN (
    echo.
    echo [DRY-RUN] finished. No file was touched.
    echo.
    pause
    exit /b 0
)

echo.
echo ============================================================
echo    Uninstall complete.
echo    Start OBS once: the filter and the top menu are gone.
echo    To install again, run the setup exe.
echo ============================================================
echo.
pause
exit /b 0
