$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "== $Title =="
}

function Invoke-WslText {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & wsl @Args 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = (($output -join "`n") -replace "`0", "")
    }
}

function Get-UbuntuDistroName {
    $result = Invoke-WslText -Args @('--list', '--quiet')
    if ($result.ExitCode -ne 0) {
        return $null
    }

    foreach ($line in ($result.Output -split "`r?`n")) {
        $name = $line.Trim()
        if ($name -like 'Ubuntu*') {
            return $name
        }
    }

    return $null
}

function Show-FinalSteps {
    param(
        [string]$DistroName
    )

    Write-Section '今できること'
    Write-Host "Hermes の導入状態を確認しました。"
    if ($DistroName) {
        Write-Host "WSL ディストリ: $DistroName"
    }

    Write-Section 'PowerShell 環境変数例'
    Write-Host '$env:X_RESEARCH_HERMES_COMMAND="wsl -d Ubuntu -- /home/goo10/.local/bin/hermes chat -q"'
    Write-Host '$env:X_RESEARCH_HERMES_TIMEOUT_SEC="120"'

    Write-Section '次に人間がやること'
    Write-Host '1. WSL2 で hermes model を実行してモデルを選ぶ'
    Write-Host '2. WSL2 で hermes auth add xai-oauth を実行して OAuth を通す'
    Write-Host '3. WSL2 で hermes tools を開き x_search を ON にする'
    Write-Host '4. PowerShell で scripts/test_hermes_provider.ps1 を実行する'
}

Write-Section 'WSL 状態確認'
$wslCommand = Get-Command wsl -ErrorAction SilentlyContinue
if (-not $wslCommand) {
    Write-Host 'wsl コマンドが見つかりません。管理者 PowerShell で次を実行してください。'
    Write-Host 'dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart'
    Write-Host 'dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart'
    Write-Host 'wsl --install -d Ubuntu'
    exit 1
}

$statusResult = Invoke-WslText -Args @('--status')
if ($statusResult.ExitCode -ne 0) {
    Write-Host 'WSL は見つかりましたが、状態確認に失敗しました。'
    if ($statusResult.Output) {
        Write-Host $statusResult.Output
    }
    Write-Host '管理者 PowerShell で次を試してください。'
    Write-Host 'wsl --install -d Ubuntu'
    exit 1
}

Write-Section 'Ubuntu ディストリ確認'
$distroName = Get-UbuntuDistroName
if (-not $distroName) {
    Write-Host 'Ubuntu 系ディストリが見つかりません。'
    Write-Host 'インストール案内: wsl --install -d Ubuntu'
    Write-Host '既存の WSL 一覧は wsl -l -v で確認できます。'
    exit 1
}
Write-Host "検出: $distroName"

Write-Section 'WSL 内ツール確認'
$toolCheckScript = @(
    'for c in bash curl git; do'
    '  command -v "$c" >/dev/null 2>&1 || { echo "missing:$c"; exit 1; }'
    'done'
    'echo "tools_ok"'
) -join "`n"
$toolCheck = Invoke-WslText -Args @('-d', $distroName, '--', 'bash', '-lc', $toolCheckScript)
if ($toolCheck.ExitCode -ne 0) {
    Write-Host 'WSL 内で curl / git / bash が足りません。'
    Write-Host 'WSL( Ubuntu )で次を実行してください。'
    Write-Host 'sudo apt update && sudo apt install -y curl git bash'
    if ($toolCheck.Output) {
        Write-Host $toolCheck.Output
    }
    exit 1
}
Write-Host $toolCheck.Output

Write-Section 'Hermes 確認'
$hermesCheck = Invoke-WslText -Args @('-d', $distroName, '--', 'bash', '-lc', 'export PATH="$HOME/.local/bin:$PATH"; command -v hermes >/dev/null 2>&1 && hermes --version || exit 1')
if ($hermesCheck.ExitCode -ne 0) {
    Write-Host 'Hermes が見つかりません。uv tool で hermes-agent をインストールします。'
    $install = Invoke-WslText -Args @('-d', $distroName, '--', 'bash', '-lc', 'export PATH="$HOME/.local/bin:$PATH"; if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi; uv tool install hermes-agent')
    if ($install.Output) {
        Write-Host $install.Output
    }
    if ($install.ExitCode -ne 0) {
        Write-Host 'Hermes のインストールは完了しませんでした。'
        Write-Host '必要なら WSL 内で手動実行してください。'
        Write-Host 'curl -LsSf https://astral.sh/uv/install.sh | sh'
        Write-Host 'export PATH="$HOME/.local/bin:$PATH"'
        Write-Host 'uv tool install hermes-agent'
        Show-FinalSteps -DistroName $distroName
        exit 1
    }
    $postInstallCheckScript = @(
        'source ~/.bashrc >/dev/null 2>&1 || true'
        'export PATH="$HOME/.local/bin:$PATH"'
        'command -v hermes >/dev/null 2>&1 && hermes --version || exit 1'
    ) -join "`n"
    $hermesCheck = Invoke-WslText -Args @('-d', $distroName, '--', 'bash', '-lc', $postInstallCheckScript)
}

if ($hermesCheck.ExitCode -ne 0) {
    Write-Host 'Hermes の確認に失敗しました。'
    if ($hermesCheck.Output) {
        Write-Host $hermesCheck.Output
    }
    Write-Host 'WSL 内で手動確認してください。'
    Show-FinalSteps -DistroName $distroName
    exit 1
}

Write-Host $hermesCheck.Output
Show-FinalSteps -DistroName $distroName
