; ============================================================================
;  OBS美颜 CPU 版 安装包  (NSIS 3 / Unicode)
;
;  装什么（4 个文件 + 文档 + 卸载器）：
;    obs-beauty.dll      = 滤镜本体（CPU 版，版本见 beauty_params.h）
;    obs-beauty-ui.dll   = 参数面板（ProgramData 下的插件目录）
;
;  版本轴：CPU 线四段式，唯一口径是 01_源码\beauty_params.h 的 BEAUTY_BUILD_STR，
;  由 build_setup.ps1 读出后用 /DPKGVER 等传进来；本文件不再写死版本号。
;  与 GPU 版 3.0.1 独立，不可互比。引擎 core 已并入这条单轴。
;
;  装机口径（2026-11-07 按用户裁定 C-1 统一到 ProgramData）：
;    $OBSDIR = %ProgramData%\obs-studio\plugins\obs-beauty\bin\64bit
;    $UIDIR  = %ProgramData%\obs-studio\plugins\obs-beauty-ui\bin\64bit
;                 放 obs-beauty-ui.dll
;  旧口径 $OBSROOT\obs-plugins\64bit（扁平布局）已废弃：OBS 扫描全局插件时
;  要求 <插件目录名>\bin\64bit\<同名>.dll，目录名与 DLL 主名必须一致，
;  否则静默跳过且不写日志（见 docs/guides/guide-ui.md §3）。
;  $OBSROOT 现在只用于确认宿主 OBS 已安装，不再作为插件写入目标。
;
;  为什么这几个位置不能改（见 04_文档\C13_装机链路.md §2）：
;    beauty_core.cpp 的 ensureReady() 用 selfDir()（= obs-beauty.dll 所在目录）
;    滤镜仍能加载，但人脸检测静默失效 → 磨皮退化成全帧。
;
;  不含 NamaSDK（约 97 MB 闭源件）：3.1.7 起默认引擎已切到 core，
;  本机实测无 SDK 目录也能正常 init（engine=core/1.0.0.0, region=on）。
;  机器上本来就有 obs-beauty\ SDK 目录的，本包一律不动。
;
;  卸载三条硬规则（"装之前什么样，卸完还是什么样"）：
;    1. **首次安装**时装之前已有同名文件 → 先备份到 <InstallDir>\backup，卸载时还原
;       （那种文件只可能来自别的产品：GPU 版、插件市场、手工放的）
;    1b. **升级安装**（注册表里已有本安装器写的 Version）→ 不备份，并把旧的
;       .bak 清掉 —— 目录里那份是本安装器上一版写的，备份它只会让卸载退回旧版。
;       1.0.13.11 起生效，之前的行为是「备份只写一次、永不刷新」。
;    2. 装之前没有 → 卸载时删除（models 目录只在空的时候删）
;    3. 不是本包装的东西（比如别人放的 obs-beauty\ SDK、models 里的其他模型）→ 一律不动
;
;  编译：
;    powershell -ExecutionPolicy Bypass -File build_setup.ps1
;  或手工：
;    makensis /DSRCDIR=<纯ASCII暂存目录> "obs-beauty.nsi"
;
;  本文件必须存为 UTF-8 with BOM，否则中文界面会乱码。
;  源文件路径必须纯 ASCII —— NSIS 处理中文源路径会报 "no files found"。
; ============================================================================

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64
SetDatablockOptimize on

!define APPNAME      "OBS美颜"
!define APPNAME_EN   "OBS Beauty"
!define EDITION      "CPU 版"
; 沿用旧包的 APPID：老版本（3.0.20 / 3.1.2）装过的话算升级，不会在
; 「程序和功能」里留下两条重复项。
!define APPID        "OBSBeauty.NamaBeauty"
; 版本号由 build_setup.ps1 用 /D 传进来 —— 只在一处维护。
; CPU 线四段式；GPU 版是另一条独立轴（3.0.1，三段式），不可互比。
; 2026-11-09 起不再写死兜底值：以前直接跑 makensis 会静默打出 v1.0.3.0 的
; 旧号包（C13 坑 #1 的变体）。现在缺 PKGVER 直接编译失败，其余三项跟随 PKGVER。
!ifndef PKGVER
  !error "PKGVER not defined. Run 06_安装包\build_setup.ps1, or pass /DPKGVER=x.x.x.x with FILTERVER/PANELVER/COREVER/SRCDIR/OUTFILE."
!endif
!ifndef FILTERVER
  !define FILTERVER "${PKGVER}"
!endif
!ifndef PANELVER
  !define PANELVER  "${PKGVER}"
!endif
!ifndef COREVER
  !define COREVER   "${PKGVER}"
!endif
!define PUBLISHER    "OBS Beauty (personal build)"
!define ESTSIZE      12250            ; KB，控制面板里显示的大小（4 个文件约 12.2 MB）

; 暂存目录（纯 ASCII）。由 build_setup.ps1 生成，也可以用 /DSRCDIR= 覆盖。
!ifndef SRCDIR
  !define SRCDIR "C:\_obspkg_src"
!endif
!ifndef OUTFILE
  !define OUTFILE "OBS美颜_CPU_v${PKGVER}.exe"
!endif

; ------------------------------------------------- 编译期源文件自检
; 必须放在编译期（!if /FileExists），不能放到 .onInit 里：
; File 是编译时把文件内容写进 exe 的，跑安装的时候根本不需要 SRCDIR，
; 而打包脚本编完就把暂存目录清掉了 —— 写成运行时检查会让安装直接 Abort。
!if ! /FileExists "${SRCDIR}\filter\obs-beauty.dll"
  !error "source missing: ${SRCDIR}\filter\obs-beauty.dll"
!endif
!if ! /FileExists "${SRCDIR}\core\onnxruntime.dll"
  !error "source missing: ${SRCDIR}\core\onnxruntime.dll"
!endif
!if ! /FileExists "${SRCDIR}\core\models\yunet.onnx"
  !error "source missing: ${SRCDIR}\core\models\yunet.onnx"
!endif
!if ! /FileExists "${SRCDIR}\panel\obs-beauty-ui.dll"
  !error "source missing: ${SRCDIR}\panel\obs-beauty-ui.dll"
!endif
!if ! /FileExists "${SRCDIR}\docs\README.txt"
  !error "source missing: ${SRCDIR}\docs\README.txt"
!endif
!if ! /FileExists "${SRCDIR}\docs\md5.txt"
  !error "source missing: ${SRCDIR}\docs\md5.txt"
!endif

!define REGKEY       "Software\${APPID}"
!define UNINSTKEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPID}"

Var OBSROOT      ; OBS Studio 安装根目录（只用于确认宿主已装，不再是插件目标）
Var OBSDIR       ; <ProgramData>\obs-studio\plugins\obs-beauty\bin\64bit（目录名须与 DLL 主名一致）
Var PDIR         ; ProgramData
Var UIDIR        ; <ProgramData>\obs-studio\plugins\obs-beauty-ui\bin\64bit

; "external" = 首次安装，装之前目录里的同名文件属于别的产品，卸载要还原
; "self"     = 升级安装，那份文件是本安装器上一版写的，卸载要删除
; 由 SecCore 开头按注册表 Version 判定，SecPanel 沿用同一个结果。
Var BACKUP_ORIGIN

Name "${APPNAME} ${EDITION} ${PKGVER}"
Caption "${APPNAME} ${EDITION} ${PKGVER} 安装程序"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\obs-beauty"
RequestExecutionLevel admin
ShowInstDetails show
ShowUninstDetails show
BrandingText "${APPNAME} ${EDITION} ${PKGVER}  ·  滤镜 ${FILTERVER} + 面板 ${PANELVER} + 引擎 ${COREVER}"

; PKGVER 已是四段式 x.y.z.w，Windows 版本资源直接取用，不能再补 ".0"（会变五段）。
VIProductVersion "${PKGVER}"
VIAddVersionKey /LANG=2052 "ProductName"     "${APPNAME} ${EDITION}"
VIAddVersionKey /LANG=2052 "ProductVersion"  "${PKGVER}"
VIAddVersionKey /LANG=2052 "FileDescription" "${APPNAME} ${EDITION} 安装程序（纯 CPU，不依赖 GPU）"
VIAddVersionKey /LANG=2052 "FileVersion"     "${PKGVER}"
VIAddVersionKey /LANG=2052 "CompanyName"     "${PUBLISHER}"
VIAddVersionKey /LANG=2052 "LegalCopyright"  "仅供自用"

; ------------------------------------------------------------------ 界面
!define MUI_ABORTWARNING
!define MUI_ICON   "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!define MUI_WELCOMEPAGE_TITLE "安装 ${APPNAME} ${PKGVER}"
!define MUI_WELCOMEPAGE_TEXT  "本程序给 OBS Studio 装「OBS美颜」：$\r$\n$\r$\n  · 滤镜 obs-beauty.dll  ${FILTERVER}（真正的像素处理）$\r$\n  · 参数面板 obs-beauty-ui.dll  ${PANELVER}（OBS 顶层菜单「美颜」）$\r$\n  · 自研引擎运行时（ONNX Runtime + YuNet 模型，约 11.8 MB）$\r$\n$\r$\n一共 4 个文件，装完在 OBS 里加一个「OBS美颜」滤镜就能用。$\r$\n$\r$\n安装前请先关闭 OBS，否则 DLL 被占用会替换失败。$\r$\n$\r$\n点「下一步」开始。"

!define MUI_FINISHPAGE_TITLE "装好了"
!define MUI_FINISHPAGE_TEXT  "打开 OBS，在源的「滤镜」里添加「OBS美颜」，$\r$\n再点顶层菜单「美颜」打开参数面板调档。$\r$\n$\r$\n卸载：开始菜单「${APPNAME}」→「卸载 ${APPNAME}」，$\r$\n或控制面板「程序和功能」里找 ${APPNAME}。$\r$\n$\r$\n卸载会还原装之前的状态（装前有的文件原样放回，装前没有的删掉）。"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "查看使用说明（README.txt）"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED

!define MUI_UNCONFIRMPAGE_TEXT_TOP "${APPNAME} ${PKGVER}"
!define MUI_UNCONFIRMPAGE_TEXT_LOCATION "点「卸载」开始移除插件。$\r$\n$\r$\n只删本包装的 4 个文件；装之前就有的同名文件会还原回去，$\r$\nOBS 的场景与参数不受影响。$\r$\n$\r$\nOBS 必须处于关闭状态。"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ------------------------------------------------------- 公共：检测 OBS 进程
Function CheckOBSRunning
  nsExec::Exec '"$SYSDIR\cmd.exe" /c tasklist /fi "imagename eq obs64.exe" /nh | "$SYSDIR\find.exe" /i "obs64.exe" >nul'
  Pop $0
  ${If} $0 == "0"
    MessageBox MB_ICONSTOP|MB_OK "OBS 正在运行。$\r$\n$\r$\n请先把 OBS 完全关闭（含托盘图标），再重新运行。$\r$\n$\r$\n现在什么都没改。" /SD IDOK
    Abort
  ${EndIf}
FunctionEnd

; ------------------------------------------------------- 初始化：定位各处
Function .onInit
  SetRegView 64
  SetShellVarContext all

  ; ProgramData：本机 NSIS 3.13 没有 $PROGRAMDATA 常量，从环境变量取
  ReadEnvStr $PDIR "ProgramData"
  ${If} $PDIR == ""
    StrCpy $PDIR "C:\ProgramData"
  ${EndIf}
  StrCpy $UIDIR "$PDIR\obs-studio\plugins\obs-beauty-ui\bin\64bit"
  StrCpy $OBSDIR "$PDIR\obs-studio\plugins\obs-beauty\bin\64bit"

  ; OBS 根目录只用来确认宿主已安装；插件不再写 $OBSROOT\obs-plugins。
  ReadRegStr $OBSROOT HKLM "SOFTWARE\OBS Studio" ""
  ${If} $OBSROOT == ""
    StrCpy $OBSROOT "$PROGRAMFILES64\obs-studio"
  ${EndIf}

  ${IfNot} ${FileExists} "$OBSROOT\bin\64bit\obs64.exe"
    MessageBox MB_ICONSTOP|MB_OK "没有找到 OBS Studio：$\r$\n$OBSROOT\bin\64bit\obs64.exe$\r$\n$\r$\n本安装包只能装进已安装的 OBS Studio（64 位）。$\r$\n请先装 OBS Studio 32.x，再运行本程序。$\r$\n$\r$\n现在什么都没改。" /SD IDOK
    Abort
  ${EndIf}

  ; 全局插件目录由本包自己创建（SetOutPath 会建），不要求预先存在。

  ; 已有安装则沿用旧目录（覆盖升级）
  ReadRegStr $0 HKLM "${REGKEY}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}

  Call CheckOBSRunning
FunctionEnd

; ============================================================ 1. 滤镜 + 运行时
Section "滤镜 + 自研引擎运行时" SecCore
  SectionIn RO
  DetailPrint "目标全局插件目录：$OBSDIR"

  CreateDirectory "$INSTDIR\backup"

  ; ---- 首次安装 / 升级安装 的判定（1.0.13.11） -----------------------------
  ; 备份只对「首次安装」有意义：那时目录里的同名文件必然是别的产品
  ; （GPU 版 / 插件市场版 / 手工放的）。升级时目录里那份是本安装器自己
  ; 上一版写的，再备份它 → 卸载会把旧版放回去。PHASE R 实测：
  ; 装 13.9 → 升级 13.10 → 卸载，ProgramData 里留下 505,856 B 的 13.9。
  ; 判据用注册表 Version：GPU 版装到同一路径，但它用另一个键
  ; （...\Uninstall\obs-beauty）且从不写本键，所以「本键有 Version」
  ; 等价于「目录里是 CPU 线的自家文件」。
  ; 滤镜 DLL 没有版本资源（01_源码下无 .rc），卸载时无法反查 .bak 的来源，
  ; 所以判断必须放在安装时。
  StrCpy $9 ""                       ; 先清空：键不存在时读失败不能沿用上个值
  ReadRegStr $9 HKLM "${REGKEY}" "Version"
  StrCmp $9 "" backup_origin_external
    StrCpy $BACKUP_ORIGIN "self"
    DetailPrint "升级安装（已有 $9）：不保留旧版备份，卸载将直接删除"
    Delete "$INSTDIR\backup\obs-beauty.dll.bak"
    Delete "$INSTDIR\backup\onnxruntime.dll.bak"
    Delete "$INSTDIR\backup\yunet.onnx.bak"
    Delete "$INSTDIR\backup\obs-beauty-ui.dll.bak"
    Goto backup_origin_done
  backup_origin_external:
    StrCpy $BACKUP_ORIGIN "external"
  backup_origin_done:

  CreateDirectory "$OBSDIR"
  SetOutPath "$OBSDIR"
  SetOverwrite on

  ; ---- 滤镜 DLL -----------------------------------------------------------
  ; 只有「首次安装」才备份（$BACKUP_ORIGIN 已在 SecCore 开头判定）：
  ; 升级时目录里那份就是本安装器上一版写的，备份它只会让卸载退回旧版。
  ${If} $BACKUP_ORIGIN == "external"
    ${IfNot} ${FileExists} "$INSTDIR\backup\obs-beauty.dll.bak"
      ${If} ${FileExists} "$OBSDIR\obs-beauty.dll"
        CopyFiles /SILENT "$OBSDIR\obs-beauty.dll" "$INSTDIR\backup\obs-beauty.dll.bak"
        DetailPrint "已备份装之前的 obs-beauty.dll（卸载时还原）"
      ${EndIf}
    ${EndIf}
  ${EndIf}
  File /oname=obs-beauty.dll "${SRCDIR}\filter\obs-beauty.dll"
  DetailPrint "滤镜   -> $OBSDIR\obs-beauty.dll"

  ${If} $BACKUP_ORIGIN == "external"
    ${IfNot} ${FileExists} "$INSTDIR\backup\onnxruntime.dll.bak"
      ${If} ${FileExists} "$OBSDIR\onnxruntime.dll"
        CopyFiles /SILENT "$OBSDIR\onnxruntime.dll" "$INSTDIR\backup\onnxruntime.dll.bak"
        DetailPrint "已备份装之前的 onnxruntime.dll（卸载时还原）"
      ${EndIf}
    ${EndIf}
  ${EndIf}
  File /oname=onnxruntime.dll "${SRCDIR}\core\onnxruntime.dll"
  DetailPrint "运行时 -> $OBSDIR\onnxruntime.dll"

  ; models 目录是不是本包建的，卸载时决定要不要删（只删空目录）
  ${If} ${FileExists} "$OBSDIR\models"
    ; 目录本来就有：可能是旧包装的（旧包 ModelsCreated=1），继承它的标记
    ReadRegDWORD $0 HKLM "${REGKEY}" "ModelsCreated"
    ${If} $0 == "1"
      WriteRegDWORD HKLM "${REGKEY}" "ModelsCreated" 1
      DetailPrint "models 目录是旧安装包建的，卸载时继续由本包清理"
    ${Else}
      WriteRegDWORD HKLM "${REGKEY}" "ModelsCreated" 0
      DetailPrint "models 目录装之前就有，卸载时保留"
    ${EndIf}
  ${Else}
    WriteRegDWORD HKLM "${REGKEY}" "ModelsCreated" 1
    DetailPrint "models 目录由本包创建，卸载时删除"
  ${EndIf}

  ${If} $BACKUP_ORIGIN == "external"
    ${IfNot} ${FileExists} "$INSTDIR\backup\yunet.onnx.bak"
      ${If} ${FileExists} "$OBSDIR\models\yunet.onnx"
        CopyFiles /SILENT "$OBSDIR\models\yunet.onnx" "$INSTDIR\backup\yunet.onnx.bak"
        DetailPrint "已备份装之前的 models\yunet.onnx（卸载时还原）"
      ${EndIf}
    ${EndIf}
  ${EndIf}

  CreateDirectory "$OBSDIR\models"
  SetOutPath "$OBSDIR\models"
  File /oname=yunet.onnx "${SRCDIR}\core\models\yunet.onnx"
  DetailPrint "模型   -> $OBSDIR\models\yunet.onnx"
SectionEnd

; ================================================================= 2. 参数面板
Section "参数面板" SecPanel
  SectionIn RO
  CreateDirectory "$UIDIR"

  ${If} $BACKUP_ORIGIN == "external"
    ${IfNot} ${FileExists} "$INSTDIR\backup\obs-beauty-ui.dll.bak"
      ${If} ${FileExists} "$UIDIR\obs-beauty-ui.dll"
        CopyFiles /SILENT "$UIDIR\obs-beauty-ui.dll" "$INSTDIR\backup\obs-beauty-ui.dll.bak"
        DetailPrint "已备份装之前的 obs-beauty-ui.dll（卸载时还原）"
      ${EndIf}
    ${EndIf}
  ${EndIf}

  SetOutPath "$UIDIR"
  SetOverwrite on
  File /oname=obs-beauty-ui.dll "${SRCDIR}\panel\obs-beauty-ui.dll"
  DetailPrint "面板   -> $UIDIR\obs-beauty-ui.dll"
SectionEnd

; ========================================================= 3. 文档 + 卸载程序
Section "说明文档与卸载程序" SecDocs
  SectionIn RO
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File /oname=README.txt "${SRCDIR}\docs\README.txt"
  File /oname=md5.txt "${SRCDIR}\docs\md5.txt"

  WriteUninstaller "$INSTDIR\Uninstall_${APPNAME}.exe"

  ; ---- 自己的状态键（卸载时靠它找回真实路径）------------------------------
  WriteRegStr HKLM "${REGKEY}" "InstallDir"     "$INSTDIR"
  WriteRegStr HKLM "${REGKEY}" "Version"        "${PKGVER}"
  WriteRegStr HKLM "${REGKEY}" "FilterVersion"  "${FILTERVER}"
  WriteRegStr HKLM "${REGKEY}" "PanelVersion"   "${PANELVER}"
  WriteRegStr HKLM "${REGKEY}" "CoreVersion"    "${COREVER}"
  WriteRegStr HKLM "${REGKEY}" "ObsDir"         "$OBSDIR"
  WriteRegStr HKLM "${REGKEY}" "UIDir"          "$UIDIR"
  WriteRegStr HKLM "${REGKEY}" "PDir"           "$PDIR"

  ; ---- 控制面板「程序和功能」--------------------------------------------
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayName"     "${APPNAME} ${EDITION} ${PKGVER}（纯 CPU 滤镜 + 参数面板）"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayVersion"  "${PKGVER}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayIcon"     "$INSTDIR\Uninstall_${APPNAME}.exe"
  WriteRegStr HKLM "${UNINSTKEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr HKLM "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "Comments"        "OBS Studio 美颜滤镜 obs_beauty_filter + 顶层菜单参数面板"
  WriteRegStr HKLM "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall_${APPNAME}.exe"'
  WriteRegStr HKLM "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall_${APPNAME}.exe" /S'
  WriteRegDWORD HKLM "${UNINSTKEY}" "EstimatedSize" ${ESTSIZE}
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoRepair" 1

  ; ---- 开始菜单 -----------------------------------------------------------
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\卸载 ${APPNAME}.lnk" "$INSTDIR\Uninstall_${APPNAME}.exe"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\使用说明 README.lnk" "$INSTDIR\README.txt"
SectionEnd

; ==================================================================== 卸载
Function un.onInit
  SetRegView 64
  SetShellVarContext all

  ; 路径优先从安装时写的状态键里取 —— ProgramData / OBS 路径在别的机器上可能不同
  ReadEnvStr $PDIR "ProgramData"
  ${If} $PDIR == ""
    StrCpy $PDIR "C:\ProgramData"
  ${EndIf}
  ReadRegStr $0 HKLM "${REGKEY}" "PDir"
  ${If} $0 != ""
    StrCpy $PDIR $0
  ${EndIf}
  StrCpy $UIDIR "$PDIR\obs-studio\plugins\obs-beauty-ui\bin\64bit"
  ReadRegStr $0 HKLM "${REGKEY}" "UIDir"
  ${If} $0 != ""
    StrCpy $UIDIR $0
  ${EndIf}

  ReadRegStr $OBSROOT HKLM "SOFTWARE\OBS Studio" ""
  ${If} $OBSROOT == ""
    StrCpy $OBSROOT "$PROGRAMFILES64\obs-studio"
  ${EndIf}
  ; 默认按当前口径推导；安装时写入的 ObsDir 优先（老包写的是历史路径，照它还原）。
  StrCpy $OBSDIR "$PDIR\obs-studio\plugins\obs-beauty\bin\64bit"
  ReadRegStr $0 HKLM "${REGKEY}" "ObsDir"
  ${If} $0 != ""
    StrCpy $OBSDIR $0
  ${EndIf}

  ReadRegStr $0 HKLM "${REGKEY}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}

  Call un.CheckOBSRunning
FunctionEnd

Function un.CheckOBSRunning
  nsExec::Exec '"$SYSDIR\cmd.exe" /c tasklist /fi "imagename eq obs64.exe" /nh | "$SYSDIR\find.exe" /i "obs64.exe" >nul'
  Pop $0
  ${If} $0 == "0"
    MessageBox MB_ICONSTOP|MB_OK "OBS 正在运行，文件被占用删不掉。$\r$\n$\r$\n请先完全关闭 OBS 再卸载。$\r$\n$\r$\n现在什么都没改。" /SD IDOK
    Abort
  ${EndIf}
FunctionEnd

Section "Uninstall"
  DetailPrint "OBS 插件目录：$OBSDIR"

  ; ---- 1) 滤镜 DLL：有备份还原，没备份删除 -------------------------------
  ${If} ${FileExists} "$INSTDIR\backup\obs-beauty.dll.bak"
    Delete "$OBSDIR\obs-beauty.dll"
    CopyFiles /SILENT "$INSTDIR\backup\obs-beauty.dll.bak" "$OBSDIR\obs-beauty.dll"
    DetailPrint "已还原装之前的 obs-beauty.dll"
  ${Else}
    Delete "$OBSDIR\obs-beauty.dll"
    DetailPrint "已删除 obs-beauty.dll"
  ${EndIf}

  ${If} ${FileExists} "$INSTDIR\backup\onnxruntime.dll.bak"
    Delete "$OBSDIR\onnxruntime.dll"
    CopyFiles /SILENT "$INSTDIR\backup\onnxruntime.dll.bak" "$OBSDIR\onnxruntime.dll"
    DetailPrint "已还原装之前的 onnxruntime.dll"
  ${Else}
    Delete "$OBSDIR\onnxruntime.dll"
    DetailPrint "已删除 onnxruntime.dll"
  ${EndIf}

  ${If} ${FileExists} "$INSTDIR\backup\yunet.onnx.bak"
    Delete "$OBSDIR\models\yunet.onnx"
    CopyFiles /SILENT "$INSTDIR\backup\yunet.onnx.bak" "$OBSDIR\models\yunet.onnx"
    DetailPrint "已还原装之前的 models\yunet.onnx"
  ${Else}
    Delete "$OBSDIR\models\yunet.onnx"
    DetailPrint "已删除 models\yunet.onnx"
  ${EndIf}
  ReadRegDWORD $0 HKLM "${REGKEY}" "ModelsCreated"
  ${If} $0 == "1"
    RMDir "$OBSDIR\models"          ; 只删空目录，里面有别的模型就保留
    DetailPrint "已清理本包创建的 models 目录"
  ${Else}
    DetailPrint "models 目录装之前就有，保留"
  ${EndIf}

  ; ---- 4) 参数面板 DLL ---------------------------------------------------
  ${If} ${FileExists} "$INSTDIR\backup\obs-beauty-ui.dll.bak"
    Delete "$UIDIR\obs-beauty-ui.dll"
    CopyFiles /SILENT "$INSTDIR\backup\obs-beauty-ui.dll.bak" "$UIDIR\obs-beauty-ui.dll"
    DetailPrint "已还原装之前的 obs-beauty-ui.dll"
  ${Else}
    Delete "$UIDIR\obs-beauty-ui.dll"
    DetailPrint "已删除 obs-beauty-ui.dll"
  ${EndIf}
  RMDir "$UIDIR"
  RMDir "$PDIR\obs-studio\plugins\obs-beauty-ui\bin"
  RMDir "$PDIR\obs-studio\plugins\obs-beauty-ui"

  ; ---- 4b) 本包新建的滤镜插件目录链（RMDir 只删空目录）--------------------
  ; 目录名 obs-beauty 与 DLL 主名一致，是 OBS 全局插件扫描的硬性要求。
  RMDir "$OBSDIR"
  RMDir "$PDIR\obs-studio\plugins\obs-beauty\bin"
  RMDir "$PDIR\obs-studio\plugins\obs-beauty"

  ; ---- 5) 老包（3.1.2 及更早）装过的 SDK ----------------------------------
  ; 老包装在历史路径 $OBSROOT\obs-plugins\64bit\obs-beauty\，不是当前 $OBSDIR。
  ; 只在旧包自己写了 SdkCreated=1 时才删：那是旧包装进去的，不是用户自己的东西。
  StrCpy $1 "$OBSROOT\obs-plugins\64bit\obs-beauty"
  ReadRegDWORD $0 HKLM "${REGKEY}" "SdkCreated"
  ${If} $0 == "1"
    RMDir /r "$1"
    DetailPrint "已删除旧安装包装的 SDK 运行时（历史路径 obs-beauty\）"
  ${ElseIf} ${FileExists} "$1"
    DetailPrint "检测到历史路径的 SDK 目录，但不是本包/旧包装的，保留不动"
  ${EndIf}

  ; ---- 6) 面板窗口设置（可选）--------------------------------------------
  IfSilent keep_settings
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除面板保存的窗口大小/位置设置？$\r$\n$\r$\n$APPDATA\obs-studio\plugin_config\obs-beauty-ui\ui.ini$\r$\n$\r$\n选「否」就保留（下次重装还是原来的窗口大小）。" /SD IDNO IDNO keep_settings IDYES del_settings
  del_settings:
    Delete "$APPDATA\obs-studio\plugin_config\obs-beauty-ui\ui.ini"
    RMDir "$APPDATA\obs-studio\plugin_config\obs-beauty-ui"
    DetailPrint "已删除面板窗口设置"
  keep_settings:

  ; ---- 7) 收尾：快捷方式、注册表、安装目录 --------------------------------
  Delete "$SMPROGRAMS\${APPNAME}\卸载 ${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\使用说明 README.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"

  DeleteRegKey HKLM "${UNINSTKEY}"
  DeleteRegKey HKLM "${REGKEY}"

  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\md5.txt"
  Delete "$INSTDIR\Uninstall_${APPNAME}.exe"
  RMDir /r "$INSTDIR\backup"
  RMDir "$INSTDIR"
  DetailPrint "卸载完成"
SectionEnd

Function un.onUninstSuccess
  HideWindow
  MessageBox MB_ICONINFORMATION|MB_OK "已卸载 ${APPNAME}。$\r$\n$\r$\n装之前就有的文件已原样还原；装之前没有的已删除。$\r$\nOBS 场景里已加的滤镜参数存在场景文件里，卸载不会动。$\r$\n$\r$\n想再装回来，重新运行安装包即可。" /SD IDOK
FunctionEnd
