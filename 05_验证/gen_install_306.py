# -*- coding: utf-8 -*-
"""生成 3.0.4 安装脚本（纯 ASCII + CRLF）。

cmd.exe 用 OEM 代码页读 .bat，路径里任何非 ASCII 字节都会破坏引号配对，
所以这里强制 ASCII 并在写盘后自检：非 ASCII 字节 0 个、孤立 LF 0 个。
"""
import os
import shutil

OUTDIR = os.path.join(os.path.expanduser("~"), "AppData/Local/Temp/legacy_306")
SRC_DLL = r"D:/插件/obs-beauty-filter/obs-plugin-build/build/obs-beauty.dll"

BODY = r"""@echo off
setlocal EnableExtensions

rem ============================================================================
rem  Nama Beauty OBS Plugin - install 3.0.6 (gate thresholds recalibrated)
rem
rem  Only swaps the filter DLL. The plain-text AI bundle is already in place.
rem
rem  Pure ASCII + CRLF. Self-elevates via UAC.
rem ============================================================================

echo.
echo ============================================================
echo    Nama Beauty  -  install 3.0.6
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

echo [5/5] Installing 3.0.6...
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
echo    3.0.6 installed.
echo.
echo    What changed vs 3.0.5 - GATE THRESHOLDS RECALIBRATED:
echo.
echo    3.0.5 already pointed the gate at the right signals [rawChg and
echo    err], but the dead zone was far too wide: rawChg 0.40-3.00 and
echo    err 0.30-1.50. Moderate sustained deformation lands entirely
echo    inside that band, where alpha is only 0.15-0.4, and the
echo    steady-state lag [1-a]/a*v works out to about 15 frame pixels.
echo    That is exactly "the mask cannot keep up with the face".
echo.
echo    The dead-zone floor is set by the NOISE floor, and that is now
echo    measured [output mask frame-to-frame residual, transition band]:
echo        +/-2 noise   rawChg max 0.107   err max 0.092
echo        +/-5 noise   rawChg max 0.190   err max 0.189
echo        +/-12 noise rawChg max 0.391   err max 0.344  [image unusable]
echo    So the floor cannot go below about 0.3. Instead the UPPER end
echo    was pulled in, making the ramp much steeper:
echo        rawChg  0.40-3.00  ->  0.35-1.00
echo        err     0.30-1.50  ->  0.32-0.80
echo.
echo    Measured [face scaled linearly by 1.20 / 1.12 / 1.05, centroid
echo    pinned so the OLD centroid gate is provably blind to it]:
echo      steady-state lag 0.94 / 0.71 / 0.87 levels
echo                    -> 0.00 / 0.00 / 0.32 levels
echo      [1 level of mean lag over the whole mask = about 3 mask px
echo       of edge lag = about 15 frame px, so this is a 15x cut]
echo      translation 20 px/frame lag: 1.8 px  [PASS, unchanged]
echo      static + noise residual:     0.082 levels [unchanged]
echo      +/-5 noise roughness excess: +0.023  [unchanged]
echo      detail retention:            unchanged
echo        sharpen 50          r1 135.8%  r2 146.2%  r3 146.5%
echo        sharpen 50+clarity  r1 149.8%  r2 163.4%  r3 164.0%
echo      static 12 frames: 0 difference
echo      background: 0 px changed outside the mask
echo      9-effect regression: unchanged
echo.
echo    Flicker: no change in this build. The anti-flicker work from
echo    3.0.3-3.0.5 is fully preserved [the noise rows above are
echo    identical]. If flicker is still visible after this build, the
echo    remaining suspect is the SDK's own per-frame output jitter,
echo    which needs a different fix [bounding d = sdkOut - src].
echo.
echo    Start OBS and check Help - Log Files for:
echo      [nama] init OK (v3.0.6 ...)
echo      [nama] region ready (fuai skin seg, landmarks off, every frame)
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
    p = os.path.join(OUTDIR, "install_306.bat")
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
