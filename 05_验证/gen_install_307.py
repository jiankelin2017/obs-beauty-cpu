# -*- coding: utf-8 -*-
"""生成 3.0.7 安装脚本（纯 ASCII + CRLF），并自检。"""
import os
import shutil

OUTDIR = r"C:/Users/<user>/AppData/Local/Temp/legacy_307"
SRC_DLL = r"D:/插件/obs-beauty-filter/obs-plugin-build/build/obs-beauty.dll"

BODY = r"""@echo off
setlocal EnableExtensions

rem ============================================================================
rem  Nama Beauty OBS Plugin - install 3.0.7 (per-pixel adaptive detail EMA)
rem
rem  Only swaps the filter DLL. The plain-text AI bundle is already in place.
rem  Pure ASCII + CRLF. Self-elevates via UAC.
rem ============================================================================

echo.
echo ============================================================
echo    Nama Beauty  -  install 3.0.7
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

echo [5/5] Installing 3.0.7...
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
echo    3.0.7 installed.
echo.
echo    What changed vs 3.0.6 - DETAIL LAYER ADAPTIVE BETA:
echo.
echo    The detail backfill (fine 1-2px + mid 3-7px) used to run its
echo    temporal EMA with a GLOBAL beta. The gate watched mask motion,
echo    but glasses frames and other high-contrast texture move a lot
echo    at full resolution while the 192x256 mask barely changes. So
echo    the gate stayed in still mode and several layers with
echo    different time constants produced multiple delayed ghosts.
echo.
echo    3.0.7 now also looks at each pixel's own |delta h|:
echo      flat skin   small delta  -^> keep the strong still smoothing
echo      glasses etc large delta  -^> beta rises to 1, no ghost
echo    Final thresholds: fine 10/12, mid 6/10 (mid is 1/64 fixed).
echo.
echo    DLL-internal detail probe, slow face movement, strong edges:
echo      old global beta      fine 15.5 / mid 15.0 levels
echo      fine 10/16 mid 6/16  fine  2.35 / mid  2.41 levels
echo      fine 10/12 mid 6/10  fine  1.14 / mid  1.14 levels  [final]
echo    +/-5 still-noise detail residual is unchanged between the
echo    last two rows, so still denoising is not traded for motion.
echo.
echo    Full regression on the final DLL:
echo      static 12 frames:            0 difference
echo      +/-2 mask residual:          0.082 levels
echo      +/-5 noise roughness excess: +0.023
echo      detail retention:            unchanged
echo        sharpen 50          r1 135.8%  r2 146.2%  r3 146.5%
echo        sharpen 50+clarity  r1 149.8%  r2 163.4%  r3 164.0%
echo      background:                  0 px changed outside the mask
echo      translation 20 px/frame:     1.8 px lag [PASS]
echo      step deformation:            0 frame settle
echo      sustained deformation:       0.00 / 0.00 / 0.32 levels
echo      9-effect regression:         unchanged
echo      frame time 1074x604:         ~15 ms blur only, ~24 ms +sharpen
echo.
echo    Start OBS and check Help - Log Files for:
echo      [nama] init OK (v3.0.7 ...)
echo      [nama] region ready (fuai skin seg, landmarks off, every frame)
echo.
echo    Please test: hold still, then start moving slowly; watch the
echo    glasses frame and cheek contour for delayed double edges.
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
    p = os.path.join(OUTDIR, "install_307.bat")
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
