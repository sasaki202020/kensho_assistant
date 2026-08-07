[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$healthUrl = "http://127.0.0.1:8787/health"
$sessionPath = Join-Path $repoRoot "data\assisted_session\session.json"
$playwrightProfile = Join-Path $repoRoot "browser_profile\chrome_user_data"

function Get-OwnedProcess {
    @(Get-CimInstance Win32_Process | Where-Object {
        $command = [string]$_.CommandLine
        $command -like "*kensho_assistant.run_web*" -and
        $command -like "*--managed-by*" -and
        $command -like "*kensho-remote-ops*"
    })
}

function Get-TailscaleCheck {
    $tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
    if (-not $tailscale) {
        return $false
    }
    try {
        & $tailscale.Source status --json *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Get-TailscaleServeCheck {
    $tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
    if (-not $tailscale) {
        return $false
    }
    try {
        & $tailscale.Source serve status *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$checks = [ordered]@{}
$listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$checks["localhost_bind"] = [bool]$listener

$health = $null
try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
    $checks["submitted_count_auto"] = ($health.submitted_count_auto -eq 0)
}
catch {
    $checks["submitted_count_auto"] = $false
}

$checks["owned_web_process"] = (@(Get-OwnedProcess).Count -eq 1)
$checks["tailscale_status"] = Get-TailscaleCheck
$checks["tailscale_serve"] = Get-TailscaleServeCheck
$checks["chrome_remote_desktop"] = [bool](Get-Service -Name "chromoting" -ErrorAction SilentlyContinue)
$checks["playwright_profile"] = Test-Path -LiteralPath $playwrightProfile

if (Test-Path -LiteralPath $sessionPath) {
    try {
        Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json | Out-Null
        $checks["session_state"] = $true
    }
    catch {
        $checks["session_state"] = $false
    }
}
else {
    # No active assisted session is a valid idle state.
    $checks["session_state"] = $true
}

$blocked = -not ($checks["localhost_bind"] -and $checks["submitted_count_auto"] -and $checks["owned_web_process"] -and $checks["session_state"])
$degraded = -not ($checks["tailscale_status"] -and $checks["tailscale_serve"] -and $checks["chrome_remote_desktop"] -and $checks["playwright_profile"])
$result = if ($blocked) { "BLOCKED" } elseif ($degraded) { "DEGRADED" } else { "READY" }

[pscustomobject]@{
    result = $result
    checks = $checks
} | ConvertTo-Json -Depth 3

if ($result -eq "BLOCKED") {
    exit 1
}
