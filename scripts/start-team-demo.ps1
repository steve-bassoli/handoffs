[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ListenAddress,
    [Parameter(Mandatory)]
    [string[]]$AllowedClientAddress,
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-PrivateIPv4 {
    param([string]$Address)
    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed)) { return $false }
    if ($parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    # Require exact canonical addresses, not abbreviated IPs, CIDRs or wildcards.
    if ($parsed.ToString() -ne $Address) { return $false }
    $octets = $parsed.GetAddressBytes()
    return ($octets[0] -eq 10 -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168))
}

if (-not (Test-PrivateIPv4 $ListenAddress)) {
    throw 'ListenAddress must be one exact private IPv4 address on the team LAN/VPN.'
}
if ($AllowedClientAddress.Count -eq 0) { throw 'At least one exact client address is required.' }
foreach ($address in $AllowedClientAddress) {
    if (-not (Test-PrivateIPv4 $address)) {
        throw 'AllowedClientAddress entries must be exact private IPv4 addresses; no ranges or wildcards.'
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in an elevated PowerShell terminal to create the scoped firewall rule.'
}
$localAddress = @(Get-NetIPAddress -AddressFamily IPv4 -IPAddress $ListenAddress -ErrorAction Stop)
if ($localAddress.Count -ne 1) { throw 'ListenAddress must identify exactly one local interface.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install the project virtual environment first.' }
$ruleName = "HANDOFFS-Team-Demo-$Port"
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    throw "Firewall rule $ruleName already exists. Inspect it before removing/reusing it."
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @($ListenAddress, '0.0.0.0', '::') }) {
    throw 'The requested team listener is already occupied.'
}

$previousDatabase = $env:HANDOFFS_DB
$ruleCreated = $false
Push-Location $projectRoot
try {
    # Use the same database as the local web app, regardless of the caller's cwd.
    $env:HANDOFFS_DB = Join-Path $projectRoot '.data\handoffs.sqlite'
    New-NetFirewallRule -Name $ruleName -DisplayName 'HANDOFFS private team demo' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port `
        -LocalAddress $ListenAddress -RemoteAddress $AllowedClientAddress `
        -InterfaceAlias $localAddress[0].InterfaceAlias -Profile Any | Out-Null
    $ruleCreated = $true
    Write-Host "Team demo: http://${ListenAddress}:$Port (mock identity; selected clients only)."
    Write-Host 'Keep this terminal open. Ctrl+C stops the server and removes its firewall rule.'
    & $python -m uvicorn app.main:app --host $ListenAddress --port $Port
    if ($LASTEXITCODE -ne 0) { throw "HANDOFFS server exited with code $LASTEXITCODE." }
}
finally {
    if ($ruleCreated) { Remove-NetFirewallRule -Name $ruleName }
    $env:HANDOFFS_DB = $previousDatabase
    Pop-Location
}
