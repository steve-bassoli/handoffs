# Private team demo

This is a temporary laptop-hosted demo, not production deployment. Mock users can impersonate one another and PR verification is simulated. Default to named trusted participants; the owner can explicitly opt into all reachable clients on the selected private interface. Do not expose this service to the public Internet, create a public tunnel or change company network policy to make it reachable.

## Host setup

### Routine publishing

The user has authorized automatic deployment after each completed, verified local
change batch. The existing canonical checkout is `C:/hackathon/handoffs`; deploy
the tested source from `C:/work/modern_watson/handoffs` without a remote Git push:

```powershell
# Run from the tested source checkout. Substitute its verified full commit SHA.
.\scripts\publish-demo.ps1 -RepositoryRoot 'C:\hackathon\handoffs' `
  -SourceRepository 'C:\work\modern_watson\handoffs' -SourceCommit '<full-tested-commit-SHA>'
```

The local source must be a real filesystem checkout and the release must be an
exact commit. The publisher fetches it into `FETCH_HEAD`, verifies a fast-forward,
and does not change `origin` or its tracking references. The ordinary no-source
command below retains its existing `origin/main` behavior. No remote push is
implied by auto-deploy. Preserve the existing database and network scope; do not
pass initialization/network flags for routine releases. Stop for unsafe migrations
or dirty/divergent checkouts instead of discarding local work.

Use ordinary PowerShell for app publishing. The one-time handoff below copies the
existing approved firewall scope into `HANDOFFS-Team-Access-8000` and replaces the
old administrator-owned listeners. Approve its single Windows administrator prompt;
only network setup runs elevated. The new web servers run as the ordinary user.
The scoped firewall rule persists until explicitly removed.

```powershell
# Once, using the actual current approved private interface address:
.\scripts\publish-demo.ps1 -SharedAddress '10.20.30.40' -InitializeSharedAccess
# Every subsequent publish:
.\scripts\publish-demo.ps1
```

Routine publishing uses a clean fast-forward, takes a consistent SQLite backup,
migrates once, restarts only this checkout's listeners, checks their health, and
prints the commit and URLs. It reuses the saved address, database, and existing
network rule; it does not request elevation or change the firewall. Logs, backups,
and publish state stay under ignored `.data/`. A changed VPN address requires
reviewing the network rule; it is never silently replaced or broadened.

The original manual launcher below remains available for temporary sessions.

Obtain the host's private VPN/LAN IPv4 address and Nate and Will's private client IPv4 addresses from the interfaces actually used for their connection. VPN client isolation may prohibit inbound traffic even with a local firewall rule. Private addresses alone do not establish end-to-end reachability.

From elevated PowerShell on Steve's laptop, run the following with actual addresses (the example values are placeholders):

```powershell
Set-Location C:\hackathon\handoffs
.\scripts\start-team-demo.ps1 -ListenAddress '10.20.30.40' -AllowedClientAddress @('10.20.30.41', '10.20.30.42')
```

To allow anyone who can reach the selected private interface, replace `-AllowedClientAddress ...` with `-AllowNetworkClients`. This explicitly removes the per-person allowlist; it does not enable Internet routing, and company VPN policy may still block peers. All reachable clients can modify demo work and impersonate users.

The script binds only the selected address, scopes the firewall rule to that interface/port and reuses this checkout's `.data/handoffs.sqlite`. The loopback server can remain running. Keep the terminal open and laptop awake. Ctrl+C runs cleanup of the named firewall rule. If the shell is forcibly terminated, inspect and remove the remaining rule with `Remove-NetFirewallRule -Name HANDOFFS-Team-Demo-8000` in an elevated terminal. Do not disable the firewall. VPN address changes require stopping and restarting with current addresses.

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
