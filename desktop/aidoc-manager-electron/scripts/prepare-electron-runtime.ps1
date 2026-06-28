$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $projectRoot 'build\electron-runtime'
$electronExe = (& node -e "process.stdout.write(require('electron'))").Trim()
if (-not (Test-Path -LiteralPath $electronExe)) {
    throw "Electron executable not found: $electronExe"
}
$source = Split-Path $electronExe

if (Test-Path -LiteralPath $target) {
    $resolved = (Resolve-Path -LiteralPath $target).Path
    if (-not $resolved.StartsWith($projectRoot)) {
        throw "Refusing to remove path outside project: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
Write-Host "Electron runtime prepared: $target"
