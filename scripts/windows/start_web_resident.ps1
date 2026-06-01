$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$pythonCandidates = @(
  (Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'),
  'py'
)

$logDir = Join-Path $env:LOCALAPPDATA 'KenshoAssistant\logs'
$logFile = Join-Path $logDir 'web_resident.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
  param([string]$Message)
  $line = ('{0} {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Message)
  Add-Content -LiteralPath $logFile -Value $line
}

function Get-PythonCommand {
  foreach ($candidate in $pythonCandidates) {
    if ($candidate -eq 'py') {
      return [pscustomobject]@{ File = 'py'; Args = @('-3') }
    }
    if (Test-Path -LiteralPath $candidate) {
      return [pscustomobject]@{ File = $candidate; Args = @() }
    }
  }
  throw 'Python not found.'
}

function Test-PortOpen {
  param([int]$Port)
  try {
    $client = [System.Net.Sockets.TcpClient]::new()
    $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(300)) {
      $client.Close()
      return $false
    }
    $client.EndConnect($async)
    $client.Close()
    return $true
  } catch {
    return $false
  }
}

Write-Log 'resident monitor started'

while ($true) {
  try {
    if (Test-PortOpen -Port 8787) {
      Write-Log 'port 8787 already open; skipping start'
    } else {
      $pythonCommand = Get-PythonCommand
      $proc = Start-Process -FilePath $pythonCommand.File -ArgumentList ($pythonCommand.Args + @('web_app.py')) -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden
      Write-Log ("web_app.py started pid={0}" -f $proc.Id)
      Wait-Process -Id $proc.Id
      Write-Log ("web_app.py exited pid={0}" -f $proc.Id)
    }
  } catch {
    Write-Log ("error: {0}" -f $_.Exception.Message)
  }
  Start-Sleep -Seconds 5
}
