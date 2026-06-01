$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$startupDir = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupDir 'KenshoAssistantWebResident.lnk'
$targetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$scriptPath = Join-Path $repoRoot 'scripts\windows\start_web_resident.ps1'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.Arguments = ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $scriptPath)
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = 'Kensho Assistant local web UI resident launcher'
$shortcut.Save()

Write-Host "Installed startup shortcut: $shortcutPath"
Write-Host "It will start the local web UI when you sign in."
