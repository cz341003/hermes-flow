param(
  [string]$Version = "0.2.0",
  [string]$RepoRoot = "",
  [string]$Notes = "",
  [switch]$Push
)
$ErrorActionPreference = "Stop"
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path }
$plugin = Join-Path $RepoRoot "plugin\hermes_flow"
if (-not $Notes) { $Notes = Join-Path $RepoRoot "docs\RELEASE_NOTES_v$Version.md" }
if (-not (Test-Path $Notes)) { throw "release notes not found: $Notes" }
$zip = Join-Path $plugin "dist\hermes_flow-$Version.zip"
$sha = "$zip.sha256"
if (-not (Test-Path $zip)) { throw "package not found: $zip (run scripts/package.py first)" }

$status = git -C $RepoRoot status --porcelain
if ($status) { throw "working tree is dirty; commit before tagging:`n$status" }
$tag = "v$Version"
if (git -C $RepoRoot rev-parse -q --verify "refs/tags/$tag") { throw "tag already exists: $tag" }

git -C $RepoRoot tag -a $tag -F $Notes
$out = Join-Path $RepoRoot "releases\$Version"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item $zip $out -Force
if (Test-Path $sha) { Copy-Item $sha $out -Force }
Copy-Item $Notes (Join-Path $out "RELEASE_NOTES.md") -Force

Write-Output "tagged $tag"
Write-Output "release assets: $out"
$remote = git -C $RepoRoot remote
if ($Push) {
  if (-not $remote) { throw "no git remote configured; add origin first" }
  git -C $RepoRoot push -u origin main
  git -C $RepoRoot push origin $tag
  if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh release create $tag $zip $sha --title "HERMES Flow $tag" --notes-file $Notes
  } else {
    Write-Output "gh not found; tag pushed, create GitHub Release manually."
  }
}
