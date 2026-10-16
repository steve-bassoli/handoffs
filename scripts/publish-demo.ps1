[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SharedAddress,
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [switch]$InitializeSharedAccess,
    [switch]$ConfigureNetwork,
    [string]$ResultPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$ruleName = "HANDOFFS-Team-Access-$Port"
$statePath = Join-Path $repo ".data\publish-$Port.json"

function Get-DemoListeners {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in $addresses })
}

function Get-DemoProcesses {
    foreach ($processId in @(Get-DemoListeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
        if (-not $process -or -not $process.CommandLine -or
            $process.CommandLine -notlike "*$repo\.venv\Scripts\python.exe*" -or
            $process.CommandLine -notlike '*-m uvicorn app.main:app*' -or
            $process.CommandLine -notmatch "--port $Port(?:\s|$)") {
            throw "Port $Port belongs to a different or elevated process. Use -InitializeSharedAccess for the one-time handoff."
        }
        $process
    }
}

function Stop-DemoListeners {
    # Validate every listener before stopping any of them.
    $processes = @(Get-DemoProcesses)
    foreach ($process in $processes) { Stop-Process -Id $process.ProcessId -Force }
}

if (-not $SharedAddress -and (Test-Path -LiteralPath $statePath)) {
    $SharedAddress = (Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json).sharedAddress
}
$addresses = @('127.0.0.1')
if ($SharedAddress) {
    $ip = $null
    if (-not [Net.IPAddress]::TryParse($SharedAddress, [ref]$ip) -or $ip.ToString() -ne $SharedAddress -or
        $ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { throw 'Use one exact private IPv4 address.' }
    $octets = $ip.GetAddressBytes()
    if (-not ($octets[0] -eq 10 -or ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168))) { throw 'SharedAddress must be a private LAN/VPN address.' }
    $addresses += $SharedAddress
}

if ($ConfigureNetwork) {
    $ruleCreated = $false
    try {
        if (-not $isAdministrator -or -not $SharedAddress -or -not $ResultPath) { throw 'Network initialization requires elevation, an address, and a result file.' }
        $oldRule = Get-NetFirewallRule -Name "HANDOFFS-Team-Demo-$Port" -ErrorAction Stop
        $scope = $oldRule | Get-NetFirewallAddressFilter
        $interface = $oldRule | Get-NetFirewallInterfaceFilter
        $filter = $oldRule | Get-NetFirewallPortFilter
        $application = $oldRule | Get-NetFirewallApplicationFilter
        $service = $oldRule | Get-NetFirewallServiceFilter
        if (@($scope.LocalAddress).Count -ne 1 -or $scope.LocalAddress -ne $SharedAddress -or
            $filter.LocalPort -ne "$Port" -or $filter.Protocol -notin @('TCP', '6') -or
            $filter.RemotePort -ne 'Any' -or $application.Program -ne 'Any' -or $application.Package -or
            $service.Service -ne 'Any' -or "$($oldRule.Enabled)" -ne 'True' -or
            "$($oldRule.Direction)" -ne 'Inbound' -or "$($oldRule.Action)" -ne 'Allow') { throw 'The original team firewall rule does not match this listener.' }
        $local = @(Get-NetIPAddress -AddressFamily IPv4 -IPAddress $SharedAddress -ErrorAction Stop)
        if ($local.Count -ne 1 -or $local[0].InterfaceAlias -ne $interface.InterfaceAlias) { throw 'Shared interface changed.' }
        if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) { throw 'Persistent rule already exists; inspect it rather than replacing it.' }
        $null = @(Get-DemoProcesses)
        # Preserve the existing scope. The web servers themselves will be started unelevated.
        New-NetFirewallRule -Name $ruleName -DisplayName 'HANDOFFS team access' -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $Port -LocalAddress $SharedAddress -RemoteAddress $scope.RemoteAddress `
            -InterfaceAlias $interface.InterfaceAlias -Profile $oldRule.Profile | Out-Null
        $ruleCreated = $true
        Stop-DemoListeners
        @{ status = 'ready'; rule = $ruleName } | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding utf8
    } catch {
        if ($ruleCreated) { Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue }
        @{ status = 'failed'; reason = $_.Exception.Message } | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding utf8
        exit 1
    }
    exit 0
}

if ($isAdministrator) { throw 'Run publishing in an ordinary PowerShell window. Only the one-time network helper elevates.' }
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install the project virtual environment before publishing.' }
if ($InitializeSharedAccess -and -not $SharedAddress) { throw 'Supply the current approved SharedAddress for the one-time handoff.' }
if ($SharedAddress -and -not $InitializeSharedAccess) {
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if (-not $rule) { throw 'One-time setup is required: supply -SharedAddress and -InitializeSharedAccess.' }
    $scope = $rule | Get-NetFirewallAddressFilter
    if ($scope.LocalAddress -ne $SharedAddress) { throw 'Network address changed; review the firewall configuration before publishing.' }
}
$dirty = @(git -C $repo status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { throw 'Publish requires a clean Git checkout; local work was preserved.' }
git -C $repo fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed; the running app was not changed.' }
git -C $repo merge-base --is-ancestor HEAD origin/main
if ($LASTEXITCODE -ne 0) { throw 'Checkout cannot fast-forward to origin/main; the running app was not changed.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$database = Join-Path $repo '.data\handoffs.sqlite'
$backup = $null
New-Item -ItemType Directory -Force (Join-Path $repo '.data') | Out-Null
if (Test-Path -LiteralPath $database) {
    $backup = Join-Path $repo ".data\before-publish-$stamp.sqlite"
    & $python -c 'import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); a.backup(b); b.close(); a.close()' $database $backup
    if ($LASTEXITCODE -ne 0) { throw 'Database backup failed; the running app was not changed.' }
}
git -C $repo merge --ff-only origin/main
if ($LASTEXITCODE -ne 0) { throw 'Fast-forward failed; the running app was not changed.' }
if ($InitializeSharedAccess) {
    $result = Join-Path $repo ".data\network-setup-$stamp.json"
    $script = Join-Path $repo 'scripts\publish-demo.ps1'
    $shell = (Get-Process -Id $PID).Path
    $helper = Start-Process -FilePath $shell -Verb RunAs -WindowStyle Hidden -WorkingDirectory $repo -PassThru `
        -ArgumentList "-NoProfile -File `"$script`" -RepositoryRoot `"$repo`" -SharedAddress $SharedAddress -Port $Port -ConfigureNetwork -ResultPath `"$result`""
    $helper.WaitForExit()
    if (-not (Test-Path -LiteralPath $result)) { throw 'Administrator setup did not finish; no web server was launched elevated.' }
    $setup = Get-Content -Raw -LiteralPath $result | ConvertFrom-Json
    if ($setup.status -ne 'ready') { throw $setup.reason }
}
Stop-DemoListeners
$previousDatabase = $env:HANDOFFS_DB
try {
    $env:HANDOFFS_DB = $database
    if (-not $env:OPENAI_API_KEY) { $env:OPENAI_API_KEY = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'User') }
    if (-not $env:OPENAI_API_KEY) { $env:OPENAI_API_KEY = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Machine') }
    Push-Location $repo
    try {
        & $python -c 'from app.storage import Database; import sys; d=Database(sys.argv[1]); d.migrate(); d.engine.dispose()' $database
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; backup is retained.' }
    } finally { Pop-Location }
    $urls = @()
    foreach ($address in $addresses) {
        $log = Join-Path $repo ".data\server-$address-$stamp"
        Start-Process -FilePath $python -WorkingDirectory $repo -WindowStyle Hidden `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $address, '--port', "$Port") `
            -RedirectStandardOutput "$log.log" -RedirectStandardError "$log-error.log" | Out-Null
        $url = "http://${address}:$Port"
        $ready = $false
        for ($i = 0; $i -lt 15; $i++) {
            try {
                $health = Invoke-RestMethod "$url/health" -TimeoutSec 2
                if ($health.status -eq 'ok') { $ready = $true; break }
            } catch { Start-Sleep -Milliseconds 250 }
        }
        if (-not $ready) { throw "Server not healthy at $url; inspect $log-error.log. Backup: $backup" }
        $urls += $url
    }
    $commit = (git -C $repo rev-parse HEAD).Trim()
    $state = [ordered]@{ status = 'ready'; commit = $commit; sharedAddress = $SharedAddress;
        port = $Port; urls = $urls; database = $database; backup = $backup; publishedUtc = [DateTime]::UtcNow.ToString('o') }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8
    $state | ConvertTo-Json -Depth 4
} finally { $env:HANDOFFS_DB = $previousDatabase }
