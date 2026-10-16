# Private team demo

This is a temporary laptop-hosted demo, not production deployment. Mock users can impersonate one another and PR verification is simulated. Allow only trusted participants. Do not expose this service to the public Internet, create a public tunnel or change company network policy to make it reachable.

## Host setup

Obtain the host's private VPN/LAN IPv4 address and Nate and Will's private client IPv4 addresses from the interfaces actually used for their connection. VPN client isolation may prohibit inbound traffic even with a local firewall rule. Private addresses alone do not establish end-to-end reachability.

From elevated PowerShell on Steve's laptop, run the following with actual addresses (the example values are placeholders):

```powershell
Set-Location C:\hackathon\handoffs
.\scripts\start-team-demo.ps1 -ListenAddress '10.20.30.40' -AllowedClientAddress @('10.20.30.41', '10.20.30.42')
```

The script binds only the selected address, permits only those client addresses on that interface/port and reuses this checkout's `.data/handoffs.sqlite`. The loopback server can remain running. Keep the terminal open and laptop awake. Ctrl+C runs cleanup of the named firewall rule. If the shell is forcibly terminated, inspect and remove the remaining rule with `Remove-NetFirewallRule -Name HANDOFFS-Team-Demo-8000` in an elevated terminal. Do not disable the firewall. VPN address changes require stopping and restarting with current addresses.

## Nate and Will

First open `http://HOST_ADDRESS:8000/health` from their own machines. Expect `{"status":"ok","mode":"demo"}`, then open `http://HOST_ADDRESS:8000/` and select the appropriate demo user. This remote check is required; a host-local request does not prove peer access.

For native desktop MCP access, obtain read access to the private `steve-bassoli/handoffs` repository and install a local checkout and Python 3.11+ virtual environment:

```powershell
git clone https://github.com/steve-bassoli/handoffs.git C:\hackathon\handoffs
Set-Location C:\hackathon\handoffs
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Register the local MCP bridge with the shared URL, substituting the actual host address and `nate` or `will`. Do not start a separate local HTTP service or import a second database:

```powershell
codex mcp add handoffs --env HANDOFFS_URL=http://HOST_ADDRESS:8000 --env HANDOFFS_DEMO_USER=nate -- C:\hackathon\handoffs\.venv\Scripts\python.exe -m app.mcp_server
```

Use the existing README's STDIO setup if configuring via the desktop UI. Restart/reconnect the MCP server, then ask it to list open HANDOFFS bounties. No OpenAI API key is needed. This local bridge is not a hosted ChatGPT connector.

## Acceptance and limits

Verify health from each peer, confirm all three see the same bounty IDs, then perform an explicitly authorized small funded-bounty cycle across two users and verify the shared wallet balances. Do not mark team access complete until those remote checks succeed. If corporate VPN routing denies peer traffic, stop and choose an approved shared host with the team; do not work around network controls.
