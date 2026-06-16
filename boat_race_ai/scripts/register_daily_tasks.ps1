param(
    [string]$PythonExe = "py -3.13",
    [string]$MorningTime = "08:00",
    [string]$OddsTime = "18:00",
    [string]$NightTime = "21:30",
    [string]$StatusTime = "22:30",
    [int]$BankrollYen = 10000
)

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$MorningScript = Join-Path $PSScriptRoot "run_daily_morning.bat"
$OddsScript = Join-Path $PSScriptRoot "run_daily_odds.bat"
$NightScript = Join-Path $PSScriptRoot "run_daily_night.bat"
$StatusScript = Join-Path $PSScriptRoot "run_daily_status.bat"

Write-Host "No task was registered automatically."
Write-Host "Review and run these commands manually if you want Windows Task Scheduler entries:"
Write-Host ""
Write-Host "schtasks /Create /TN BoatRaceAI-Morning /SC DAILY /ST $MorningTime /TR `"$MorningScript`" /F"
Write-Host "schtasks /Create /TN BoatRaceAI-Odds /SC DAILY /ST $OddsTime /TR `"$OddsScript`" /F"
Write-Host "schtasks /Create /TN BoatRaceAI-Night /SC DAILY /ST $NightTime /TR `"`"`"$NightScript`"`" --bankroll-yen $BankrollYen`" /F"
Write-Host "schtasks /Create /TN BoatRaceAI-Status /SC DAILY /ST $StatusTime /TR `"$StatusScript`" /F"
Write-Host ""
Write-Host "ProjectRoot: $ProjectRoot"
Write-Host "PYTHON_EXE can be set before running the .bat files. Suggested: $PythonExe"
Write-Host "Night bankroll guard defaults to BANKROLL_YEN=$BankrollYen."
