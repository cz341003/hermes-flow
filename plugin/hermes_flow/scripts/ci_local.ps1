$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tmp = Join-Path $root '.tmp'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$env:FLOW_TEST_TMP = $tmp
$env:PYTHONIOENCODING = 'utf-8'
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
Push-Location $root
try {
  & $python -m compileall -q .
  & $python scripts\dashboard_smoke.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & $python -m unittest discover -s tests -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & $python -m unittest discover -s tests\legacy -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & $python tests\smoke_core.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Output 'HERMES Flow local CI passed.'
  exit 0
} finally {
  Pop-Location
}
