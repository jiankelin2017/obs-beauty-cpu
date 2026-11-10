rem ===========================================================================
rem  build_1.0.13.8.bat - build BOTH CPU dlls for version 1.0.13.8
rem
rem  1.0.13.8 = "still flashes at ~45 deg after 1.0.13.8".
rem  1.0.13.8 fixed the geometry transition and that fix holds: with mask
rem  alignment disabled the 0..57..0 geometry sweep is flat. What still jumps
rem  is the MASK ALIGNMENT in the async path. When a worker result lands,
rem  process() writes heldFrame_ (THE PREVIOUS FRAME) to dst; when it does
rem  not, it writes the current frame. Worker busy half the time -> the two
rem  alternate and the picture flips between 'one frame late' and 'current'.
rem
rem    alignDiff=0 : 57->57 deg  meanD 7.09 -> 1.67   (d = -5.41)
rem    alignDiff=4 : whole 0..57..0 sweep  1.29..1.68, no jump at all
rem
rem  Note on the metric: in the ASYNC path meanD is NOT beauty strength.
rem  Synced runs give a flat 1.2..1.7; the extra 5.4 is the whole-frame
rem  shift of a 1 deg/frame rotation. Measure strength on the sync path.
rem
rem  Reproduced in the async path (face_src stepped 3 deg per frame, 0 -> 57,
rem  all three warp sliders at 100, measuring mean|out-in| per frame):
rem    f16 48 deg  roll=  0  phi=+0.88  box 108x113  meanD 0.98
rem    f17 51 deg  roll=  0  phi=-6.28  box 116x119  meanD 1.16   52.2 ms
rem    f18 54 deg  roll=-45  phi=+45.72 box 179x179  meanD 1.61  <- +39% in one frame
rem  Two things change at once:
rem    . phi jumps from ~0 (YuNet's five keypoints collapse into a horizontal
rem      line on a 45 deg face) to the real 45.7 deg -> the warp direction
rem      turns 45 deg;
rem    . fw/fh jumps from the detection box (an axis-aligned AABB when roll==0)
rem      to rw/rh (the tight box): 108x116 -> 107x142.
rem  Note: the async path lost ZERO frames. 1.0.13.6's smaller rollMiss did not
rem  miss the target because it was wrong - it just was not this target.
rem
rem  Fix (beauty_core.cpp, new "geometry transition"):
rem    . DetState gains geoLast / geoFrom / geoFadeLeft. geoLast is the geometry
rem      that was actually handed downstream, written by buildMaskInto itself.
rem      Do NOT use DetState::faces for this: in the async path that field is
rem      swapped in by the render thread (collectAsync), so the worker's view of
rem      it at detection time is timing-dependent. The first attempt did exactly
rem      that and the transition never started - geoFrom came out empty.
rem    . startGeoFade() on both directions of the switch: 0 -> +-45 (roll probe
rem      hit) and +-45 -> 0 (re-detect at the plain direction angle succeeds).
rem      It stores the pre-switch box and sets geoFadeLeft = 6.
rem    . applyGeoFade() blends every geometric quantity for the next 6 frames
rem      (centre, rw/rh, roll, all 5 keypoints). For frames where roll != 0 the
rem      box w/h is recomputed as the AABB of rw/rh rotated by roll - the mask is
rem      painted as a rotated rw x rh rectangle while ROI and fw/fh read w/h, so
rem      letting them disagree would misplace one against the other.
rem    . smoothFaceBoxes is skipped entirely during the transition: those frames
rem      are already moving along a designed path, an extra "did it jump" hysteresis
rem      only drags it back, and EMA would write the interpolated value into
rem      faceEmaPrev and pull on it again after the transition ends.
rem    . Only 1-to-1 faces are interpolated. When the face count changes (someone
rem      walks in) the two sets cannot be paired; a hard cut is safer than dragging
rem      A's geometry onto B.
rem
rem  Verified: the lock-on segment 1.16 -> 1.61 in one frame became
rem  0.93 -> 1.13 -> 1.25 -> 1.38 -> 1.48 -> 1.63 (1/5 per frame); the largest
rem  adjacent jump went from +0.46 to +0.19. Upright 8/8 panel combos stay byte
rem  identical (000 combo still 0efa47d9cf6a5505848410dd6f5e35af); 270 deg stays
rem  7/8 DIFF; _warp_seam.py unchanged; diff 30/30, ema_cmp 0/16, mt_cmp 40/40.
rem
rem  Output goes to 02_build\\build_1.0.13.8 so older out dirs stay untouched.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path and
rem  cmd.exe reads .bat as GBK.
rem ===========================================================================
rem  build_1.0.13.8.bat - build BOTH CPU dlls for version 1.0.13.8
rem
rem  1.0.13.8 = the shared face detector is serialised.
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
rem  Output goes to 02_build\build_1.0.13.8 so older out dirs stay untouched.
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
    echo [build118] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [build118] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [build118] offline-verify dir not found
    exit /b 1
)

if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build118] Qt not found at %QT%
    exit /b 1
)

set OUT=%HERE%build_1.0.13.8
if not exist "%OUT%" mkdir "%OUT%"

echo [build118] src=%SRC%
echo [build118] dep=%DEP%
echo [build118] out=%OUT%

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
    echo [build118] FILTER BUILD FAILED
    exit /b 1
)
echo [build118] FILTER OK -^> %OUT%\obs-beauty.dll

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
    echo [build118] UI BUILD FAILED
    exit /b 1
)
echo [build118] UI OK -^> %OUT%\obs-beauty-ui.dll
exit /b 0
