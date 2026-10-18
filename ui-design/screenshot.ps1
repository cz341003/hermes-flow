<#
  HERMES · Migration Control Plane — UI 设计稿截图脚本
  ----------------------------------------------------------
  用途：在装有 Edge / Chrome 的普通 Windows 机器上，复现 screenshots/ 下 8 屏 + 总览图。
  要求：浏览器可正常启动（本脚本使用 headless 模式，不依赖网络、不依赖外部 CDN）。

  用法（PowerShell / pwsh）：
      pwsh -ExecutionPolicy Bypass -File .\screenshot.ps1
  可选参数：
      -Browser 自动 | edge | chrome     指定浏览器（默认自动探测）
      -Width / -Height                 截图尺寸（默认 1600 x 1000）
      -FullPage                        是否整页截图（默认否，按视口）
#>
param(
  [ValidateSet('auto','edge','chrome')][string]$Browser = 'auto',
  [int]$Width = 1600,
  [int]$Height = 1000,
  [switch]$FullPage
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $root 'screenshots'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$indexPath = Join-Path $root 'index.html'
if (-not (Test-Path $indexPath)) { throw "未找到 index.html：$indexPath" }

function Find-Browser {
  param([string]$pref)
  $candidates = @()
  if ($pref -eq 'auto' -or $pref -eq 'edge') {
    $candidates += @(
      "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
      "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    )
  }
  if ($pref -eq 'auto' -or $pref -eq 'chrome') {
    $candidates += @(
      "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
      "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
      "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
  }
  foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
  $cmd = Get-Command msedge.exe, chrome.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cmd) { return $cmd.Source }
  throw "未找到 Edge/Chrome，请用 -Browser 指定或安装浏览器。"
}

$browserPath = Find-Browser $Browser
Write-Host "浏览器: $browserPath" -ForegroundColor Cyan

$pages = [ordered]@{
  '01-workbench' = 'workbench'
  '02-monitor'   = 'monitor'
  '03-agents'    = 'agents'
  '04-skills'    = 'skills'
  '05-flow'      = 'flow'
  '06-memory'    = 'memory'
  '07-quality'   = 'quality'
  '08-settings'  = 'settings'
}

$fileUrl = ([System.Uri]$indexPath).AbsoluteUri
$profileDir = Join-Path ([System.IO.Path]::GetTempPath()) ("hermes-shot-" + [guid]::NewGuid().ToString('N').Substring(0,8))

function Invoke-Shot {
  param([string]$url, [string]$outFile, [string]$size)
  $args = @(
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    '--no-first-run',
    '--no-default-browser-check',
    "--window-size=$size",
    '--virtual-time-budget=3500',
    "--user-data-dir=$profileDir",
    "--screenshot=$outFile"
  )
  if ($FullPage) { $args += '--screenshot-format=png' }
  $args += $url
  & $browserPath @args 2>$null | Out-Null
  if (-not (Test-Path $outFile)) { throw "截图失败：$outFile（请确认浏览器可在当前环境启动）" }
}

$size = "$Width,$Height"
foreach ($name in $pages.Keys) {
  $out = Join-Path $outDir "$name.png"
  Remove-Item $out -ErrorAction SilentlyContinue
  Write-Host ("[{0}] {1}" -f $name, $pages[$name]) -NoNewline
  Invoke-Shot -url "$fileUrl#$($pages[$name])" -outFile $out -size $size
  Write-Host "  ✓" -ForegroundColor Green
}

# ---------- 00-overview：8 屏缩略总览 ----------
$tiles = ($pages.Keys | ForEach-Object {
  $src = "$_.png"
  "<figure class='tile'><img src='$src' alt='$_'><figcaption><b>$_</b></figcaption></figure>"
}) -join "`n"

$overviewHtml = @"
<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
  *{box-sizing:border-box}
  body{margin:0;background:#07090B;color:#E6EDF3;font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;padding:22px 24px}
  h1{font:600 20px/1 'Bahnschrift','Segoe UI',sans-serif;letter-spacing:.14em;margin:0 0 4px}
  .sub{font:400 10px/1 'Cascadia Mono',Consolas,monospace;color:#737F8C;letter-spacing:.08em}
  .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}
  .tile{margin:0;background:#0F1419;border:1px solid #1E262F;border-radius:7px;overflow:hidden}
  .tile img{display:block;width:100%;aspect-ratio:16/10;object-fit:cover;border-bottom:1px solid #1E262F}
  figcaption{display:flex;align-items:center;gap:8px;padding:6px 8px;font:600 9px/1 'Cascadia Mono',Consolas,monospace;color:#A3AFBB;letter-spacing:.06em}
  figcaption b{color:#35CFC1;font-weight:600}
  .foot{display:flex;align-items:center;gap:16px;margin-top:14px;font:400 9.5px/1 'Cascadia Mono',Consolas,monospace;color:#4C5865}
  .dot{width:5px;height:5px;border-radius:50%;background:#35CFC1;display:inline-block;margin-right:5px}
</style></head><body>
  <h1>HERMES · MIGRATION CONTROL PLANE</h1>
  <div class="sub">UI DESIGN SPEC — 8 SCREENS · VUE2 → VUE3 WORKFLOW CONSOLE · 1600×1000</div>
  <div class="grid">$tiles</div>
  <div class="foot"><span><span class="dot"></span>LIVE MISSION · 78/287 FILES</span><span>DSH · UI-DESIGN v1.0</span><span>2026-10-18</span></div>
</body></html>
"@
$tmpOverview = Join-Path $outDir '_overview.html'
[System.IO.File]::WriteAllText($tmpOverview, $overviewHtml, (New-Object System.Text.UTF8Encoding($false)))
$overviewOut = Join-Path $outDir '00-overview.png'
Remove-Item $overviewOut -ErrorAction SilentlyContinue
Write-Host "[00-overview] thumbnails" -NoNewline
Invoke-Shot -url ([System.Uri]$tmpOverview).AbsoluteUri -outFile $overviewOut -size $size
Remove-Item $tmpOverview -ErrorAction SilentlyContinue
Write-Host "  ✓" -ForegroundColor Green

Write-Host ""
Write-Host "完成：" -ForegroundColor Cyan
Get-ChildItem $outDir -Filter *.png | Sort-Object Name | ForEach-Object {
  "{0,-20} {1,8:N0} KB" -f $_.Name, ($_.Length / 1KB)
}
