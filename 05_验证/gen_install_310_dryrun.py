# -*- coding: utf-8 -*-
"""Dry-run variant of the v3.0.10 installer: same logic, DST redirected to a
scratch directory so it can be validated WITHOUT elevation and WITHOUT
touching the real plugin. Run gen_install_310.py first to get the real one.
"""
import io

SRC = r"C:\legacy_e2e\obs-beauty_310.dll"
DST = r"C:\legacy_e2e\dryrun\obs-beauty.dll"
BAK = r"C:\legacy_e2e\dryrun\backup\obs-beauty.dll.20261025_195741.bak"

lines = [
    "@echo off",
    "rem DRY RUN of the v3.0.10 installer - scratch destination only",
    "setlocal",
    "set SRC=" + SRC,
    "set DST=" + DST,
    "set BAK=" + BAK,
    "",
    "echo [0] preflight (dry run: skipped)",
    "",
    "echo [1/3] backup current DLL",
    "if exist \"%DST%\" copy /y \"%DST%\" \"%BAK%\"",
    "if not exist \"%BAK%\" echo [note] nothing to back up (first install)",
    "echo   backup -^> %BAK%",
    "",
    "echo [2/3] copy new DLL",
    "copy /y \"%SRC%\" \"%DST%\"",
    "if errorlevel 1 echo [FAIL] copy failed",
    "if errorlevel 1 exit /b 1",
    "",
    "echo [3/3] verify size + md5",
    "for %%A in (\"%SRC%\") do set S1=%%~zA",
    "for %%B in (\"%DST%\") do set S2=%%~zB",
    'for /f "tokens=1" %%a in (\'certutil -hashfile "%SRC%" MD5 ^| findstr /r "^[0-9a-f]*$"\') do set H1=%%a',
    'for /f "tokens=1" %%b in (\'certutil -hashfile "%DST%" MD5 ^| findstr /r "^[0-9a-f]*$"\') do set H2=%%b',
    "echo   src %S1% bytes  md5 %H1%",
    "echo   dst %S2% bytes  md5 %H2%",
    "",
    'if not "%S1%"=="%S2%" echo [FAIL] size mismatch',
    'if not "%S1%"=="%S2%" exit /b 1',
    'if /i not "%H1%"=="%H2%" echo [FAIL] md5 mismatch',
    'if /i not "%H1%"=="%H2%" exit /b 1',
    "",
    "echo [OK] dry run passed",
    "exit /b 0",
]

data = "\r\n".join(lines) + "\r\n"
with io.open("install_310_dryrun.bat", "wb") as f:
    f.write(data.encode("ascii"))
raw = open("install_310_dryrun.bat", "rb").read()
assert all(b < 128 for b in raw)
assert b"\n" not in raw.replace(b"\r\n", b"")
print("install_310_dryrun.bat written: %d bytes, ASCII+CRLF OK" % len(raw))
