param(
  [string]$SetupPath = "$env:USERPROFILE\Downloads\NVIDIA_582.53_extracted\setup.exe"
)

$ErrorActionPreference = "Continue"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
$logDir = Join-Path $projectRoot "driver_update_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$nvidiaLogDir = Join-Path $logDir "nvidia_58253"
New-Item -ItemType Directory -Path $nvidiaLogDir -Force | Out-Null
$runLog = Join-Path $logDir ("nvidia_install_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Write-RunLog {
  param([string]$Message)
  $line = "$(Get-Date -Format o) $Message"
  Write-Host $line
  Add-Content -Path $runLog -Value $line
}

Write-RunLog "NVIDIA install started"
Write-RunLog "Running as administrator: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"
Write-RunLog "SetupPath: $SetupPath"

if (-not (Test-Path $SetupPath)) {
  Write-RunLog "ERROR setup.exe not found"
  exit 2
}

$args = @("-s", "-n", "Display.Driver", "-log:$nvidiaLogDir", "-loglevel:6")
Write-RunLog "Arguments: $($args -join ' ')"
$proc = Start-Process -FilePath $SetupPath -ArgumentList $args -Wait -PassThru
Write-RunLog "ExitCode: $($proc.ExitCode)"

try {
  $gpu = & nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>&1
  Write-RunLog "nvidia-smi: $gpu"
} catch {
  Write-RunLog "WARNING nvidia-smi failed: $($_.Exception.Message)"
}

Write-RunLog "NVIDIA install finished"
exit $proc.ExitCode
