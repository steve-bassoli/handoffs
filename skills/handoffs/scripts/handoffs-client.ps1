[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('Board','Mine','Show','Post','Stats','Transactions','Take','Status','Deliver','Review','Settle','Cancel')]
    [string]$Action,
    [Alias('BountyId')][string]$TaskId,
    [string]$BodyJson = '{}',
    [string]$OperationId,
    [string]$ServiceUrl = $env:HANDOFFS_URL,
    [string]$DemoUser = $env:HANDOFFS_DEMO_USER,
    [int]$Offset = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ServiceUrl)) { $ServiceUrl = 'http://127.0.0.1:8000' }
if ([string]::IsNullOrWhiteSpace($DemoUser)) { $DemoUser = 'steve' }
$headers = @{ 'X-Demo-User' = $DemoUser }
$method = 'Get'
$path = switch ($Action) {
    'Board' { "/tasks?view=open&offset=$Offset" }
    'Mine' { "/tasks?view=mine&offset=$Offset" }
    'Stats' { '/me/stats' }
    'Transactions' { "/me/transactions?offset=$Offset" }
    'Post' { $method = 'Post'; '/tasks' }
    default {
        if ([string]::IsNullOrWhiteSpace($TaskId)) { throw 'TaskId is required.' }
        $encodedId = [Uri]::EscapeDataString($TaskId)
        if ($Action -eq 'Show') { "/tasks/$encodedId" }
        else {
            $method = 'Post'
            $suffix = switch ($Action) { 'Deliver' { 'deliveries' }; 'Review' { 'reviews' }; default { $Action.ToLowerInvariant() } }
            "/tasks/$encodedId/$suffix"
        }
    }
}
$arguments = @{ Uri = $ServiceUrl.TrimEnd('/') + '/api/v1' + $path; Method = $method; Headers = $headers; TimeoutSec = 30 }
if ($method -eq 'Post') {
    if ([string]::IsNullOrWhiteSpace($OperationId)) { throw 'Supply and retain OperationId for a write; reuse it after an uncertain response.' }
    $null = $BodyJson | ConvertFrom-Json
    $headers['Idempotency-Key'] = $OperationId
    $headers['X-Automation'] = 'handoffs-client'
    $headers['X-Action-Intent'] = 'user-directed'
    $arguments['Body'] = [System.Text.Encoding]::UTF8.GetBytes($BodyJson)
    $arguments['ContentType'] = 'application/json; charset=utf-8'
}
$result = Invoke-RestMethod @arguments
$result | ConvertTo-Json -Depth 30
