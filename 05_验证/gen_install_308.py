# -*- coding: utf-8 -*-
"""生成 3.0.8 安装脚本（纯 ASCII + CRLF），并自检。"""
import os
import shutil

OUTDIR = os.path.join(os.path.expanduser("~"), "AppData/Local/Temp/legacy_308")
SRC_DLL = r"D:/插件/obs-beauty-filter/obs-plugin-build/build/obs-beauty.dll"

BODY = r"""@echo off
setlocal EnableExtensions

rem ============================================================================
rem  Nama Beauty OBS Plugin - install 3.0.8 (same-notch calibration)
rem
rem  Only swaps the filter DLL. The plain-text AI bundle is already in place.
rem  Pure ASCII + CRLF. Self-elevates via UAC.
rem ============================================================================

echo.
echo ============================================================
echo    Nama Beauty  -  install 3.0.8
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

echo [5/5] Installing 3.0.8...
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
echo    3.0.8 installed.
echo.
echo    What changed vs 3.0.7 - BLUR STRENGTH MOVED TO CPU:
echo.
echo    Measured on the real bundle: blur_level is NOT a strength
echo    knob. Detail retention inside the skin mask, blur=50:
echo      blur_level 0.6  -^> 66.3   3.0 -^> 72.0   6.0 -^> 78.1
echo      panel blur 0 -^> 100.0    panel blur 1 -^> 68.1
echo    So the whole 0..100 slider only spans 66..78, and the real
echo    switch is off/on at 0.  blur_scale / heavy_blur do not
echo    exist in this bundle.  The real lever is blur_type:
echo      weak 94.5 / gauss 84.6 / bilateral 72.0
echo.
echo    3.0.8 therefore blends the SDK result back toward the
echo    source by t = blur / 100, inside the same pass that swaps
echo    B and R, so it costs nothing measurable.
echo.
echo    Detail retention (1 / 2 / 3 px), blur slider:
echo      0    100.0 / 100.0 / 100.0
echo      10    98.1 /  98.2 /  98.6
echo      25    94.0 /  94.7 /  95.4
echo      50    85.3 /  87.8 /  88.9   (was 72.0 / 76.6 / 79.1)
echo      75    81.6 /  83.4 /  84.7
echo     100    78.1 /  79.8 /  81.0
echo    Same notch now keeps far more skin texture and face relief.
echo.
echo    Whitening at 50 also came down (kMax 0.70 -^> 0.58):
echo      dLuma +8.19 -^> +6.75 on the same frame, so the face is
echo      no longer lifted brighter than the background.
echo.
echo    Regression on the final DLL:
echo      static 12 frames:          0 difference
echo      background outside mask:   0 px changed
echo      +/-2 noise s50-s0 rough:   +0.006
echo      +/-5 noise s50-s0 rough:   +0.017  (3.0.7 was +0.023)
echo      translation 20 px/frame:   1.7 px lag  [PASS]
echo      9-effect regression:       red unchanged at +1.86
echo      frame time 1074x604:       ~14.7 ms blur only, ~22.7 ms +sharpen
echo.
echo    Note: sharpen is additive on top of a sharper base now, so
echo    blur 50 + sharpen 50 reads about 148 pct of source detail
echo    instead of 136 pct.  Lower the sharpen slider if it looks
echo    too crisp.
echo.
echo    Start OBS and check Help - Log Files for:
echo      [nama] init OK (v3.0.8 ...)
echo      [nama] region ready (fuai skin seg, landmarks off, every frame)
echo.
echo    Please test with the same settings as the third-party camera:
echo    blur 50 + whiten 50, and compare skin texture and face relief.
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
    p = os.path.join(OUTDIR, "install_308.bat")
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
