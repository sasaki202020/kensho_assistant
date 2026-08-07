[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$packageParent = Split-Path -Parent $repoRoot
$pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
$python = Get-ChildItem -LiteralPath $pythonRoot -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1

if (-not $python) {
    throw "Python runtime was not found."
}

Write-Output "This helper prepares a local preview only. It never publishes a post."
$postText = Read-Host "Draft text"
if ([string]::IsNullOrWhiteSpace($postText)) {
    throw "Draft text is required."
}

Push-Location $packageParent
try {
    & $python.FullName -m kensho_assistant.scripts.x_post --dry-run --text $postText
}
finally {
    Pop-Location
}
