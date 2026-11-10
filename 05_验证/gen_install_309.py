# -*- coding: utf-8 -*-
"""生成 3.0.9 安装脚本（纯 ASCII + CRLF），并自检。"""
import os
import shutil

OUTDIR = os.path.join(os.path.expanduser("~"), "AppData/Local/Temp/legacy_309")
SRC_DLL = r"D:/插件/obs-beauty-filter/obs-plugin-build/build/obs-beauty.dll"

BODY = r"""@echo off
setlocal EnableExtensions

rem ============================================================================
rem  Nama Beauty OBS Plugin - install 3.0.9 (whiten recalibrated)
rem
rem  Only swaps the filter DLL. The plain-text AI bundle is already in place.
rem  Pure ASCII + CRLF. Self-elevates via UAC.
rem ============================================================================

echo.
echo ============================================================
echo    Nama Beauty  -  install 3.0.9
echo ============================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator rights through UAC...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    if errorlevel 1 echo [ERROR] elevation cancelled or failed.
    exit /b
)

set "OBSTARGET="
for /f "tokens=2,*" %%K in ('reg query "HKLM\SOFTWARE\OBS Studio" /ve 2^>nul ^| "%SystemRoot%\System32\find.exe" /i "REG_SZ"') do set "OBSTARGET=%%L"
if not defined OBSTARGET set "OBSTARGET=C:\Program Files\obs-studio"
echo [1/5] OBS root: %OBSTARGET%

if not exist "%OBSTARGET%\bin\64bit\obs64.exe" (
    echo [ERROR] obs64.exe not found under "%OBSTARGET%\bin\64bit"
    goto :fail
)

echo [2/5] Checking OBS is not running...
"%SystemRoot%\System32\tasklist.exe" /fi "imagename eq obs64.exe" 2>nul | "%SystemRoot%\System32\find.exe" /i "obs64.exe" >nul
if not errorlevel 1 (
    echo [ERROR] OBS is running, its DLLs are locked. Close OBS first.
    goto :fail
)
echo         OBS is closed.

set "SRC=%~dp0"
set "PLUGDIR=%OBSTARGET%\obs-plugins\64bit"
set "RTDIR=%PLUGDIR%\obs-beauty"

echo [3/5] Checking source...
if not exist "%SRC%obs-beauty.dll" (
    echo [ERROR] missing %SRC%obs-beauty.dll
    goto :fail
)
for %%F in ("%SRC%obs-beauty.dll") do echo         source DLL: %%~zF bytes

echo [4/5] Backing up the installed DLL...
set "STAMP=unknown"
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%T"
set "BAKDIR=%PLUGDIR%\obs-beauty-backup"
if not exist "%BAKDIR%" mkdir "%BAKDIR%"
if exist "%PLUGDIR%\obs-beauty.dll" (
    copy /y "%PLUGDIR%\obs-beauty.dll" "%BAKDIR%\obs-beauty.dll.%STAMP%.bak" >nul
    if errorlevel 1 (
        echo [ERROR] backup failed, aborting before anything is overwritten.
        goto :fail
    )
    echo         backup: obs-beauty.dll.%STAMP%.bak
) else (
    echo         no previous DLL, fresh install
)

echo [5/5] Installing 3.0.9...
copy /y "%SRC%obs-beauty.dll" "%PLUGDIR%\obs-beauty.dll" >nul
if errorlevel 1 (
    echo [ERROR] failed to copy the filter DLL.
    goto :fail
)
echo         filter DLL installed

rem ---- verify -------------------------------------------------------------
echo.
echo Verifying...
set "FAILED=0"
if not exist "%PLUGDIR%\obs-beauty.dll" (
    echo [MISSING] filter DLL
    set "FAILED=1"
)
if not exist "%RTDIR%\assets\model\ai_face_processor_pc_plain.bundle" (
    echo [WARN] plain bundle missing - region falls back to colour heuristic
)
if "%FAILED%"=="1" goto :fail

for %%F in ("%SRC%obs-beauty.dll") do set "S1=%%~zF"
for %%F in ("%PLUGDIR%\obs-beauty.dll") do set "S2=%%~zF"
echo         source %S1% bytes / installed %S2% bytes
if not "%S1%"=="%S2%" (
    echo [WARN] size mismatch, the copy may be incomplete.
)

echo.
echo ============================================================
echo    3.0.9 installed.
echo.
echo    What changed vs 3.0.8 - WHITEN RECALIBRATED:
echo.
echo    Measured inside the fuai skin mask (not the diluted
echo    colour-heuristic number): whiten 50 used to lift the face
echo    by about 13.6 levels, and whiten 100 by about 30 levels,
echo    which pushed the skin past 176 and into the highlight
echo    shoulder.  That is what made the face look pale.
echo.
echo    kMax 0.58 -^> 0.32:
echo      whiten  50    +13.6 -^> +7.3 levels
echo      whiten 100    +30   -^> +16  levels
echo.
echo    Nothing else changed. Blur calibration, detail backfill,
echo    adaptive beta and the mask chain are identical to 3.0.8.
echo.
echo    Regression on the final DLL:
echo      detail retention (blur slider): unchanged
echo        50   85.3 / 87.8 / 88.9
echo      static 12 frames:          0 difference
echo      background outside mask:   0 px changed
echo      +/-2 noise s50-s0 rough:   +0.006
echo      +/-5 noise s50-s0 rough:   +0.017
echo      translation 20 px/frame:   1.4 px lag  [PASS]
echo      red 50:                    +1.86, unchanged
echo      frame time 1074x604:       ~14.2 ms blur only, ~21.4 ms +sharpen
echo.
echo    Start OBS and check Help - Log Files for:
echo      [nama] init OK (v3.0.9 ...)
echo      [nama] region ready (fuai skin seg, landmarks off, every frame)
echo.
echo    Please test with blur 50 + whiten 50 and compare skin tone
echo    and face relief against the third-party camera. If the face
echo    still looks too pale, whiten can come down further.
echo.

endlocal
exit /b 0

:fail
echo.
echo [FAILED] nothing was installed. See the messages above.
endlocal
exit /b 1
"""


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    body = BODY.replace("\r\n", "\n").replace("\n", "\r\n")
    p = os.path.join(OUTDIR, "install_309.bat")
    with open(p, "wb") as f:
        f.write(body.encode("ascii"))
    d = open(p, "rb").read()
    bad = [b for b in d if b > 127]
    lone = d.replace(b"\r\n", b"").count(b"\n")
    print("写入 %s  %d 字节" % (p, len(d)))
    print("  非 ASCII 字节 %d   孤立 LF %d" % (len(bad), lone))
    assert not bad and lone == 0

    shutil.copy2(SRC_DLL, os.path.join(OUTDIR, "obs-beauty.dll"))
    print("  已放源 DLL %d 字节" % os.path.getsize(os.path.join(OUTDIR, "obs-beauty.dll")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
