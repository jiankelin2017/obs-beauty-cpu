rem ===========================================================================
rem  build_1.0.13.6.bat - build BOTH CPU dlls for version 1.0.13.6
rem
rem  1.0.13.6 = "head tilted ~45 deg: the picture blinks / hitches once".
rem  Four things were stacked; only (4) came from 1.0.13.5.
rem
rem      starts after g_cfg.rollMiss consecutive misses. Traced frame by frame
rem      on face_src rotated 45 deg: f00..f07 = no face, f08 = probe locks on.
rem      Mask survived on kMaskHold, which was 6 - and it counts MISSES, not
rem      frames (async path = one miss per frame). So frames 7-8 dropped the
rem      mask entirely: smoothing and all three warp sliders went off for two
rem      frames. That is the blink.
rem  (2) The frame that locks on runs two extra 640x640 inferences (+-45).
rem      That is the hitch.
rem  (3) On that frame the box collapses from the AABB (176.6x176.6) to the
rem      tight box (107.5x142.2, area ratio 2.04) and resetFaceEmaState()
rem      wipes the EMA, so the new box is adopted raw - no transition at all.
rem  (4) NEW IN 1.0.13.5: beauty_warp.cpp decided whether to swap fw/fh by
rem      |cos(phi)| >= |sin(phi)|. At 45 deg that is 0.7085 vs 0.7057 - 0.4%.
rem      A 0.2 deg keypoint jitter flips the face width and height (fw 107.5
rem      vs 142.2, a 32% scale jump) and the picture blinks right there.
rem      Root cause: a CONTINUOUS quantity was used to guess a DISCRETE fact.
rem      invRotateFace() swaps the box w/h only for 90/270; upright and 90/270
rem      merely happened to guess right.
rem
rem  Fixes:
rem    . FaceBox gains srcRot (0/90/270), set in invRotateFace exactly where
rem      the swap happens. beauty_warp.cpp now uses it: rw/rh if present (they
rem      already ARE the face width/height, never swapped) -> else swap iff
rem      srcRot is 90/270 -> else leave as is.
rem    . g_cfg.rollMiss 8 -> 4.
rem    . kMaskHold 6 -> 8.
rem    . smoothFaceBoxes keeps the EMA history across short detection gaps
rem      (up to kEmaResyncMiss = 15 frames) and the first recovered frame goes
rem      through EMA instead of the jump-hold.
rem
rem  Verified: detection gap 8 -> 4 frames; upright 8/8 panel combos byte
rem  identical (000 combo still 0efa47d9cf6a5505848410dd6f5e35af); 270 deg
rem  still 7/8 DIFF; _warp_seam.py unchanged vs 1.0.13.5; diff 30/30,
rem  ema_cmp 0/16, mt_cmp 40/40.
rem
rem  Output goes to 02_build\build_1.0.13.6 so older out dirs stay untouched.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path and
rem  cmd.exe reads .bat as GBK.
rem ===========================================================================
rem  build_1.0.13.6.bat - build BOTH CPU dlls for version 1.0.13.6
rem
rem  1.0.13.6 = the shared face detector is serialised.
rem            1.0.13.2 moved the detection STATE per slot, but the detector
rem            itself (beautycore::FaceDetector, one per process) was still
rem            shared with no lock. detect() writes its 640x640 intermediate
rem            image into member buffers (resized_ / input_) and hands the
rem            pointer to ORT; with two slots the render thread and the async
rem            worker could run it at once, and one side's resize() reallocates
rem            while the other still writes through the old pointer.
rem              . FaceDetector gets a mutex; detect/load/release/setInputSize
rem                are serialised. load() now calls releaseLocked() instead of
rem                release() (that would deadlock on the non-recursive mutex).
rem              . "best score" for the failure log used to be read back from
rem                the shared detector (lastBestScore()), i.e. it could belong
rem                to the other slot. It now travels out of detect() via
rem                DetMeta and lands in DetState.detBest.
rem              . CoreEngine::ensureReady() is serialised too: preheat() and
rem                acquireSlot() can arrive on two threads, and the faceTried_
rem                gate is not atomic, so both could load the model.
rem            Verified with dual_instance_check.py --mode mt_dual (two threads
rem            calling the mask path at the same time): the no-lock control
rem            build differed on 4 and 9 of 40 masks in 2 of 3 runs; this build
rem            is identical 40/40 in 3 of 3 runs. diff mode still 30/30, ema_cmp
rem            0/16, single-instance output unchanged.
rem  Output goes to 02_build\build_1.0.13.6 so older out dirs stay untouched.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path and
rem  cmd.exe reads .bat as GBK.
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
    echo [build116] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [build116] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [build116] offline-verify dir not found
    exit /b 1
)

if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build116] Qt not found at %QT%
    exit /b 1
)

set OUT=%HERE%build_1.0.13.6
if not exist "%OUT%" mkdir "%OUT%"

echo [build116] src=%SRC%
echo [build116] dep=%DEP%
echo [build116] out=%OUT%

rem ---- 1) engine / filter dll ---------------------------------------------
cl /nologo /LD /O2 /EHsc /std:c++17 /W3 /utf-8 /D_CRT_SECURE_NO_WARNINGS ^
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
    echo [build116] FILTER BUILD FAILED
    exit /b 1
)
echo [build116] FILTER OK -^> %OUT%\obs-beauty.dll

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
    echo [build116] UI BUILD FAILED
    exit /b 1
)
echo [build116] UI OK -^> %OUT%\obs-beauty-ui.dll
exit /b 0
