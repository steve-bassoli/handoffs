[CmdletBinding()]
param(
    [string]$PromptFile,
    [string]$RunDirectory,
    [string]$PreviousRun,
    [string]$RepositoryRoot = 'C:/hackathon/handoffs',
    [switch]$Check
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$python = Join-Path $RepositoryRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Commons Python runtime is unavailable' }
$savedKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$savedBudget = [Environment]::GetEnvironmentVariable('HANDOFFS_API_BUDGET_DB', 'Process')
try {
    if (-not $savedKey) {
        $configuredKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'User')
        if (-not $configuredKey) { $configuredKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Machine') }
        $env:OPENAI_API_KEY = $configuredKey
    }
    $env:HANDOFFS_API_BUDGET_DB = Join-Path $RepositoryRoot '.data/api-budget.sqlite'
    $arguments = @('-B', '-m', 'app.astra_chat')
    if ($Check) {
        $arguments += '--check'
    } else {
        if (-not $PromptFile -or -not $RunDirectory) { throw 'PromptFile and new RunDirectory are required' }
        $arguments += @('--prompt-file', $PromptFile, '--run', $RunDirectory)
        if ($PreviousRun) { $arguments += @('--previous-run', $PreviousRun) }
    }
    Push-Location -LiteralPath $RepositoryRoot
    try {
        & $python @arguments
        if ($LASTEXITCODE -ne 0) { throw "Astra relay stopped with exit code $LASTEXITCODE; inspect the run; do not retry automatically" }
    } finally { Pop-Location }
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $savedKey, 'Process')
    [Environment]::SetEnvironmentVariable('HANDOFFS_API_BUDGET_DB', $savedBudget, 'Process')
}
