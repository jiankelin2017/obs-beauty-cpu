param(
    [Parameter(Mandatory=$true)][string]$Src,
    [Parameter(Mandatory=$true)][string]$Dst,
    [int]$MaxSide = 640
)

Add-Type -AssemblyName System.Drawing

$img = [System.Drawing.Image]::FromFile($Src)
try {
    $scale = [Math]::Min(1.0, $MaxSide / [Math]::Max($img.Width, $img.Height))
    $w = [int][Math]::Round($img.Width * $scale)
    $h = [int][Math]::Round($img.Height * $scale)
    # keep both sides even so downstream maths stays simple
    if ($w % 2 -ne 0) { $w++ }
    if ($h % 2 -ne 0) { $h++ }

    $bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.DrawImage($img, 0, 0, $w, $h)
    $g.Dispose()

    $bmp.Save($Dst, [System.Drawing.Imaging.ImageFormat]::Bmp)
    $bmp.Dispose()
    Write-Output ("OK {0}x{1} -> {2}" -f $w, $h, $Dst)
}
finally {
    $img.Dispose()
}
