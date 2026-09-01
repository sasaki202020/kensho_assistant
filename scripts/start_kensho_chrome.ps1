param(
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
if ($Manifest.host_permissions -contains "<all_urls>" -or
    $Manifest.host_permissions -contains "https://*/*" -or
    $Manifest.host_permissions -contains "http://*/*") {
    throw "BLOCKED_EXCESSIVE_HOST_PERMISSION"
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
    "--verify-only"
)
if ($Headless) { $RunnerArgs += "--headless" }

py -3.12 @RunnerArgs
exit $LASTEXITCODE
