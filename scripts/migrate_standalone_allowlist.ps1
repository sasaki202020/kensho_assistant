[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = 'Stop'

$sourceRoot = [System.IO.Path]::GetFullPath($Source).TrimEnd('\')
$destinationRoot = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\')

if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw 'SOURCE_NOT_FOUND'
}
if ($destinationRoot -eq $sourceRoot -or $destinationRoot.StartsWith($sourceRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'DESTINATION_INSIDE_SOURCE'
}

New-Item -ItemType Directory -Force -Path $destinationRoot | Out-Null

$allowedExisting = @(
    'docs/superpowers/specs/2026-08-08-kensho-standalone-completion-design.md',
    'docs/superpowers/plans/2026-08-08-kensho-standalone-completion.md',
    'tests/test_standalone_migration.py',
    'scripts/migrate_standalone_allowlist.ps1'
)

$existingFiles = Get-ChildItem -LiteralPath $destinationRoot -Recurse -File -Force -ErrorAction SilentlyContinue
foreach ($file in $existingFiles) {
    $relative = $file.FullName.Substring($destinationRoot.Length).TrimStart('\').Replace('\', '/')
    if ($relative -notin $allowedExisting) {
        throw "DESTINATION_NOT_EMPTY:$relative"
    }
}

$allowedDirectories = @(
    'app',
    'tests',
    'samples',
    'scripts',
    'docs',
    'extension',
    'pilot',
    'ui',
    'web',
    'config'
)

$allowedTopFiles = @(
    '__init__.py',
    '.gitattributes',
    '.gitignore',
    '.env.example',
    'AGENTS.md',
    'auto_scan.bat',
    'desktop_app.py',
    'mail_importer.py',
    'main.py',
    'MIGRATION_PROVENANCE.md',
    'README.md',
    'RELEASE_NOTES_v0.4.3.md',
    'requirements.txt',
    'run_web.py'
)

$deniedSegments = @(
    '.git',
    '.venv',
    '__pycache__',
    'browser_profile',
    'cache',
    'logs',
    'node_modules',
    'screenshots',
    'tmp',
    'traces'
)

function Test-DeniedRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $normalized = $RelativePath.Replace('\', '/')
    $segments = $normalized.Split('/')
    foreach ($segment in $segments) {
        if ($segment -in $deniedSegments) {
            return $true
        }
        if ($segment -like '.pytest*' -or $segment -like '*.pyc' -or $segment -like '*.pyo') {
            return $true
        }
    }
    if ($normalized -ieq '.env' -or $normalized -ieq 'config/profile.enc') {
        return $true
    }
    if ($normalized -match '(?i)(^|/)cookies?($|/)') {
        return $true
    }
    return $false
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $bytes = $sha.ComputeHash($stream)
            return [System.BitConverter]::ToString($bytes).Replace('-', '')
        }
        finally {
            $sha.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

$copyCandidates = New-Object System.Collections.Generic.List[string]

foreach ($directory in $allowedDirectories) {
    $directoryPath = Join-Path $sourceRoot $directory
    if (-not (Test-Path -LiteralPath $directoryPath -PathType Container)) {
        continue
    }
    foreach ($file in Get-ChildItem -LiteralPath $directoryPath -Recurse -File -Force) {
        $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\').Replace('\', '/')
        if (-not (Test-DeniedRelativePath -RelativePath $relative)) {
            [void]$copyCandidates.Add($relative)
        }
    }
}

foreach ($fileName in $allowedTopFiles) {
    $sourcePath = Join-Path $sourceRoot $fileName
    if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
        [void]$copyCandidates.Add($fileName)
    }
}

$safePilotManifest = 'data/pilot/manifests/5site-pilot-v1.json'
if (Test-Path -LiteralPath (Join-Path $sourceRoot $safePilotManifest) -PathType Leaf) {
    [void]$copyCandidates.Add($safePilotManifest)
}

$inventoryRows = New-Object System.Collections.Generic.List[object]
foreach ($relative in ($copyCandidates | Sort-Object -Unique)) {
    if (Test-DeniedRelativePath -RelativePath $relative) {
        throw "DENIED_PATH_SELECTED:$relative"
    }

    $sourcePath = Join-Path $sourceRoot ($relative.Replace('/', '\'))
    $destinationPath = Join-Path $destinationRoot ($relative.Replace('/', '\'))
    $destinationParent = Split-Path -Parent $destinationPath
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null

    $sourceHash = Get-Sha256 -Path $sourcePath
    if (Test-Path -LiteralPath $destinationPath -PathType Leaf) {
        $destinationHash = Get-Sha256 -Path $destinationPath
        if ($destinationHash -ne $sourceHash) {
            throw "DESTINATION_CONFLICT:$relative"
        }
    }
    else {
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
    }

    [void]$inventoryRows.Add([ordered]@{
        relative_path = $relative
        sha256 = $sourceHash
    })
}

$inventory = [ordered]@{
    schema_version = 1
    file_count = $inventoryRows.Count
    files = $inventoryRows.ToArray()
}
$inventoryPath = Join-Path $destinationRoot 'migration_inventory.json'
$inventoryJson = $inventory | ConvertTo-Json -Depth 4
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($inventoryPath, $inventoryJson + [System.Environment]::NewLine, $utf8NoBom)

[ordered]@{
    status = 'STANDALONE_COPY_VERIFIED'
    file_count = $inventoryRows.Count
    inventory = 'migration_inventory.json'
} | ConvertTo-Json -Compress
