[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $env:LOCALAPPDATA "kensho_assistant\remote_ops"
$pidFile = Join-Path $runtimeDir "web_app.pid"

function Get-OwnedProcess {
    @(Get-CimInstance Win32_Process | Where-Object {
        $command = [string]$_.CommandLine
        $command -like "*kensho_assistant.run_web*" -and
        $command -like "*--managed-by*" -and
        $command -like "*kensho-remote-ops*"
    })
}

$owned = @(Get-OwnedProcess)
foreach ($process in $owned) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
}

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
if ($owned.Count -eq 0) {
    Write-Output "No owned kensho_assistant web process was running."
}
else {
    Write-Output "Stopped $($owned.Count) owned kensho_assistant web process(es)."
}
