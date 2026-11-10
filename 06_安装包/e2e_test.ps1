# e2e_test.ps1 - 需要管理员权限运行。分两段验证安装包的装/卸逻辑。
#   Phase A：模拟"机器上没装过" -> 装 -> 卸 -> 应回到什么都没有
#   Phase B：放回原文件 -> 装 -> 卸 -> 应原样还原（逐位相同）
# 结果写进 $T\log.txt，结束时写 done.flag。

$ErrorActionPreference = 'Continue'

$T        = Join-Path $env:TEMP 'obsbeauty_test'
$Log      = Join-Path $T 'log.txt'
$Safety   = Join-Path $T 'safety'
$Done     = Join-Path $T 'done.flag'
# 2026-11-09：版本与 build_setup.ps1 / beauty_params.h 同源，不再手抄文件名。
# 以前这里写死 v1.0.3.0，升版后脚本会一直拿旧包做装卸回归（静默测错对象）。
# 要复测历史包时设 BEAUTY_E2E_SETUP 指向那个 exe 的完整路径。
if ($env:BEAUTY_E2E_SETUP) {
    $Setup = $env:BEAUTY_E2E_SETUP
} else {
    $ParamsH = Join-Path (Split-Path -Parent $PSScriptRoot) '01_源码\beauty_params.h'
    $mv = Select-String -LiteralPath $ParamsH -Pattern 'BEAUTY_BUILD_STR\s+"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"'
    if (-not $mv) { throw "BEAUTY_BUILD_STR not found in $ParamsH" }
    $Setup = Join-Path $PSScriptRoot ("OBS美颜_CPU_v{0}.exe" -f $mv.Matches[0].Groups[1].Value)
}
if (-not (Test-Path -LiteralPath $Setup)) { throw "setup exe not found: $Setup" }

# 2026-11-07 C-1：与 obs-beauty.nsi / install_1.0.3.0.bat 统一到 ProgramData 全局插件路径。
# 目录名 obs-beauty 必须与 obs-beauty.dll 主名一致，否则 OBS 静默跳过。
$OBSDIR   = 'C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit'
$FILTER   = Join-Path $OBSDIR 'obs-beauty.dll'
$ORT      = Join-Path $OBSDIR 'onnxruntime.dll'
$MODELDIR = Join-Path $OBSDIR 'models'
$MODEL    = Join-Path $MODELDIR 'yunet.onnx'
$UIDIR    = 'C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit'
$UI       = Join-Path $UIDIR 'obs-beauty-ui.dll'
$INSTDIR  = 'C:\Program Files\obs-beauty'
$UNINST   = Join-Path $INSTDIR 'Uninstall_OBS美颜.exe'
$REGSELF  = 'HKLM:\SOFTWARE\OBSBeauty.NamaBeauty'
$REGUN    = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\OBSBeauty.NamaBeauty'

New-Item -ItemType Directory -Path $T -Force | Out-Null
New-Item -ItemType Directory -Path $Safety -Force | Out-Null
Remove-Item $Log, $Done -Force -ErrorAction SilentlyContinue
Set-Content -LiteralPath $Log -Value "=== e2e start $(Get-Date -Format o) ===" -Encoding UTF8

function L($m) { Add-Content -LiteralPath $Log -Value $m -Encoding UTF8; Write-Host $m }
function Md5($p) { if (Test-Path -LiteralPath $p) { (Get-FileHash -LiteralPath $p -Algorithm MD5).Hash.ToLower() } else { 'MISSING' } }
function Chk($ok, $what) { if ($ok) { L "  PASS  $what" } else { L "  FAIL  $what" }; return $ok }

$fails = 0
function Assert($ok, $what) { if (-not (Chk $ok $what)) { $script:fails++ } }

function Wait-RegGone($path, $sec) {
    $end = (Get-Date).AddSeconds($sec)
    while ((Test-Path $path) -and (Get-Date) -lt $end) { Start-Sleep -Milliseconds 250 }
    return -not (Test-Path $path)
}

# 2026-11-09：卸载器的文件删除是异步的 —— 它先删文件、最后删注册表，
# 但 Delete 失败不会报错也不会重试。原脚本等注册表一消失就硬睡 1.2 秒再断言，
# 改成轮询：只放宽时间窗口，不改变「最终有没有删掉」的判定。
function Wait-PathGone($path, $sec) {
    $end = (Get-Date).AddSeconds($sec)
    while ((Test-Path -LiteralPath $path) -and (Get-Date) -lt $end) { Start-Sleep -Milliseconds 250 }
    return -not (Test-Path -LiteralPath $path)
}

# 2026-11-09：把 <InstallDir>\backup 的内容打出来。卸载器有「有备份就还原」的分支
# （obs-beauty.nsi:382/392/402/419），而安装器对已存在的备份**永不覆盖**（nsi:223 是 IfNot）。
# 于是「装过两次再卸」时，卸载器还原的是更早那一版 —— 文件当然还在。
# Phase A 若没清掉这个目录，A3 的 6 条 FAIL 会被读成「删除失败」，方向就指错了。
function Show-Backup([string]$tag) {
    $bk = Join-Path $INSTDIR 'backup'
    if (-not (Test-Path -LiteralPath $bk)) {
        L ("    [bak {0}] none  ({1})" -f $tag, $bk)
        return
    }
    $items = @(Get-ChildItem -LiteralPath $bk -File -ErrorAction SilentlyContinue)
    L ("    [bak {0}] {1} file(s) in {2}" -f $tag, $items.Count, $bk)
    foreach ($it in $items) {
        L ("      {0,-28} {1,10} B  {2}" -f $it.Name, $it.Length, (Md5 $it.FullName))
    }
}

function Run-Setup([string]$exe, [string]$silent) {
    $p = Start-Process -FilePath $exe -ArgumentList $silent -PassThru -Wait -ErrorAction SilentlyContinue
    if ($null -eq $p) { return -1 }
    return $p.ExitCode
}

function Run-Uninstall {
    if (-not (Test-Path -LiteralPath $UNINST)) { L "  (uninstaller not found at $UNINST)"; return -1 }
    $p = Start-Process -FilePath $UNINST -ArgumentList '/S' -PassThru -ErrorAction SilentlyContinue
    if ($null -eq $p) { return -1 }
    Start-Sleep -Seconds 1
    $ok = Wait-RegGone $REGSELF 120
    L "  (uninstall registry key gone: $ok)"
    Start-Sleep -Milliseconds 1200
    return 0
}

# ---------------------------------------------------------------- safety
L ''
L '### safety backup of current install'
$safetyMap = @{}
foreach ($pair in @(@('filter', $FILTER), @('ort', $ORT), @('model', $MODEL), @('ui', $UI))) {
    $name = $pair[0]; $src = $pair[1]
    if (Test-Path -LiteralPath $src) {
        $dst = Join-Path $Safety ($name + '.dll' -replace '\.dll$', '')
        $dst = Join-Path $Safety $name
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $safetyMap[$name] = @{ path = $src; copy = $dst; md5 = (Md5 $src) }
        L ("  saved {0,-6} {1}  {2}" -f $name, (Md5 $src), $src)
    } else {
        L "  (missing before test: $src)"
    }
}

# ================================================================ PHASE R (optional)
# 只在 BEAUTY_E2E_REPRO_UPGRADE=1 时跑。不判 PASS/FAIL，只把「装过旧版 -> 装新版 -> 卸载，
# 到底留下什么」量出来。这一段不产生 Assert，所以断言总数仍是 40 项。
#
# 为什么需要它：卸载器的语义是「装之前有什么就还原成什么」，而备份只写一次、永不刷新
# （nsi:223 的 IfNot FileExists）。所以升级装卸后，用户看到的是「卸载不掉、退回旧版」。
# 这是设计选择还是缺陷，需要先用数字确认，再让人决定。
#
# 1.0.13.11 起安装器改成「只有首次安装才备份」（注册表 Version 为空 = 首次）。
# 期望值因此变了，读日志时按这个比：
#   1.0.13.10 及更早   R2 后 backup 有 4 个 .bak（dll.bak = 505856）→ R3 survivor 505856
#   1.0.13.11 及以后   R2 后 backup 为 none（升级不备份、旧 .bak 被清）→ R3 四个全 gone
# R2 那行 [bak after R2] 是区分「新安装器是否真的生效」的最快证据。
if ($env:BEAUTY_E2E_REPRO_UPGRADE -eq '1') {
    $SetupOld = Join-Path $PSScriptRoot 'OBS美颜_CPU_v1.0.13.9.exe'
    if (-not (Test-Path -LiteralPath $SetupOld)) { throw "repro needs $SetupOld" }

    L ''
    L '### PHASE R - upgrade-then-uninstall repro (informational, no PASS/FAIL)'
    L '  R0 wipe to a real clean slate (no INSTDIR, no backup, no registry)'
    foreach ($rp in @($FILTER, $ORT, $MODEL, $UI)) {
        if (Test-Path -LiteralPath $rp) { Remove-Item -LiteralPath $rp -Force -ErrorAction SilentlyContinue }
    }
    foreach ($rd in @($MODELDIR, $UIDIR, $INSTDIR)) {
        if (Test-Path -LiteralPath $rd) { Remove-Item -LiteralPath $rd -Recurse -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item -LiteralPath $REGSELF -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $REGUN   -Recurse -Force -ErrorAction SilentlyContinue
    Show-Backup 'after R0'

    L ("  R1 install the older package first (the ""older version already installed"" case): {0}" -f (Split-Path -Leaf $SetupOld))
    $rc = Run-Setup $SetupOld '/S'
    Start-Sleep -Seconds 1
    L ("    R1 exit {0}  filter {1} B  {2}" -f $rc, (Get-Item -LiteralPath $FILTER).Length, (Md5 $FILTER))

    L ("  R2 install the package under test over it: {0}" -f (Split-Path -Leaf $Setup))
    $rc = Run-Setup $Setup '/S'
    Start-Sleep -Seconds 1
    L ("    R2 exit {0}  filter {1} B  {2}" -f $rc, (Get-Item -LiteralPath $FILTER).Length, (Md5 $FILTER))
    Show-Backup 'after R2'

    L '  R3 uninstall -> what is left behind?'
    $rc = Run-Uninstall
    Start-Sleep -Seconds 1
    L "    R3 exit $rc"
    foreach ($rp in @($FILTER, $ORT, $MODEL, $UI)) {
        if (Test-Path -LiteralPath $rp) {
            L ("    survivor {0,-18} {1,10} B  {2}" -f (Split-Path -Leaf $rp), (Get-Item -LiteralPath $rp).Length, (Md5 $rp))
        } else {
            L ("    gone     {0}" -f (Split-Path -Leaf $rp))
        }
    }
    L ("    INSTDIR exists={0}  models dir exists={1}" -f (Test-Path -LiteralPath $INSTDIR), (Test-Path -LiteralPath $MODELDIR))

    L '  R4 wipe again so PHASE A starts from a real clean slate'
    foreach ($rp in @($FILTER, $ORT, $MODEL, $UI)) {
        if (Test-Path -LiteralPath $rp) { Remove-Item -LiteralPath $rp -Force -ErrorAction SilentlyContinue }
    }
    foreach ($rd in @($MODELDIR, $UIDIR, $INSTDIR)) {
        if (Test-Path -LiteralPath $rd) { Remove-Item -LiteralPath $rd -Recurse -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item -LiteralPath $REGSELF -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $REGUN   -Recurse -Force -ErrorAction SilentlyContinue
    L '  R done (state wiped; PHASE A takes over)'
}

# ================================================================ PHASE A
L ''
L '### PHASE A - fresh machine simulation'
L '  removing installed files to simulate a machine without the plugin'
foreach ($name in @('filter', 'ort', 'ui', 'model')) {
    if (Test-Path -LiteralPath $safetyMap[$name].path) {
        Remove-Item -LiteralPath $safetyMap[$name].path -Force -ErrorAction SilentlyContinue
    }
}
if (Test-Path -LiteralPath $MODELDIR) { Remove-Item -LiteralPath $MODELDIR -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path -LiteralPath $UIDIR)     { Remove-Item -LiteralPath $UIDIR -Recurse -Force -ErrorAction SilentlyContinue }
# 2026-11-09：原版 A0 只清 ProgramData 四件，没清 $INSTDIR 与两个注册表键。
# 上一包装留下的 $INSTDIR\backup\*.bak 会让 A3 走「还原」分支，于是判据把
# 「还原成了更早那一版」读成「没删掉」。要真的模拟「机器上没装过」，这里必须一起清。
Show-Backup 'at A0 (before wipe)'
Remove-Item -LiteralPath $INSTDIR -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $REGSELF -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $REGUN   -Recurse -Force -ErrorAction SilentlyContinue
L ("    A0 clean slate: INSTDIR exists={0} REGSELF exists={1} REGUN exists={2}" -f
    (Test-Path -LiteralPath $INSTDIR), (Test-Path -LiteralPath $REGSELF), (Test-Path -LiteralPath $REGUN))
Assert (-not (Test-Path -LiteralPath $FILTER)) 'A0 filter removed'
Assert (-not (Test-Path -LiteralPath $MODELDIR)) 'A0 models dir removed'

L '  A1 run setup /S'
$rc = Run-Setup $Setup '/S'
L "  setup exit code: $rc"
Assert ($rc -eq 0) 'A1 setup exit code 0'
Start-Sleep -Seconds 1

L '  A2 verify installed state'
Assert ((Md5 $FILTER) -eq $safetyMap['filter'].md5) 'A2 filter dll md5 matches package'
Assert ((Md5 $ORT)    -eq $safetyMap['ort'].md5)    'A2 onnxruntime md5 matches package'
Assert ((Md5 $MODEL)  -eq $safetyMap['model'].md5)  'A2 yunet.onnx md5 matches package'
Assert ((Md5 $UI)     -eq $safetyMap['ui'].md5)     'A2 panel dll md5 matches package'
Assert (Test-Path -LiteralPath $UNINST) 'A2 uninstaller written to INSTDIR'
Assert (Test-Path -LiteralPath (Join-Path $INSTDIR 'README.txt')) 'A2 README written'
Assert (Test-Path -LiteralPath (Join-Path $INSTDIR 'md5.txt')) 'A2 md5 manifest written'
Assert (Test-Path -LiteralPath $REGSELF) 'A2 registry state key exists'
Assert (Test-Path -LiteralPath $REGUN)   'A2 uninstall registry key exists'
$dn = (Get-ItemProperty -LiteralPath $REGUN -ErrorAction SilentlyContinue).DisplayName
$dv = (Get-ItemProperty -LiteralPath $REGUN -ErrorAction SilentlyContinue).DisplayVersion
$us = (Get-ItemProperty -LiteralPath $REGUN -ErrorAction SilentlyContinue).UninstallString
$es = (Get-ItemProperty -LiteralPath $REGUN -ErrorAction SilentlyContinue).EstimatedSize
L "    DisplayName    = $dn"
L "    DisplayVersion = $dv"
L "    EstimatedSize  = $es KB"
L "    UninstallString= $us"
Assert ((Test-Path -LiteralPath "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\OBS美颜") -or (Test-Path -LiteralPath "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\OBS美颜")) 'A2 start menu folder created'
Assert ((Get-ItemProperty -LiteralPath $REGSELF).ModelsCreated -eq 1) 'A2 ModelsCreated=1 (we created models dir)'
# 2026-11-09：把卸载器将要读的三个路径打出来 —— A3 若删不掉文件，
# 第一步就是看这里和下面 A3 的 gone 行对不对得上。
$sv = Get-ItemProperty -LiteralPath $REGSELF
L "    reg ObsDir  = $($sv.ObsDir)"
L "    reg UIDir   = $($sv.UIDir)"
L "    reg PDir    = $($sv.PDir)"

L '  A3 run uninstaller /S'
$rc = Run-Uninstall
Assert ($rc -eq 0) 'A3 uninstaller started'
# 卸载器删文件是异步的，最多等 8 秒；等不到仍然判 FAIL。
$gFilter = Wait-PathGone $FILTER 8
$gOrt    = Wait-PathGone $ORT 8
$gModel  = Wait-PathGone $MODELDIR 8
$gUi     = Wait-PathGone 'C:\ProgramData\obs-studio\plugins\obs-beauty-ui' 8
L ("    gone after wait: filter={0} ort={1} models={2} ui={3}" -f $gFilter, $gOrt, $gModel, $gUi)
# 2026-11-09：等不到就量一下活下来的东西 —— 体积能直接分辨「被还原成了旧版」还是「压根没删」。
foreach ($sp in @($FILTER, $ORT, $MODEL, $UI)) {
    if (Test-Path -LiteralPath $sp) {
        L ("    survivor {0,-18} {1,10} B  {2}" -f (Split-Path -Leaf $sp), (Get-Item -LiteralPath $sp).Length, (Md5 $sp))
    }
}
Assert (-not (Test-Path -LiteralPath $FILTER)) 'A3 filter dll removed'
Assert (-not (Test-Path -LiteralPath $ORT))    'A3 onnxruntime removed'
Assert (-not (Test-Path -LiteralPath $MODEL))  'A3 model removed'
Assert (-not (Test-Path -LiteralPath $UI))     'A3 panel dll removed'
Assert (-not (Test-Path -LiteralPath $MODELDIR)) 'A3 models dir removed (was ours)'
Assert (-not (Test-Path -LiteralPath 'C:\ProgramData\obs-studio\plugins\obs-beauty-ui')) 'A3 ProgramData ui chain removed'
Assert (-not (Test-Path -LiteralPath $INSTDIR)) 'A3 install dir removed'
Assert (-not (Test-Path -LiteralPath $REGSELF)) 'A3 registry state key removed'
Assert (-not (Test-Path -LiteralPath $REGUN))   'A3 uninstall registry key removed'
Assert (-not (Test-Path -LiteralPath 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\OBS美颜')) 'A3 start menu folder removed'

# ================================================================ PHASE B
L ''
L '### PHASE B - upgrade / backup-restore path'
L '  restoring the original files, then install over them'
foreach ($name in @('filter', 'ort', 'ui', 'model')) {
    if ($safetyMap.ContainsKey($name)) {
        $dst = $safetyMap[$name].path
        $dir = Split-Path -Parent $dst
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Copy-Item -LiteralPath $safetyMap[$name].copy -Destination $dst -Force
    }
}
Assert ((Md5 $FILTER) -eq $safetyMap['filter'].md5) 'B0 original filter restored to place'
Assert ((Md5 $MODEL)  -eq $safetyMap['model'].md5)  'B0 original model restored to place'

L '  B1 run setup /S over existing files'
$rc = Run-Setup $Setup '/S'
L "  setup exit code: $rc"
Assert ($rc -eq 0) 'B1 setup exit code 0'
Start-Sleep -Seconds 1
Assert ((Md5 $FILTER) -eq $safetyMap['filter'].md5) 'B1 filter dll correct after install'
Assert (Test-Path -LiteralPath (Join-Path $INSTDIR 'backup\obs-beauty.dll.bak')) 'B1 previous filter backed up'
Assert ((Get-ItemProperty -LiteralPath $REGSELF).ModelsCreated -eq 0) 'B1 ModelsCreated=0 (models dir pre-existed)'

L '  B2 run uninstaller /S'
$rc = Run-Uninstall
Assert ($rc -eq 0) 'B2 uninstaller started'
Assert ((Md5 $FILTER) -eq $safetyMap['filter'].md5) 'B2 filter dll RESTORED from backup'
Assert ((Md5 $ORT)    -eq $safetyMap['ort'].md5)    'B2 onnxruntime RESTORED from backup'
Assert ((Md5 $MODEL)  -eq $safetyMap['model'].md5)  'B2 model RESTORED from backup'
Assert ((Md5 $UI)     -eq $safetyMap['ui'].md5)     'B2 panel dll RESTORED from backup'
Assert (Test-Path -LiteralPath $MODELDIR) 'B2 models dir kept (pre-existed)'
Assert (-not (Test-Path -LiteralPath $INSTDIR)) 'B2 install dir removed'
Assert (-not (Test-Path -LiteralPath $REGSELF)) 'B2 registry state key removed'
Assert (-not (Test-Path -LiteralPath $REGUN))   'B2 uninstall registry key removed'

L ''
L "=== e2e end $(Get-Date -Format o) : $fails failure(s) ==="
L '### FINAL STATE (must equal the state before the test)'
foreach ($name in @('filter', 'ort', 'ui', 'model')) {
    L ("  {0,-6} {1}" -f $name, (Md5 $safetyMap[$name].path))
}
Set-Content -LiteralPath $Done -Value 'done' -Encoding UTF8
