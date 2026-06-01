param(
  [string]$NvidiaInstaller = "$env:USERPROFILE\Downloads\582.53-desktop-win10-win11-64bit-international-dch-whql.exe"
)

$ErrorActionPreference = "Continue"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
$logDir = Join-Path $projectRoot "driver_update_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "driver_update_$timestamp.log"

function Write-Log {
  param([string]$Message)
  $line = "$(Get-Date -Format o) $Message"
  Write-Host $line
  Add-Content -Path $logPath -Value $line
}

Write-Log "Driver update started"
Write-Log "Running as administrator: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"

Write-Log "Restore point creation skipped to avoid blocking unattended driver install"

try {
  Write-Log "Searching Windows Update driver updates..."
  $session = New-Object -ComObject Microsoft.Update.Session
  $searcher = $session.CreateUpdateSearcher()
  $result = $searcher.Search("IsInstalled=0 and Type='Driver'")
  Write-Log "Windows Update driver updates found: $($result.Updates.Count)"

  if ($result.Updates.Count -gt 0) {
    $updates = New-Object -ComObject Microsoft.Update.UpdateColl
    for ($i = 0; $i -lt $result.Updates.Count; $i++) {
      $u = $result.Updates.Item($i)
      Write-Log "WU driver [$i]: $($u.Title)"
      if (-not $u.EulaAccepted) { $u.AcceptEula() }
      [void]$updates.Add($u)
    }

    $downloader = $session.CreateUpdateDownloader()
    $downloader.Updates = $updates
    $downloadResult = $downloader.Download()
    Write-Log "Windows Update download result: $($downloadResult.ResultCode)"

    $installer = $session.CreateUpdateInstaller()
    $installer.Updates = $updates
    $installResult = $installer.Install()
    Write-Log "Windows Update install result: $($installResult.ResultCode)"
    Write-Log "Windows Update reboot required: $($installResult.RebootRequired)"

    for ($i = 0; $i -lt $updates.Count; $i++) {
      $ur = $installResult.GetUpdateResult($i)
      Write-Log "WU result [$i]: result=$($ur.ResultCode) hresult=$('0x{0:X8}' -f ($ur.HResult -band 0xffffffff)) title=$($updates.Item($i).Title)"
    }
  }
} catch {
  Write-Log "WARNING Windows Update driver installation failed: $($_.Exception.Message)"
}

try {
  if (Test-Path $NvidiaInstaller) {
    Write-Log "Running NVIDIA installer: $NvidiaInstaller"
    $proc = Start-Process -FilePath $NvidiaInstaller -ArgumentList "-s", "-noreboot" -Wait -PassThru
    Write-Log "NVIDIA installer exit code: $($proc.ExitCode)"
  } else {
    Write-Log "WARNING NVIDIA installer not found: $NvidiaInstaller"
  }
} catch {
  Write-Log "WARNING NVIDIA driver installation failed: $($_.Exception.Message)"
}

Write-Log "Post-update device problems:"
$problemDevices = Get-PnpDevice -PresentOnly | Where-Object { $_.Status -ne "OK" } | Select-Object Status, Class, FriendlyName, InstanceId | Out-String
Add-Content -Path $logPath -Value $problemDevices
Write-Host $problemDevices

Write-Log "Driver update finished"
Write-Log "Log written to: $logPath"
