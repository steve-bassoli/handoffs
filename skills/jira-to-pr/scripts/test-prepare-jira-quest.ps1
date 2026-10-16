[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'prepare-jira-quest.ps1'
$root = Join-Path ([System.IO.Path]::GetTempPath()) ('handoffs-jira-quest-test-' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path $root 'source'
$launch = Join-Path $root 'launch'
$checks = 0

function Assert([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
    $script:checks++
}

try {
    $null = New-Item -ItemType Directory -Path $source -Force
    $null = & git -C $source init --quiet
    $null = & git -C $source config user.name 'JIRA Quest Test'
    $null = & git -C $source config user.email 'jira-quest@example.invalid'
    [System.IO.File]::WriteAllText((Join-Path $source 'README.md'), "fixture`n", (New-Object System.Text.UTF8Encoding($false)))
    $null = & git -C $source add -- README.md
    $null = & git -C $source commit --quiet -m fixture
    $base = (& git -C $source rev-parse HEAD).Trim()
    $quest = [ordered]@{
        schemaVersion = 1
        taskId = 'jira-fixture'
        handoffRevision = '1' * 40
        issueKey = 'CPC-123'
        issueFingerprint = 'a' * 64
        sourceRepository = $source
        baseRevision = $base
        acceptanceCriteria = @('The fixture works.')
        constraints = @('Do not push.')
    }
    $prepared = & $script -QuestJson ($quest | ConvertTo-Json -Depth 5 -Compress) -DestinationRoot $launch | ConvertFrom-Json
    Assert ($prepared.modelPolicy.selection -eq 'strongest-available') 'executor must select the strongest available model'
    Assert ($prepared.modelPolicy.reasoningEffort -eq 'high' -and $prepared.modelPolicy.agents -eq 1) 'executor must use one HIGH agent'
    Assert ((& git -C $prepared.repositoryRoot rev-parse HEAD).Trim() -eq $base) 'checkout must match the pinned base revision'
    Assert ((Get-Content -Raw $prepared.questFile | ConvertFrom-Json).acceptanceCriteria[0] -eq 'The fixture works.') 'verbatim AC must survive preparation'
    Assert (Test-Path -LiteralPath $prepared.iterativeImplementationSkillFile -PathType Leaf) 'executor package must contain iterative-implementation instructions'
    Assert ((Split-Path -Parent $prepared.planFile) -eq (Split-Path -Parent $prepared.statusFile)) 'plan artifacts must share a retained artifact directory'
    Assert (-not $prepared.planFile.StartsWith($prepared.repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) 'plan artifacts must stay outside the source checkout'
    Assert ($prepared.prompt -match [regex]::Escape($prepared.planFile) -and $prepared.prompt -match [regex]::Escape($prepared.statusFile)) 'prompt must supply exact artifact paths'
    Assert ($prepared.prompt -match 'scope ceiling' -and $prepared.prompt -match 'remove anything not required' -and $prepared.prompt -match 'never commit the plan artifacts') 'prompt must enforce minimal AC-bound implementation'
    $iterativeContract = Get-Content -Raw -LiteralPath $prepared.iterativeImplementationSkillFile
    Assert ($iterativeContract -match 'complexity: easy' -and $iterativeContract -match 'complexity:\s*medium') 'executor contract must permit only easy and medium plan items'
    Assert ($iterativeContract -match 'bounty proposal is not a task' -and $iterativeContract -match 'human explicitly approves') 'high-complexity work must remain an unpublished bounty proposal'
    Assert ($prepared.prompt -match 'Do not push' -and $prepared.prompt -match 'calling agent handles branch publication' -and $prepared.cleanupAfter -eq 'parent-verifies-plan-and-pr-confirmed-remote') 'prompt must separate implementation from automatic publication and retain evidence through parent verification'

    $directQuest = [ordered]@{
        schemaVersion = 2
        taskId = 'jira-cpc-456'
        issueKey = 'CPC-456'
        issueFingerprint = 'b' * 64
        summary = 'Direct JIRA launch'
        requirements = @('Implement the ticket requirement exactly as written.')
        sourceRepository = $source
        baseRevision = $base
        acceptanceCriteria = @()
    }
    $directLaunch = Join-Path $root 'direct-launch'
    $direct = & $script -QuestJson ($directQuest | ConvertTo-Json -Depth 5 -Compress) -DestinationRoot $directLaunch | ConvertFrom-Json
    $savedDirect = Get-Content -Raw $direct.questFile | ConvertFrom-Json
    Assert ($savedDirect.schemaVersion -eq 2 -and $savedDirect.requirements[0] -eq $directQuest.requirements[0]) 'direct JIRA launch must preserve verbatim requirements'
    Assert ($savedDirect.acceptanceCriteria.Count -eq 0 -and $direct.issueKey -eq 'CPC-456') 'direct JIRA launch must allow a clearly marked missing acceptance-criteria set'

    $quest.baseRevision = 'abc123'
    $failed = $false
    try { $null = & $script -QuestJson ($quest | ConvertTo-Json -Depth 5 -Compress) -DestinationRoot (Join-Path $root 'invalid') } catch { $failed = $true }
    Assert $failed 'a short base revision must fail before cloning'

    Write-Output "PASS: $checks JIRA quest preparation assertions."
} finally {
    if (Test-Path -LiteralPath $root) {
        $resolved = (Resolve-Path -LiteralPath $root).Path
        $temp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        if (-not $resolved.StartsWith($temp, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Refusing to remove a test directory outside the operating-system temp root.'
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
