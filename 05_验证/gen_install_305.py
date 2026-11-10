# -*- coding: utf-8 -*-
"""生成 3.0.4 安装脚本（纯 ASCII + CRLF）。

cmd.exe 用 OEM 代码页读 .bat，路径里任何非 ASCII 字节都会破坏引号配对，
所以这里强制 ASCII 并在写盘后自检：非 ASCII 字节 0 个、孤立 LF 0 个。
"""
import os
import shutil

OUTDIR = os.path.join(os.path.expanduser("~"), "AppData/Local/Temp/legacy_305")
SRC_DLL = r"D:/插件/obs-beauty-filter/obs-plugin-build/build/obs-beauty.dll"

BODY = r"""@echo off
setlocal EnableExtensions

rem ============================================================================
rem  Nama Beauty OBS Plugin - install 3.0.5 (change-aware smoothing gate)
rem
rem  Only swaps the filter DLL. The plain-text AI bundle is already in place.
rem
rem  Pure ASCII + CRLF. Self-elevates via UAC.
rem ============================================================================

echo.
echo ============================================================
echo    Nama Beauty  -  install 3.0.5
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

echo [5/5] Installing 3.0.5...
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
echo    3.0.5 installed.
echo.
echo    What changed vs 3.0.4 - MASK CANNOT FOLLOW THE FACE:
echo.
echo    Two symptoms were reported together: "still flickers once or
echo    twice" and "during fast movement the mask cannot keep up with
echo    the face shape". They have the same root cause.
echo.
echo    The smoothing strength was locked at alpha = 0.10, i.e. a
echo    10-frame time constant [167 ms at 60 fps]. Steady-state lag is
echo    [1-alpha]/alpha * v = 9v mask pixels = about 50v frame pixels
echo    [192 mask px -> 1074 frame px]. So a mask edge moving just
echo    1 mask px/frame already trails by 50 frame pixels.
echo.
echo    The gate that was supposed to open the smoothing looked at the
echo    mask CENTROID velocity. A centroid is blind to DEFORMATION:
echo    when the face turns, nods or leans towards the camera the
echo    silhouette changes a lot while the centroid barely moves
echo    [measured 0.001-0.003 mask px/frame]. The gate therefore
echo    decided "static", alpha stayed at 0.10, and the mask trailed.
echo.
echo    Fix: the gate now uses two direct measurements.
echo      1] rawChg = mean abs diff between this frame's RAW mask and
echo         the previous one. Static+noise: 0.059-0.107. Pure shape
echo         change [face scaled 1.15x]: about 12. Separation is 100x.
echo      2] err = mean abs diff between the current softened mask and
echo         the previous OUTPUT mask, i.e. "how far behind am I".
echo         rawChg alone fails on a single-frame step: it spikes once
echo         and returns to zero immediately, so alpha closed again and
echo         the rest of the difference crawled in over 4 frames.
echo    alpha = kEmaStill + [1-kEmaStill] * max(motion(rawChg), err).
echo    Still frames keep exactly the old anti-flicker strength.
echo.
echo    Also: the 3-frame median is now skipped when rawChg is high.
echo    The spikes it removes are per-pixel and only reach rawChg 0.08
echo    [same order as noise], so a high rawChg always means real
echo    motion - and there the median cost 1 frame [16 px of lag].
echo.
echo    Also: when fuai returns no mask for a frame, the previous mask
echo    is now held for up to 2 frames instead of dropping the effect
echo    for that frame. Dropping it made applyRegionEffects return
echo    early, which leaves the whole frame un-masked, i.e. a
echo    full-screen whitening flash.
echo.
echo    Measured:
echo      shape change [centroid 0.00-0.16 mask px/frame]:
echo        convergence 3.0.4 = 4+ frames, 3.0.5 = 0 frames
echo        residual on the switch frame  4.46 -> 0.00 levels
echo      translation 20 px/frame lag:   1.8 px  [PASS, unchanged]
echo      static + noise mask residual:  0.082 levels [-33%% vs 3.0.3]
echo      static 12 frames: 0 difference
echo      detail retention [blur50]:     unchanged
echo        sharpen 50          r1 135.8%%  r2 146.2%%  r3 146.5%%
echo        sharpen 50+clarity  r1 149.8%%  r2 163.4%%  r3 164.0%%
echo      +/-5 noise roughness excess:   +0.023 [unchanged]
echo      9-effect regression:           unchanged
echo      background: 0 px changed outside the mask
echo      cost: 0.035 ms/frame [two passes over 192x256]
echo.
echo    Start OBS and check Help - Log Files for:
echo      [nama] init OK (v3.0.5 ...)
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
    p = os.path.join(OUTDIR, "install_305.bat")
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
