#Requires -Version 5.1
<#
.SYNOPSIS
    Install the HERMES Flow (hermes_flow) plugin on Windows.

.DESCRIPTION
    Links the current plugin directory to $env:HERMES_HOME\plugins\hermes_flow
    (junction by default, copy with -Copy). The script is idempotent: it skips
    when the target already points at this directory, and moves any other
    existing target to $HERMES_HOME\backups\hermes_flow-<timestamp> first.

    This file is ASCII-only on purpose: it must run under both Windows
    PowerShell 5.1 and PowerShell 7 even when saved as UTF-8 without BOM.

.PARAMETER HermesHome
    Hermes home directory. Defaults to $env:HERMES_HOME, or E:\hermes.

.PARAMETER Copy
    Copy the plugin tree instead of creating a junction (cross-volume,
    permission-restricted, FAT/exFAT).

.PARAMETER Enable
    Run `hermes plugins enable hermes_flow` after installation when the
    hermes command is available.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1

.EXAMPLE
    .\install.ps1 -HermesHome 'D:\hermes' -Copy -Enable
#>
[CmdletBinding()]
param(
    [string]$HermesHome = $(if ($env:HERMES_HOME) { $env:HERMES_HOME } else { 'E:\hermes' }),
    [switch]$Copy,
    [switch]$Enable
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) { Write-Host "[hermes_flow] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "[hermes_flow] $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "[hermes_flow] $Message" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 1. Source directory and plugin completeness
# ---------------------------------------------------------------------------
$Source = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Source)) { $Source = (Get-Location).Path }
$Source = (Resolve-Path -LiteralPath $Source).Path

$required = @('plugin.yaml', 'flow_core', 'tools.py', 'runtime.py', '__init__.py',
              'agents', 'skills', 'workflows')
$missing = @()
foreach ($item in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $Source $item))) { $missing += $item }
}
if ($missing.Count -gt 0) {
    throw "Not a hermes_flow plugin root. Missing: $($missing -join ', ') (dir: $Source)"
}
Write-Step "Source: $Source"

# ---------------------------------------------------------------------------
# 2. Validate Python (the plugin kernel and CLI need Python 3.9+)
# ---------------------------------------------------------------------------
$pythonCmd = $null
foreach ($candidate in @('python', 'py')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { continue }
    try {
        if ($candidate -eq 'py') {
            $verText = (& py -3 --version 2>&1 | Out-String).Trim()
        } else {
            $verText = (& python --version 2>&1 | Out-String).Trim()
        }
        if ($LASTEXITCODE -eq 0 -and $verText -match 'Python\s+3\.(\d+)') {
            $minor = [int]$Matches[1]
            if ($minor -lt 9) {
                throw "Python 3.9+ is required, found: $verText"
            }
            $pythonCmd = $candidate
            Write-Ok "Python available: $verText ($candidate)"
            break
        }
    } catch {
        Write-Warn2 "Probe $candidate failed: $($_.Exception.Message)"
    }
}
if ($null -eq $pythonCmd) {
    throw "Python 3.9+ not found. Install Python, add it to PATH, then re-run this script."
}

# ---------------------------------------------------------------------------
# 3. Target: $HERMES_HOME\plugins\hermes_flow
# ---------------------------------------------------------------------------
$HermesHome = [System.IO.Path]::GetFullPath($HermesHome)
if (-not (Test-Path -LiteralPath $HermesHome)) {
    throw "HERMES_HOME does not exist: $HermesHome. Install/initialize Hermes first, or pass -HermesHome."
}
$PluginsDir = Join-Path $HermesHome 'plugins'
if (-not (Test-Path -LiteralPath $PluginsDir)) {
    New-Item -ItemType Directory -Path $PluginsDir -Force | Out-Null
}
$Target = Join-Path $PluginsDir 'hermes_flow'
Write-Step "Target: $Target"

function Test-SameLinkTarget {
    param([string]$Path, [string]$Expected)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.LinkType) { return $false }
    $raw = @($item.Target)[0]
    if (-not $raw) { return $false }
    try {
        $resolved = (Resolve-Path -LiteralPath $raw).Path
    } catch {
        return $false
    }
    return ($resolved -eq $Expected)
}

$alreadyLinked = Test-SameLinkTarget -Path $Target -Expected $Source

if ((Test-Path -LiteralPath $Target) -and (-not $alreadyLinked)) {
    $backupRoot = Join-Path $HermesHome 'backups'
    if (-not (Test-Path -LiteralPath $backupRoot)) {
        New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = Join-Path $backupRoot "hermes_flow-$stamp"
    Write-Warn2 "Target exists and is not this source; moving it to backup: $backup"
    Move-Item -LiteralPath $Target -Destination $backup -Force
}

$mode = $null
if ($alreadyLinked) {
    Write-Ok "Already installed and linked to this source; skipping (idempotent)."
    $mode = 'junction'
} elseif ($Copy) {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
    Write-Step "Copying plugin files..."
    Copy-Item -Path (Join-Path $Source '*') -Destination $Target -Recurse -Force
    $mode = 'copy'
} else {
    $linked = $false
    try {
        New-Item -ItemType Junction -Path $Target -Target $Source -Force | Out-Null
        $linked = $true
    } catch {
        Write-Warn2 "Junction API failed ($($_.Exception.Message)); trying mklink /J."
    }
    if (-not $linked) {
        try {
            & cmd.exe /c mklink /J "$Target" "$Source" | Out-Null
            $linked = (-not $LASTEXITCODE) -and (Test-Path -LiteralPath $Target)
        } catch {
            $linked = $false
        }
    }
    if ($linked) {
        $mode = 'junction'
        Write-Ok "Junction created (source edits are live)."
    } else {
        Write-Warn2 "Junction creation failed; falling back to copy."
        New-Item -ItemType Directory -Path $Target -Force | Out-Null
        Copy-Item -Path (Join-Path $Source '*') -Destination $Target -Recurse -Force
        $mode = 'copy'
    }
}

# ---------------------------------------------------------------------------
# 4. Enable and verification hints
# ---------------------------------------------------------------------------
$dataDir = Join-Path (Join-Path $HermesHome 'plugin-data') 'hermes_flow'
Write-Host ""
Write-Ok "Install complete (mode: $mode)."
Write-Host "  Plugin root: $Target"
Write-Host "  Data dir:    $dataDir (created on first run: state.db / experience.db / batches.db / runs / staging / backups)"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1) hermes plugins enable hermes_flow"
Write-Host "  2) hermes flow status"
Write-Host "  3) hermes flow agents / hermes flow skills / hermes flow workflows"
Write-Host "  4) hermes flow demo --files 287"
Write-Host ""

$hermes = Get-Command hermes -ErrorAction SilentlyContinue
if ($Enable) {
    if ($null -eq $hermes) {
        Write-Warn2 "hermes command not found; run manually: hermes plugins enable hermes_flow"
    } else {
        Write-Step "Running: hermes plugins enable hermes_flow"
        & hermes plugins enable hermes_flow
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "Enable command returned a non-zero exit code; check its output or run it manually."
        }
    }
} elseif ($null -eq $hermes) {
    Write-Warn2 "hermes command not found in PATH; run the enable command inside the Hermes environment."
}

Write-Host "Note: if Hermes is already running, restart it or open a new session so the plugin is discovered."
exit 0
