$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $ProjectRoot

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "== $Title =="
}

function Get-Advice([string]$Reason) {
    switch ($Reason) {
        'wsl_not_found' { return 'WSL2 を有効化して Ubuntu を入れてください。setup_hermes_wsl.ps1 を先に実行してください。' }
        'hermes_not_found' { return 'scripts/setup_hermes_wsl.ps1 を実行して Hermes を入れてください。' }
        'command_not_found' { return 'Hermes 起動コマンドを確認してください。X_RESEARCH_HERMES_COMMAND か KENSHO_HERMES_COMMAND を見直してください。' }
        'xai_auth_missing' { return 'WSL で hermes model、hermes auth add xai-oauth、hermes tools を順番に実行してください。' }
        'x_search_disabled' { return 'WSL で hermes tools を開き、x_search を有効化してください。' }
        'timeout' { return 'X_RESEARCH_HERMES_TIMEOUT_SEC を 300 にして再実行してください。' }
        'x_search_timeout' { return 'X Search が時間切れです。X_RESEARCH_HERMES_TIMEOUT_SEC を 300 以上にして再実行してください。' }
        'invalid_json' { return 'Hermes の返答が JSON ではありません。プロンプト改善が必要です。' }
        'empty_result' { return '検索結果が空です。クエリを変えるか、Hermes 側の x_search 設定を見直してください。' }
        default { return '診断 JSON を確認し、Hermes / WSL / x_search の状態を見直してください。' }
    }
}

function Find-FirstLine([string[]]$Lines, [string]$Prefix) {
    foreach ($line in $Lines) {
        if ($line -like "$Prefix*") {
            return $line
        }
    }
    return $null
}

$env:X_RESEARCH_HERMES_COMMAND = 'wsl -d Ubuntu -- /home/goo10/.local/bin/hermes chat -q'
$env:X_RESEARCH_HERMES_TIMEOUT_SEC = '300'

Write-Section 'Hermes 診断'
py -3 scripts\check_hermes_x_search.py
$checkPath = Join-Path $ProjectRoot 'kensho_assistant\data\research\x_harness\diagnostics\hermes_x_search_check.json'
if (-not (Test-Path $checkPath)) {
    Write-Host '診断 JSON が見つかりません。'
    exit 1
}

$report = Get-Content -Path $checkPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.status -ne 'success') {
    Write-Host "status: failed"
    Write-Host "failed_stage: check"
    Write-Host "reason: $($report.reason)"
    Write-Host "output_file: $checkPath"
    Write-Host ("next_action: " + (Get-Advice -Reason $report.reason))
    exit 1
}

Write-Section 'X Research Harness 実行'
$harnessLines = & py -3 scripts\run_x_research_harness.py --query 'Hermes Agent' --mode quick --provider hermes 2>&1
$exitCode = $LASTEXITCODE
$outputDirLine = Find-FirstLine -Lines $harnessLines -Prefix 'output_dir: '
if (-not $outputDirLine) {
    Write-Host 'output_dir が取得できませんでした。'
    if ($harnessLines) {
        $harnessLines | ForEach-Object { Write-Host $_ }
    }
    exit 1
}

$outputDir = $outputDirLine.Substring(12).Trim()
$runReport = Join-Path $outputDir 'run_report.json'
$claimAnalysis = Join-Path $outputDir 'claim_analysis.json'
$noteMaterial = Join-Path $outputDir 'note_material.md'

if ($exitCode -ne 0) {
    $reason = 'unknown_error'
    if (Test-Path $runReport) {
        try {
            $runJson = Get-Content -Path $runReport -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($null -ne $runJson.hermes_error_type -and "$($runJson.hermes_error_type)".Trim()) {
                $reason = [string]$runJson.hermes_error_type
            } elseif ($null -ne $runJson.reason -and "$($runJson.reason)".Trim()) {
                $reason = [string]$runJson.reason
            } else {
                $reason = 'unknown_error'
            }
        } catch {
            $reason = 'unknown_error'
        }
    }
    Write-Host 'status: failed'
    Write-Host 'failed_stage: provider_hermes'
    Write-Host "provider: hermes"
    Write-Host "output_dir: $outputDir"
    Write-Host "run_report: $runReport"
    Write-Host "reason: $reason"
    Write-Host ("next_action: " + (Get-Advice -Reason $reason))
    exit 1
}

Write-Host 'status: success'
Write-Host 'provider: hermes'
Write-Host "output_dir: $outputDir"
Write-Host "note_material.md: $noteMaterial"
Write-Host "claim_analysis.json: $claimAnalysis"
Write-Host "run_report.json: $runReport"
