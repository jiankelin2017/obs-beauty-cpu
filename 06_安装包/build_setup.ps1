# ============================================================================
#  build_setup.ps1 - 打包 "OBS美颜" 安装包 (NSIS 3)
#
#  做什么：
#    1) 从 02_构建\build_<版本> 取滤镜/面板 DLL（CPU 线独立产物目录），
#    2) 校验版本串（防止把旧构建打进包里 —— C13 坑 #1）
#    3) 暂存到纯 ASCII 目录（NSIS 遇到中文源路径会报 no files found）
#    4) 生成 README.txt / md5.txt
#    5) 确保 obs-beauty.nsi 是 UTF-8 with BOM（否则中文界面乱码）
#    6) 调 makensis 编译，产物落到 06_安装包\OBS美颜_CPU_v<版本>.exe
#
#  版本从哪来（2026-11-09 改）：
#    默认读 01_源码\beauty_params.h 的 BEAUTY_BUILD_STR —— 源码是唯一口径，
#    不再在这里手抄版本号。打旧包用 -Version 显式指定（同时要配合
#    BEAUTY_BUILD_OUT 指向那版产物，否则版本串自检会拦）。
#
#  用法：
#    powershell -ExecutionPolicy Bypass -File build_setup.ps1
#    powershell -ExecutionPolicy Bypass -File build_setup.ps1 -KeepStage
#    powershell -ExecutionPolicy Bypass -File build_setup.ps1 -Version 1.0.12.0 `
#        -BuildOut "D:\插件\OBS美颜源码\02_构建\build_1.0.12.0"
# ============================================================================

[CmdletBinding()]
param(
    [switch]$KeepStage,
    [string]$Version,
    [string]$BuildOut
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$Nsi       = Join-Path $ScriptDir 'obs-beauty.nsi'
$Makensis  = 'C:\Program Files (x86)\NSIS\makensis.exe'

# CPU 四段版本轴（唯一口径见 01_源码\beauty_params.h 的 BEAUTY_BUILD_STR）。
# GPU 版是另一条独立轴（3.0.1，三段式），两条轴不可互比。
$ParamsH = Join-Path $Root '01_源码\beauty_params.h'
if (-not (Test-Path -LiteralPath $ParamsH)) { Write-Host "[build] ERROR: $ParamsH not found" -ForegroundColor Red; exit 1 }
$m = Select-String -LiteralPath $ParamsH -Pattern 'BEAUTY_BUILD_STR\s+"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"'
if (-not $m) { Write-Host "[build] ERROR: BEAUTY_BUILD_STR not found in beauty_params.h" -ForegroundColor Red; exit 1 }
$SrcVer = $m.Matches[0].Groups[1].Value
$Ver    = if ($Version) { $Version } else { $SrcVer }
if ($Ver -ne $SrcVer) {
    Write-Host "[build] WARNING: packaging $Ver but source says $SrcVer" -ForegroundColor Yellow
}

# 版本号单一来源，四个字段同轴
$FilterVer = $Ver
$PanelVer  = $Ver
$CoreVer   = $Ver

# CPU 产物与 3.1.40 定稿 DLL 物理隔离：默认只从独立目录取件，
# 绝不读 build_output（那里是 3.1.40，版本串自检会拦住但不必依赖它）。
# 需要临时指向别处（例如验证构建）时用 -BuildOut 或环境变量 BEAUTY_BUILD_OUT。
if (-not $BuildOut) {
    $BuildOut = if ($env:BEAUTY_BUILD_OUT) { $env:BEAUTY_BUILD_OUT } else { Join-Path $Root "02_构建\build_$Ver" }
}

function Fail($msg) { Write-Host "[build] ERROR: $msg" -ForegroundColor Red; exit 1 }
function Info($msg) { Write-Host "[build] $msg" }
function Md5($p) { (Get-FileHash -LiteralPath $p -Algorithm MD5).Hash.ToLower() }

if (-not (Test-Path -LiteralPath $Makensis)) { Fail "NSIS not found: $Makensis" }
if (-not (Test-Path -LiteralPath $Nsi))      { Fail "nsi not found: $Nsi" }

# ---------------------------------------------------------------- 源文件
$Src = [ordered]@{
    filter = Join-Path $BuildOut 'obs-beauty.dll'
    panel  = Join-Path $BuildOut 'obs-beauty-ui.dll'
    ort    = Join-Path $Root '05_验证\deps\runtime\onnxruntime.dll'
    yunet  = Join-Path $Root '05_验证\models\yunet.onnx'
}
# 兜底：05_验证 被清理过时用 参考文件\03_依赖与SDK_OBS\installer-stage 里那份
if (-not (Test-Path -LiteralPath $Src.ort)) {
    $Src.ort = Join-Path $Root '参考文件\03_依赖与SDK_OBS\installer-stage\onnxruntime.dll'
}
if (-not (Test-Path -LiteralPath $Src.yunet)) {
    $Src.yunet = Join-Path $Root '参考文件\03_依赖与SDK_OBS\installer-stage\yunet.onnx'
}

foreach ($k in $Src.Keys) {
    if (-not (Test-Path -LiteralPath $Src[$k])) { Fail "missing source ($k): $($Src[$k])" }
    $sz = (Get-Item -LiteralPath $Src[$k]).Length
    if ($sz -lt 100000) { Fail "source ($k) is only $sz bytes - looks truncated: $($Src[$k])" }
    Info ("source {0,-7} {1,10} bytes  {2}" -f $k, $sz, $Src[$k])
}

# --------------------------------------------------- 版本串自检（防止打旧构建）
function Assert-ContainsBytes([string]$path, [string]$needle) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $text  = [System.Text.Encoding]::ASCII.GetString($bytes)
    if ($text.IndexOf($needle, [System.StringComparison]::Ordinal) -lt 0) {
        Fail "$([System.IO.Path]::GetFileName($path)) does not contain '$needle' - it is a stale build"
    }
}
# 注：2026-11-07 起 CoreEngine::version() 直接返回 BEAUTY_BUILD_STR，
# 滤镜 DLL 里不再残留旧版本串；自检要求两件 DLL 都含当前轴的版本串。
Assert-ContainsBytes $Src.filter $Ver
Assert-ContainsBytes $Src.panel  $Ver
Assert-ContainsBytes $Src.filter 'obs_beauty_filter'
Info "version strings OK (CPU $Ver / obs_beauty_filter)"

# ---------------------------------------------------------------- 暂存目录
$Stage = Join-Path $env:TEMP 'obsbeauty_pkg'
if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
foreach ($d in 'filter','core','core\models','panel','docs','out') {
    New-Item -ItemType Directory -Path (Join-Path $Stage $d) -Force | Out-Null
}
if ($Stage -match '[^\x20-\x7E]') { Fail "stage path must be pure ASCII: $Stage" }

Copy-Item -LiteralPath $Src.filter -Destination (Join-Path $Stage 'filter\obs-beauty.dll')
Copy-Item -LiteralPath $Src.ort    -Destination (Join-Path $Stage 'core\onnxruntime.dll')
Copy-Item -LiteralPath $Src.yunet  -Destination (Join-Path $Stage 'core\models\yunet.onnx')
Copy-Item -LiteralPath $Src.panel  -Destination (Join-Path $Stage 'panel\obs-beauty-ui.dll')

$Md5Filter = Md5 (Join-Path $Stage 'filter\obs-beauty.dll')
$Md5Panel  = Md5 (Join-Path $Stage 'panel\obs-beauty-ui.dll')
$Md5Ort    = Md5 (Join-Path $Stage 'core\onnxruntime.dll')
$Md5Yunet  = Md5 (Join-Path $Stage 'core\models\yunet.onnx')

# 和已装机文件对照：不一致只提示（这不是错误，装机版可能本来就是旧的）
$Installed = @{
    'filter\obs-beauty.dll'       = 'C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\obs-beauty.dll'
    'core\onnxruntime.dll'        = 'C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\onnxruntime.dll'
    'core\models\yunet.onnx'      = 'C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\models\yunet.onnx'
    'panel\obs-beauty-ui.dll'     = 'C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\obs-beauty-ui.dll'
}
foreach ($rel in $Installed.Keys) {
    $ip = $Installed[$rel]
    if (Test-Path -LiteralPath $ip) {
        $im = Md5 $ip
        $sm = Md5 (Join-Path $Stage $rel)
        if ($im -ne $sm) { Write-Host "[build] NOTE: installed copy differs from package: $rel ($im vs $sm)" -ForegroundColor Yellow }
    }
}

# ---------------------------------------------------------------- README.txt
$readme = @"
OBS美颜 ${Ver}  ——  使用说明
================================================================

一、这个包装了什么
----------------------------------------------------------------
一共 4 个文件（外加本说明、md5 清单和卸载程序）：

  滤镜    C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\obs-beauty.dll
  运行时  C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\onnxruntime.dll
  模型    C:\ProgramData\obs-studio\plugins\obs-beauty\bin\64bit\models\yunet.onnx
  面板    C:\ProgramData\obs-studio\plugins\obs-beauty-ui\bin\64bit\obs-beauty-ui.dll

  两个插件目录名（obs-beauty / obs-beauty-ui）必须与各自 DLL 主名一致，
  且 DLL 必须在 bin\64bit\ 下；名字对不上 OBS 会静默跳过且不写日志。

  版本：滤镜 ${FilterVer} · 面板 ${PanelVer} · 引擎 ${CoreVer}

  md5（本包内四件，可用来核对装进去的是不是同一份）：
    ${Md5Filter}  obs-beauty.dll
    ${Md5Panel}  obs-beauty-ui.dll
    ${Md5Ort}  onnxruntime.dll
    ${Md5Yunet}  yunet.onnx

  onnxruntime.dll 与 models\yunet.onnx 必须待在滤镜 DLL 旁边：
  滤镜按自身所在目录找它们。放错位置不会报错，但人脸检测会静默失效，
  磨皮退化成全帧（等于没有脸部保护）。

本包不含外部运行库（约 97 MB 的闭源组件）。3.1.7 起默认引擎已是自研
CoreEngine；机器上本来就有 obs-beauty\ SDK 目录的，装/卸都不会动它。


二、怎么用
----------------------------------------------------------------
  1. 打开 OBS Studio
  2. 在要美颜的源（摄像头/采集卡/窗口）上右键 ->「滤镜」
  3. 左下角「+」-> 选「OBS美颜」-> 确定
  4. 顶层菜单「美颜」->「参数面板」打开调参窗口
     （面板左下角显示 v${PanelVer}；「美颜」->「关于」里可看滤镜版本 ${FilterVer}）

  面板里的档位（磨皮/美白/红润/清晰…）都是实时生效的；窗口大小和位置
  会被记住，存在：
    %APPDATA%\obs-studio\plugin_config\obs-beauty-ui\ui.ini


三、怎么卸载
----------------------------------------------------------------
  开始菜单「OBS美颜」->「卸载 OBS美颜」
  或 控制面板 ->「程序和功能」-> 找「OBS美颜 ${Ver}」-> 卸载
  或 直接运行：<安装目录>\Uninstall_OBS美颜.exe

  卸载规则（装之前什么样，卸完还是什么样）：
    · 装之前就有同名文件  -> 先用备份还原回去，不直接删
    · 装之前没有          -> 删除
    · 不是本包装的东西    -> 一律不动（例如别人放的 obs-beauty\ SDK、
                             models 目录里的其他模型）
  卸载会问要不要同时删掉面板窗口设置（ui.ini），默认保留。

  OBS 必须关闭，否则 DLL 被占用删不掉。


四、装完怎么确认真的生效
----------------------------------------------------------------
  OBS 启动后看日志：%APPDATA%\obs-studio\logs\ 里最新那个 txt，应有：

    [obs-beauty] init OK (v${FilterVer}, engine=core/${CoreVer}, region=on ...)
    [obs-beauty] filter registered as 'obs_beauty_filter' (v${FilterVer})
    [obs-beauty-ui] 模块已加载 v${PanelVer}
    [obs-beauty-ui] 顶层菜单已添加

  关键看两处：
    engine=core     而不是 nama     -> 用的是自研引擎
    region=on       而不是 off       -> 人脸掩码正常（模型装对了）

  若出现 "has NO face mask" 之类的 WARN，说明 onnxruntime.dll 或
  models\yunet.onnx 没落在滤镜 DLL 旁边。


五、常见问题
----------------------------------------------------------------
  Q: 装的时候提示「OBS 正在运行」
  A: 托盘里也退干净再装。DLL 被占用时替换会失败，装到一半最麻烦。

  Q: 装完 OBS 里看不到「OBS美颜」滤镜
  A: 看 四 里的日志。没有 [obs-beauty] 行 = DLL 没加载（版本不匹配或被杀软拦）。

  Q: 「程序和功能」里出现两条 OBS美颜
  A: 老版本（3.0.20 / 3.1.2）与本版共用同一个注册表键，正常升级不会重复；
     若真出现两条，把旧的那条卸载掉即可。

  Q: 磨皮拉到 0 时「锐化」滑块没反应
  A: 已知设计：锐化是「回填磨皮削掉的细节」，磨皮为 0 时按设计不动。

  Q: 想彻底恢复出厂
  A: 卸载，再删掉 %APPDATA%\obs-studio\plugin_config\obs-beauty-ui\ 即可。


六、文件清单
----------------------------------------------------------------
  本次打包时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
  打包脚本    ：06_安装包\build_setup.ps1
  安装脚本    ：06_安装包\obs-beauty.nsi
"@

$readmePath = Join-Path $Stage 'docs\README.txt'
[System.IO.File]::WriteAllText($readmePath, ($readme -replace "`r?`n", "`r`n"), (New-Object System.Text.UTF8Encoding($true)))

$manifest = @(
    "$Md5Filter  obs-beauty.dll        (滤镜 ${FilterVer})"
    "$Md5Panel  obs-beauty-ui.dll     (面板 ${PanelVer})"
    "$Md5Ort  onnxruntime.dll       (引擎运行时)"
    "$Md5Yunet  yunet.onnx            (人脸模型)"
) -join "`r`n"
$manifest = "OBS美颜 ${Ver} 文件清单`r`n$('-' * 60)`r`n$manifest`r`n"
[System.IO.File]::WriteAllText((Join-Path $Stage 'docs\md5.txt'), $manifest, (New-Object System.Text.UTF8Encoding($true)))

# ---------------------------------------------- nsi 必须是 UTF-8 with BOM
$nsiBytes = [System.IO.File]::ReadAllBytes($Nsi)
if ($nsiBytes.Length -lt 3 -or $nsiBytes[0] -ne 0xEF -or $nsiBytes[1] -ne 0xBB -or $nsiBytes[2] -ne 0xBF) {
    $bom = [byte[]](0xEF,0xBB,0xBF)
    [System.IO.File]::WriteAllBytes($Nsi, ($bom + $nsiBytes))
    Info 'added UTF-8 BOM to obs-beauty.nsi'
}

# ---------------------------------------------------------------- 编译
# 注意：/DOUTFILE 里不能出现中文 —— makensis 按控制台代码页解析命令行，
# 中文名会被写成乱码文件名。这里先出 ASCII 名，编译完再重命名。
$outName = "OBS美颜_CPU_v$Ver.exe"
$outExe  = Join-Path $Stage "out\OBSBeauty_CPU_Setup_v$Ver.exe"

Info "compiling with $Makensis ..."
# 版本号只在本脚本顶部维护，/D 传给 nsi（nsi 里的同名 define 只在手工编译时兜底）
$nsiArgs = @(
    "/DSRCDIR=$Stage",
    "/DOUTFILE=$outExe",
    "/DPKGVER=$Ver",
    "/DFILTERVER=$FilterVer",
    "/DPANELVER=$PanelVer",
    "/DCOREVER=$CoreVer",
    $Nsi
)
& $Makensis @nsiArgs
if ($LASTEXITCODE -ne 0) { Fail "makensis failed with exit code $LASTEXITCODE" }
if (-not (Test-Path -LiteralPath $outExe)) { Fail "makensis reported success but produced no exe" }

$final = Join-Path $ScriptDir $outName
Copy-Item -LiteralPath $outExe -Destination $final -Force

$size = (Get-Item -LiteralPath $final).Length
$md5  = Md5 $final
Info ''
Info '============================================================'
Info ("output : {0}" -f $final)
Info ("size   : {0:N0} bytes ({1:N2} MB)" -f $size, ($size / 1MB))
Info ("md5    : {0}" -f $md5)
Info '============================================================'
Info ''
Info 'payload inside the exe:'
Info ("  obs-beauty.dll        {0,10}  {1}" -f (Get-Item -LiteralPath $Src.filter).Length, $Md5Filter)
Info ("  obs-beauty-ui.dll     {0,10}  {1}" -f (Get-Item -LiteralPath $Src.panel).Length, $Md5Panel)
Info ("  onnxruntime.dll       {0,10}  {1}" -f (Get-Item -LiteralPath $Src.ort).Length, $Md5Ort)
Info ("  models\yunet.onnx     {0,10}  {1}" -f (Get-Item -LiteralPath $Src.yunet).Length, $Md5Yunet)

if (-not $KeepStage) {
    Remove-Item -LiteralPath $Stage -Recurse -Force
    Info "stage cleaned: $Stage"
} else {
    Info "stage kept: $Stage"
}
