[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$QuestJson,
    [string]$DestinationRoot,
    [string]$IterativeImplementationSkillPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-Git([string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& git @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "Git failed: git $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return @($output | ForEach-Object { $_.ToString() })
}

$quest = $QuestJson | ConvertFrom-Json
foreach ($field in @('schemaVersion', 'taskId', 'issueKey', 'issueFingerprint',
        'sourceRepository', 'baseRevision')) {
    if ($null -eq $quest.PSObject.Properties[$field]) { throw "Missing quest field: $field" }
}
if ($quest.schemaVersion -notin @(1, 2)) { throw 'Unsupported quest schema.' }
if ($quest.schemaVersion -eq 1) {
    foreach ($field in @('handoffRevision', 'acceptanceCriteria')) {
        if ($null -eq $quest.PSObject.Properties[$field]) { throw "Missing quest field: $field" }
    }
} else {
    foreach ($field in @('summary', 'requirements')) {
        if ($null -eq $quest.PSObject.Properties[$field]) { throw "Missing quest field: $field" }
    }
}
if ($quest.taskId -notmatch '^[a-z0-9][a-z0-9-]{0,49}$') { throw 'Invalid task ID.' }
if ($quest.schemaVersion -eq 1 -and $quest.handoffRevision -notmatch '^[a-fA-F0-9]{40}$') { throw 'Handoff revision must be a full commit SHA.' }
if ($quest.issueKey -notmatch '^[A-Z][A-Z0-9]+-[0-9]+$') { throw 'Invalid JIRA issue key.' }
if ($quest.issueFingerprint -notmatch '^[a-fA-F0-9]{64}$') { throw 'Issue fingerprint must be SHA-256.' }
if ($quest.baseRevision -notmatch '^[a-fA-F0-9]{40}$') { throw 'Base revision must be a full commit SHA.' }
$criteria = @(if ($null -ne $quest.PSObject.Properties['acceptanceCriteria']) { @($quest.acceptanceCriteria) } else { @() })
if ($quest.schemaVersion -eq 1 -and ($criteria.Count -eq 0 -or @($criteria | Where-Object { [string]::IsNullOrWhiteSpace([string]$_) }).Count -gt 0)) {
    throw 'At least one nonempty verbatim acceptance criterion is required.'
}
$requirements = @(if ($quest.schemaVersion -eq 2) { @($quest.requirements) } else { @($criteria) })
if ($requirements.Count -eq 0 -or @($requirements | Where-Object { [string]::IsNullOrWhiteSpace([string]$_) }).Count -gt 0) {
    throw 'At least one nonempty verbatim ticket requirement is required.'
}

if ([string]::IsNullOrWhiteSpace($IterativeImplementationSkillPath)) {
    $skillCandidates = @(
        [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\iterative-implementation'))
    )
    $IterativeImplementationSkillPath = @($skillCandidates | Where-Object {
            Test-Path -LiteralPath (Join-Path $_ 'SKILL.md') -PathType Leaf
        } | Select-Object -First 1)[0]
}
if ([string]::IsNullOrWhiteSpace($IterativeImplementationSkillPath)) {
    throw 'The iterative-implementation skill could not be located.'
}
$iterativeSkillRoot = [System.IO.Path]::GetFullPath($IterativeImplementationSkillPath)
$iterativeSkillSource = Join-Path $iterativeSkillRoot 'SKILL.md'
$iterativeTemplateSource = Join-Path $iterativeSkillRoot 'references\implementation-steps-template.md'
$complexityGuardSource = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\app\complexity.py'))
if (-not (Test-Path -LiteralPath $complexityGuardSource -PathType Leaf)) { throw 'The shared complexity guard is missing.' }
if (-not (Test-Path -LiteralPath $iterativeSkillSource -PathType Leaf)) {
    throw 'The iterative-implementation SKILL.md is missing.'
}
if (-not (Test-Path -LiteralPath $iterativeTemplateSource -PathType Leaf)) {
    throw 'The iterative-implementation plan template is missing.'
}

$source = [string]$quest.sourceRepository
$localSource = $null
if (Test-Path -LiteralPath $source -PathType Container) {
    $localSource = (Get-Item -LiteralPath $source -Force).FullName
    $null = Invoke-Git @('-C', $localSource, 'rev-parse', '--git-dir')
    $source = $localSource
} elseif ($source -notmatch '^https://github\.com/[^/\s]+/[^/\s]+(?:\.git)?$') {
    throw 'Source repository must be an existing local Git checkout or an HTTPS GitHub repository without credentials.'
}

if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
    $DestinationRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('handoffs-jira-quest-' + [Guid]::NewGuid().ToString('N'))
}
$destination = [System.IO.Path]::GetFullPath($DestinationRoot)
if (Test-Path -LiteralPath $destination) { throw 'DestinationRoot must not already exist.' }
$null = New-Item -ItemType Directory -Path $destination
$repository = Join-Path $destination 'repo'
$contractRoot = Join-Path $destination 'executor-contract\iterative-implementation'
$contractReferences = Join-Path $contractRoot 'references'
$artifactsRoot = Join-Path $destination 'artifacts'
$null = New-Item -ItemType Directory -Path $contractReferences -Force
$null = New-Item -ItemType Directory -Path $artifactsRoot -Force
$iterativeSkillFile = Join-Path $contractRoot 'SKILL.md'
$iterativeTemplateFile = Join-Path $contractReferences 'implementation-steps-template.md'
[System.IO.File]::Copy($iterativeSkillSource, $iterativeSkillFile)
[System.IO.File]::Copy($iterativeTemplateSource, $iterativeTemplateFile)
$contractScripts = Join-Path $contractRoot 'scripts'
$null = New-Item -ItemType Directory -Path $contractScripts
$complexityGuardFile = Join-Path $contractScripts 'complexity.py'
[System.IO.File]::Copy($complexityGuardSource, $complexityGuardFile)
$planFile = Join-Path $artifactsRoot 'iterative_implementation_items.txt'
$statusFile = Join-Path $artifactsRoot 'iterative_implementation_items_status.txt'

$null = Invoke-Git @('clone', '--no-checkout', '--no-tags', '--', $source, $repository)
$null = Invoke-Git @('-C', $repository, 'checkout', '--detach', [string]$quest.baseRevision)
$head = @(Invoke-Git @('-C', $repository, 'rev-parse', 'HEAD') | Select-Object -First 1)[0]
if ($head -cne ([string]$quest.baseRevision).ToLowerInvariant()) {
    throw 'Disposable checkout did not resolve to the pinned base revision.'
}

$constraints = if ($null -ne $quest.PSObject.Properties['constraints']) { @($quest.constraints) } else { @() }
$normalized = [ordered]@{
    schemaVersion = [int]$quest.schemaVersion
    taskId = [string]$quest.taskId
    issueKey = [string]$quest.issueKey
    issueFingerprint = ([string]$quest.issueFingerprint).ToLowerInvariant()
    sourceRepository = [string]$quest.sourceRepository
    baseRevision = $head
}
if ($quest.schemaVersion -eq 1) {
    $normalized.handoffRevision = ([string]$quest.handoffRevision).ToLowerInvariant()
} else {
    $normalized.summary = [string]$quest.summary
    $normalized.requirements = $requirements
}
$normalized.acceptanceCriteria = $criteria
$normalized.constraints = $constraints
$savedQuest = Join-Path $destination 'quest.json'
[System.IO.File]::WriteAllText($savedQuest, (($normalized | ConvertTo-Json -Depth 6) + "`n"), $utf8)

$prompt = @"
Execute one atomic JIRA quest in the disposable repository at:
$repository

Read the applicable repository instructions, then read the immutable quest contract at:
$savedQuest

Read and follow the packaged iterative-implementation contract at:
$iterativeSkillFile

Before editing source, write its plan and status artifacts to these exact paths:
$planFile
$statusFile

The plan must be JSON with a steps hierarchy and only HIGH/MEDIUM/LOW labels: HIGH -> either 2+ HIGH children or exactly 3 MEDIUM children, never a mixture; MEDIUM -> exactly 3 LOW children. HIGH descendants must eventually reach LOW. Only LOW leaves execute or commit. Validate and commit using the standalone guard at:
$complexityGuardFile

This is a continuous delegated executor session: proceed through the retained plan without asking the parent between items. Treat the ticket requirements and any acceptance criteria as verbatim authority and as the scope ceiling. Inspect only relevant source. Implement the most minimal solution that satisfies exactly those criteria. Do not add cleanup, refactoring, hardening, error behavior, abstractions, documentation, or tests beyond the narrowest proof required by a criterion. Ask one concise question and stop if a material decision is missing.

Before committing each LOW leaf, compare every changed line and behavior with the retained plan and criteria, and remove anything not required. Stage only that leaf's declared files and use the guard's commit action with --plan, --step, --repository and --message. Never commit a HIGH or MEDIUM parent or bypass the guard with direct git commit; never commit the plan artifacts. Do not push, mutate JIRA, record human acceptance, or award rewards; the calling agent handles branch publication and PR creation. Return both plan artifacts verbatim, a requirement-by-requirement evidence matrix, exact validation results, unresolved gaps, an explicit plan-to-diff conformance statement, and the local commit SHAs per LOW leaf.
"@

[pscustomobject][ordered]@{
    schemaVersion = 1
    taskId = $normalized.taskId
    issueKey = $normalized.issueKey
    repositoryRoot = $repository
    questFile = $savedQuest
    iterativeImplementationSkillFile = $iterativeSkillFile
    complexityGuardFile = $complexityGuardFile
    planFile = $planFile
    statusFile = $statusFile
    baseRevision = $head
    modelPolicy = [ordered]@{
        selection = 'strongest-available'
        preferred = 'astra'
        reasoningEffort = 'high'
        agents = 1
    }
    cleanupAfter = 'parent-verifies-plan-and-pr-confirmed-remote'
    prompt = $prompt.Trim()
} | ConvertTo-Json -Depth 6
