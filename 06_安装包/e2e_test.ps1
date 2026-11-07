# e2e_test.ps1 - 需要管理员权限运行。分两段验证安装包的装/卸逻辑。
#   Phase A：模拟"机器上没装过" -> 装 -> 卸 -> 应回到什么都没有
#   Phase B：放回原文件 -> 装 -> 卸 -> 应原样还原（逐位相同）
# 结果写进 $T\log.txt，结束时写 done.flag。

$ErrorActionPreference = 'Continue'

$T        = Join-Path $env:TEMP 'obsbeauty_test'
$Log      = Join-Path $T 'log.txt'
$Safety   = Join-Path $T 'safety'
$Done     = Join-Path $T 'done.flag'
$Setup    = Join-Path $PSScriptRoot 'OBS美颜_CPU_v1.0.0.3.exe'

# 2026-11-07 C-1：与 obs-beauty.nsi / install_1.0.0.3.bat 统一到 ProgramData 全局插件路径。
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

L '  A3 run uninstaller /S'
$rc = Run-Uninstall
Assert ($rc -eq 0) 'A3 uninstaller started'
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
