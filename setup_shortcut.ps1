# 生成应用图标 + 桌面快捷方式
$ErrorActionPreference = "Stop"
$dir = "D:\py\AI_CAMP"
Add-Type -AssemblyName System.Drawing

# ---- 1) 生成图标 app.ico（蓝紫渐变 + 靶心）----
$bmp = New-Object System.Drawing.Bitmap(64, 64)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$grad = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (New-Object System.Drawing.Point(0, 0)), (New-Object System.Drawing.Point(64, 64)),
    [System.Drawing.Color]::FromArgb(91, 141, 239), [System.Drawing.Color]::FromArgb(123, 110, 240))
$g.FillRectangle($grad, 0, 0, 64, 64)
$g.FillEllipse([System.Drawing.Brushes]::White, 6, 6, 52, 52)
$g.FillEllipse($grad, 16, 16, 32, 32)
$g.FillEllipse([System.Drawing.Brushes]::White, 24, 24, 16, 16)
$g.FillEllipse((New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(239, 68, 68))), 27, 27, 10, 10)
$h = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($h)
$fs = [System.IO.File]::Create("$dir\app.ico")
$icon.Save($fs)
$fs.Close()
Write-Output "图标已生成: $dir\app.ico"

# ---- 2) 创建桌面快捷方式 ----
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = "$desktop\导师匹配系统.lnk"
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = "$dir\run.bat"
$lnk.WorkingDirectory = $dir
$lnk.IconLocation = "$dir\app.ico, 0"
$lnk.Description = "益志领导师匹配系统"
$lnk.WindowStyle = 1
$lnk.Save()
Write-Output "快捷方式已创建: $lnkPath"
