rem ===========================================================================
rem  build_1.0.13.10.bat - build BOTH CPU dlls for version 1.0.13.10
rem
rem  1.0.13.10 = C-1: the per-size reallocation can no longer leave a
rem              half-built state behind.
rem
rem  obs-beauty.cpp's render callback reallocated its per-frame resources
rem  (two cx*cy*4 buffers, a texrender, a stagesurface, one GS_DYNAMIC
rem  texture) in this order: commit f->w/f->h FIRST, then allocate, then
rem  check every pointer and return early on failure. When a malloc failed,
rem  the next frame saw "f->w == cx && f->h == cy && f->tr != NULL", so the
rem  "size changed" test was false forever: the buffers were never retried
rem  and the code walked straight into memcpy(f->buf_in, ...) and
rem  gs_stage_texture(f->stage, ...). A stagesurface that failed while the
rem  texrender succeeded ends the same way. Crash on the render thread, with
rem  only the "alloc failed" line in the log.
rem
rem  1080p is 8 MB per buffer, 4K is 33 MB - this only fires when memory or
rem  GPU resources run out, which is why normal rendering never noticed.
rem
rem  Fix: new beauty_filter_alloc() builds the whole new set in locals and
rem  frees/commits the old one ONLY after every piece succeeded. On failure
rem  it releases the partial set and returns false, leaving the struct
rem  exactly as it was; the frame is passed through and the next frame
rem  retries because f->w still holds the old size. The "needs realloc"
rem  test now also checks stage/out_tex/buf_in/buf_out, so no half-built
rem  state can hide from it.
rem
rem  No pixel path changed, engine untouched. The offline harness never
rem  calls this function (it drives the engine, not the OBS render
rem  callback). Verified at compile level only: same cl line as 1.0.13.9,
rem  0 warnings, obs-beauty.dll 506,880 B vs 505,856 B. Real-machine
rem  install/uninstall regression NOT run yet - this build makes no package.
rem
rem  Output goes to 02_build\build_1.0.13.10 so older out dirs stay untouched.
rem
rem  C-2 / C-3 (same version, added after the C-1 fix): this is the RELEASE
rem  build and it defines BEAUTY_ENV_LOCK=1. All 115 BEAUTY_* env overrides
rem  (BEAUTY_ALIGN_DIFF, BEAUTY_ROLL_CHECK, BEAUTY_FACE_MODEL, ...) are inert
rem  here: beauty_env() in beauty_env.h returns nullptr, so every call site
rem  falls through to its default branch. BEAUTY_FACE_MODEL in particular can
rem  no longer point the plugin at an arbitrary .onnx.
rem
rem  The pixel path is identical to the dev build; only the env lookup differs.
rem  Load-time log tells the two apart:/r/nrem    env override: locked (release build)   <- this build
rem    env override: open (dev build)         <- build_1.0.13.10_dev.bat
rem
rem  Use the DEV build for any A/B that drives BEAUTY_* variables. Do not
rem  ship it.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path
rem  and cmd.exe reads .bat as GBK.
rem ===========================================================================
setlocal enabledelayedexpansion

set VSBASE=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231
set SDKBASE=C:\Program Files (x86)\Windows Kits\10
set SDKVER=10.0.26100.0
set QT=C:\Qt

set PATH=%VSBASE%\bin\Hostx64\x64;%PATH%
set INCLUDE=%VSBASE%\include;%SDKBASE%\Include\%SDKVER%\ucrt;%SDKBASE%\Include\%SDKVER%\um;%SDKBASE%\Include\%SDKVER%\shared;%SDKBASE%\Include\%SDKVER%\winrt
set LIB=%VSBASE%\lib\x64;%SDKBASE%\Lib\%SDKVER%\ucrt\x64;%SDKBASE%\Lib\%SDKVER%\um\x64

set HERE=%~dp0
set ROOT=%HERE%..

set SRC=
for /d %%d in ("%ROOT%\01_*") do if exist "%%d\obs-beauty.cpp" set SRC=%%d
if not defined SRC (
    echo [build140] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [build140] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [build140] offline-verify dir not found
    exit /b 1
)

if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build140] Qt not found at %QT%
    exit /b 1
)

set OUT=%HERE%build_1.0.13.10
if not exist "%OUT%" mkdir "%OUT%"

echo [build140] src=%SRC%
echo [build140] dep=%DEP%
echo [build140] out=%OUT%

rem ---- 1) engine / filter dll ---------------------------------------------
cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS /DBEAUTY_ENV_LOCK=1 ^
   /I "%DEP%\obs-studio-32.1.1\libobs" ^
   /I "%OFFDIR%\deps\runtime\include" ^
   /Fo"%OUT%\\" /Fe"%OUT%\obs-beauty.dll" ^
   "%SRC%\obs-beauty.cpp" ^
   "%SRC%\beauty_core.cpp" ^
   "%SRC%\beauty_pool.cpp" ^
   "%SRC%\beauty_smooth.cpp" ^
   "%SRC%\beauty_freq.cpp" ^
   "%SRC%\beauty_guide.cpp" ^
   "%SRC%\beauty_onnx.cpp" ^
   "%SRC%\beauty_face.cpp" ^
   "%SRC%\beauty_region.cpp" ^
   "%SRC%\beauty_warp.cpp" ^
   "%SRC%\beauty_log.cpp" ^
   "%DEP%\obs-sdk\obs.lib" user32.lib gdi32.lib opengl32.lib
if errorlevel 1 (
    echo [build140] FILTER BUILD FAILED
    exit /b 1
)
echo [build140] FILTER OK -^> %OUT%\obs-beauty.dll

rem ---- 2) UI dll - Qt6, needs QT\bin on PATH ------------------------------
set PATH=%QT%\bin;%PATH%
cl /nologo /LD /O2 /EHsc /std:c++17 /Zc:__cplusplus /permissive- /W3 /utf-8 ^
   /DBEAUTY_UI_CPU_EDITION=1 ^
   /I "%DEP%\obs-studio-32.1.1\libobs" ^
   /I "%QT%\include" /I "%QT%\include\QtCore" /I "%QT%\include\QtGui" /I "%QT%\include\QtWidgets" ^
   /Fo"%OUT%\\" /Fe"%OUT%\obs-beauty-ui.dll" ^
   "%SRC%\obs-beauty-ui.cpp" ^
   "%DEP%\obs-sdk\obs.lib" "%DEP%\obs-sdk\obs-frontend-api.lib" ^
   "%QT%\lib\Qt6Widgets.lib" "%QT%\lib\Qt6Gui.lib" "%QT%\lib\Qt6Core.lib" ^
   user32.lib
if errorlevel 1 (
    echo [build140] UI BUILD FAILED
    exit /b 1
)
echo [build140] UI OK -^> %OUT%\obs-beauty-ui.dll
exit /b 0
