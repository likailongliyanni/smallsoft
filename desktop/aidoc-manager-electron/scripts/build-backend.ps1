$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$distRoot = Join-Path $projectRoot 'build\backend-dist'
$workRoot = Join-Path $projectRoot 'build\pyinstaller-work'
$specRoot = Join-Path $projectRoot 'build\pyinstaller-spec'

foreach ($target in @($distRoot, $workRoot, $specRoot)) {
    if (Test-Path -LiteralPath $target) {
        $resolved = (Resolve-Path -LiteralPath $target).Path
        if (-not $resolved.StartsWith($projectRoot)) {
            throw "Refusing to remove path outside project: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

New-Item -ItemType Directory -Path $distRoot, $workRoot, $specRoot -Force | Out-Null

Push-Location $projectRoot
try {
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --console `
        --name aidoc-backend `
        --distpath $distRoot `
        --workpath $workRoot `
        --specpath $specRoot `
        --hidden-import fitz `
        --hidden-import PIL.Image `
        --hidden-import PIL.ImageDraw `
        --hidden-import PIL.ImageFont `
        --hidden-import PIL.ImageOps `
        --hidden-import pypdf `
        --hidden-import openpyxl `
        backend.py
} finally {
    Pop-Location
}

$exe = Join-Path $distRoot 'aidoc-backend\aidoc-backend.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    throw 'Backend executable was not produced.'
}
Write-Host "Backend built: $exe"
