# -*- coding: utf-8 -*-
"""生成 3.0.4 安装脚本（纯 ASCII + CRLF）。

cmd.exe 用 OEM 代码页读 .bat，路径里任何非 ASCII 字节都会破坏引号配对，
所以这里强制 ASCII 并在写盘后自检：非 ASCII 字节 0 个、孤立 LF 0 个。
"""
import os
import shutil

OUTDIR = r"C:/Users/<user>/AppData/Local/Temp/legacy_304"
SRC_DLL = r"D:/插件/obs-beauty-filter/obs-plugin-build/build/obs-beauty.dll"

BODY = r"""@echo off
setlocal EnableExtensions

rem ============================================================================
rem  Nama Beauty OBS Plugin - install 3.0.4 (temporal median on the raw mask)
rem
rem  Only swaps the filter DLL. The plain-text AI bundle is already in place.
rem
rem  Pure ASCII + CRLF. Self-elevates via UAC.
rem ============================================================================

echo.
echo ============================================================
echo    Nama Beauty  -  install 3.0.4
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

echo [5/5] Installing 3.0.4...
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
echo    3.0.4 installed.
echo.
echo    What changed vs 3.0.3 - RESIDUAL BOUNDARY FLICKER:
echo.
echo    3.0.3 lowered the mask EMA still-alpha to 0.10 and the user
echo    reported "still flickers, but less often". So the frequency
echo    went down and the amplitude did not. Measuring 12 frames of
echo    the RAW fuai mask over the transition band [260 px] explains
echo    why:
echo        frame-to-frame abs-delta  mean 10.6  median 3  max 196
echo        dstd/tstd median 0.84   [white noise ~1.41]
echo        sign flip rate 0.59     [white noise ~0.5]
echo    Mostly white-noise-like, so the EMA compresses it 11x
echo    [10.6 -> 0.95]. But the max is 196: isolated spikes. An EMA
echo    can only DILUTE a spike, not delete it: 0.10 * 196 ~ 20, and
echo    20 is exactly the residual max we measured. Those surviving
echo    spikes are the "slower" flicker that is still visible.
echo.
echo    Fix: a 3-frame temporal MEDIAN on the RAW mask, before
echo    soften and before the EMA. The fuai mask is hard binary
echo    [92.65%% exactly 0, 6.88%% exactly 255], so a median of 3
echo    binary samples is a per-pixel majority vote - the standard
echo    answer to binary noise, not a blur. It does not soften the
echo    border and does not weaken the effect.
echo    A median passes a monotone ramp unchanged, so a turning head
echo    keeps its timing; and above kMotionFull [1.5 mask px/frame]
echo    the median is switched off entirely, so fast motion has zero
echo    added lag.
echo.
echo    Measured [same raw sequence, transition band only]:
echo      final mask frame-to-frame residual  0.123 -> 0.085  [-31%%]
echo      residual peak                          5  -> 5 levels
echo      mask lag                               1.8 px  [PASS]
echo.
echo    Unchanged on purpose [verified, no regression]:
echo      mask-only detail retention, blur50:
echo        sharpen 50          r1 135.8%%  r2 146.2%%  r3 146.5%%
echo        sharpen 50+clarity  r1 149.8%%  r2 163.4%%  r3 164.0%%
echo        sharpen 100         r1 186.6%%  r2 201.8%%  r3 200.8%%
echo      9-effect regression identical [whiten +12.39, red +2.97,
echo      sharpen +2.17]
echo      static 12 frames: 0 difference
echo      background: 0 px changed outside the mask
echo      cost: 0.017 ms/frame, +147 KB buffers
echo.
echo    Start OBS and check Help - Log Files for:
echo      [nama] init OK (v3.0.4 ...)
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
    p = os.path.join(OUTDIR, "install_304.bat")
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
