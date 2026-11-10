rem ===========================================================================
rem  build_1.0.13.5.bat - build BOTH CPU dlls for version 1.0.13.5
rem
rem  1.0.13.5 = the warp displacement field is built in the FACE's own frame.
rem            The slim-face and chin sliders were deforming the wrong part of
rem            the face on portrait / landscape sources (the ones that trigger
rem            the 90/270 auto-orientation compensation).
rem            Root cause: beauty_warp.cpp built every field on the IMAGE axes.
rem            After invRotatePoint() the box handed to warpFace() has, for a
rem            source rotated by 90/270, f.w == the face HEIGHT and f.h == the
rem            face WIDTH - but makeGeom() used f.w/f.h as face width/height:
rem              . "compress horizontally toward the midline" compressed along
rem                the face's long axis instead;
rem              . "compress vertically below the mouth line" compressed
rem                across the face width, landing beside the ear;
rem              . the ROI expanded from f.x/f.w, so its rectangle cut outside
rem                the face.
rem            Fix:
rem              . new Geom cp/sp/rot (image -> face frame); phi from the eye
rem                line atan2, the mouth corners only disambiguate +-180 deg;
rem              . 8 deg dead zone: kills keypoint noise AND keeps upright
rem                sources on the byte-identical old code path (face_src has a
rem                5.8 deg eye line, well inside the dead zone);
rem              . face-native fw/fh: box w/h (rw/rh preferred when the head is
rem                tilted) swapped by abs(cos) >= abs(sin);
rem              . inner loop goes ox,oy -> ax,ay (face frame) -> the three
rem                fields -> back to (sx,sy) for sampling;
rem              . ROI for rot takes the bounding box of the 0.80fw x 0.68fh
rem                rectangle expressed in the face frame; upright branch is
rem                kept verbatim;
rem              . the thinning vertical weight now uses ay instead of oy
rem                (ay == oy when not rotated, so still bit-identical upright).
rem            Verified with 05_VERIFY/_warp_seam.py against a control build
rem            (beauty_core_test_norot.dll, one line changed: phi forced to 0,
rem            i.e. the 1.0.13.4 path). Change regions rewritten in face
rem            coordinates: chin at 90/270 deg went from a narrow band spanning
rem            the whole face height on one side to the lower-face band that the
rem            upright case produces; thinning's asymmetric extent (one side not
rem            touched at all) became symmetric and equal to upright. Upright
rem            output bit-identical across 8 panel combinations; diff 30/30,
rem            ema_cmp 0/16, mt_cmp 40/40 still pass.
rem  Output goes to 02_build\build_1.0.13.5 so older out dirs stay untouched.
rem
rem  Pure ASCII + CRLF on purpose: the tree lives under a Chinese-named path and
rem  cmd.exe reads .bat as GBK.
rem ===========================================================================
rem  build_1.0.13.5.bat - build BOTH CPU dlls for version 1.0.13.5
rem
rem  1.0.13.5 = the shared face detector is serialised.
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
rem  Output goes to 02_build\build_1.0.13.5 so older out dirs stay untouched.
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
    echo [build115] source dir not found under %ROOT%
    exit /b 1
)

set DEP=
for /d %%d in ("%ROOT%\*") do for /d %%e in ("%%d\*") do if exist "%%e\obs-studio-32.1.1\libobs" set DEP=%%e
if not defined DEP (
    echo [build115] dependency dir not found
    exit /b 1
)

set OFFDIR=
for /d %%d in ("%ROOT%\05_*") do if exist "%%d\deps\runtime\include" set OFFDIR=%%d
if not defined OFFDIR (
    echo [build115] offline-verify dir not found
    exit /b 1
)

if not exist "%QT%\lib\Qt6Widgets.lib" (
    echo [build115] Qt not found at %QT%
    exit /b 1
)

set OUT=%HERE%build_1.0.13.5
if not exist "%OUT%" mkdir "%OUT%"

echo [build115] src=%SRC%
echo [build115] dep=%DEP%
echo [build115] out=%OUT%

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
    echo [build115] FILTER BUILD FAILED
    exit /b 1
)
echo [build115] FILTER OK -^> %OUT%\obs-beauty.dll

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
    echo [build115] UI BUILD FAILED
    exit /b 1
)
echo [build115] UI OK -^> %OUT%\obs-beauty-ui.dll
exit /b 0
