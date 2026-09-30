param(
    [Parameter(Mandatory=$true)][string]$CandidateId,
    [string]$TargetUrl = "https://www.epinard.jp/presentquiz/",
    [switch]$VerifyOnly,
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
# The Python runner starts Chrome with --disable-extensions-except and
# --load-extension, both pointing at this fixed build\extension path.
$BuildPath = Join-Path $ProjectRoot "build\extension"
$DefaultRuntimeProfilesRoot = Join-Path $env:USERPROFILE "AppData\Local\kensho_assistant\chrome-runs"
$RuntimeProfilesRoot = if ($env:KENSHO_CHROME_RUNS_PATH) {
    $env:KENSHO_CHROME_RUNS_PATH
} else {
    $DefaultRuntimeProfilesRoot
}

$Manifest = Get-Content (Join-Path $BuildPath "manifest.json") -Raw | ConvertFrom-Json
if (($Manifest.host_permissions -join ',') -ne 'https://*/*,http://127.0.0.1/*,http://localhost/*' -or
    $Manifest.version_name -ne 'dedicated-runtime-origin' -or
    $null -ne $Manifest.content_scripts -or $null -ne $Manifest.optional_host_permissions) {
    throw "BLOCKED_INVALID_RUNTIME_ORIGIN_BUILD"
}

$ExistingDedicated = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "chrome.exe" -and $_.CommandLine -like "*--user-data-dir=$RuntimeProfilesRoot*"
}
if ($ExistingDedicated) {
    throw "dedicated Chrome is already running; close only that window before restarting"
}

$RunnerArgs = @(
    (Join-Path $PSScriptRoot "run_dedicated_chrome.py"),
    "--project-root", $ProjectRoot,
    "--runtime-profiles-root", $RuntimeProfilesRoot,
    "--url", $TargetUrl,
    "--candidate-id", $CandidateId,
    "--verify-only"
)
if ($Headless) { $RunnerArgs += "--headless" }

py -3.13 @RunnerArgs
exit $LASTEXITCODE
