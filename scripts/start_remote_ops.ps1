[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packageParent = Split-Path -Parent $repoRoot
$runtimeDir = Join-Path $env:LOCALAPPDATA "kensho_assistant\remote_ops"
$pidFile = Join-Path $runtimeDir "web_app.pid"
$stdoutPath = Join-Path $runtimeDir "web_app.stdout.log"
$stderrPath = Join-Path $runtimeDir "web_app.stderr.log"
$healthUrl = "http://127.0.0.1:8787/health"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

function Get-OwnedProcess {
    @(Get-CimInstance Win32_Process | Where-Object {
        $command = [string]$_.CommandLine
        $command -like "*kensho_assistant.run_web*" -and
        $command -like "*--managed-by*" -and
        $command -like "*kensho-remote-ops*"
    })
}

function Get-PythonExecutable {
    $localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path -LiteralPath $localPythonRoot) {
        $candidate = Get-ChildItem -LiteralPath $localPythonRoot -Filter python.exe -File -Recurse |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*WindowsApps*") {
        return $command.Source
    }

    throw "Python runtime was not found. Install Python 3 before starting kensho_assistant."
}

function Get-Health {
    Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
}

$owned = @(Get-OwnedProcess)
if ($owned.Count -gt 1) {
    throw "More than one owned kensho_assistant web process was found. Stop it before starting again."
}
if ($owned.Count -eq 1) {
    $health = Get-Health
    if ($health.status -ne "ok" -or $health.submitted_count_auto -ne 0) {
        throw "The existing owned process did not pass the local safety health check."
    }
    Set-Content -LiteralPath $pidFile -Value ([string]$owned[0].ProcessId) -Encoding ascii
    Write-Output "kensho_assistant is already running on 127.0.0.1:8787."
    exit 0
}

$listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    throw "127.0.0.1:8787 is already in use by a process that is not owned by kensho_assistant."
}

$python = Get-PythonExecutable
$startProcessArguments = @{
    FilePath = $python
    ArgumentList = @("-m", "kensho_assistant.run_web", "--managed-by", "kensho-remote-ops")
    WorkingDirectory = $packageParent
    RedirectStandardOutput = $stdoutPath
    RedirectStandardError = $stderrPath
    WindowStyle = "Hidden"
    PassThru = $true
}
$process = Start-Process @startProcessArguments
Set-Content -LiteralPath $pidFile -Value ([string]$process.Id) -Encoding ascii

$ready = $false
for ($attempt = 1; $attempt -le 25; $attempt += 1) {
    Start-Sleep -Seconds 1
    try {
        $health = Get-Health
        if ($health.status -eq "ok" -and $health.app -eq "kensho_assistant" -and $health.submitted_count_auto -eq 0) {
            $ready = $true
            break
        }
    }
    catch {
        # The local process is still starting. Do not open a browser or retry externally.
    }
}

if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    throw "kensho_assistant did not become healthy on 127.0.0.1:8787."
}

Write-Output "kensho_assistant is ready on 127.0.0.1:8787."
