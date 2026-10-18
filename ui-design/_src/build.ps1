$ErrorActionPreference = 'Stop'
$root = 'E:\deepSeek\ui-design'
$src = Join-Path $root '_src'

$cssFiles = @('10-base.css','20-components.css','30-overlays.css','40-pages.css','45-batch.css')
$css = ($cssFiles | ForEach-Object { Get-Content -Raw -Encoding UTF8 (Join-Path $src $_) }) -join "`n"

$htmlFiles = @('51-pages-workbench-agents.html','52-pages-skills-flow.html','53-pages-monitor-memory.html','54-pages-quality-settings.html','55-overlays.html')
$body = ($htmlFiles | ForEach-Object { Get-Content -Raw -Encoding UTF8 (Join-Path $src $_) }) -join "`n"

$head = Get-Content -Raw -Encoding UTF8 (Join-Path $src '50-head.html')
$js = Get-Content -Raw -Encoding UTF8 (Join-Path $src '60-app.js')

$doc = $head.Replace('/* CSS_PLACEHOLDER */', $css) + $body
$doc = $doc.Replace('/* JS_PLACEHOLDER */', $js)

$out = Join-Path $root 'index.html'
[System.IO.File]::WriteAllText($out, $doc, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ("built: {0}  bytes: {1}" -f $out, (Get-Item $out).Length)
