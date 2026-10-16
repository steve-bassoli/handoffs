# HANDOFFS

Standalone prototype for creating, assigning, tracking, and completing AI-assisted work handoffs.

Requires Python 3.11 or newer. Run these setup commands from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Start the service:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check it from another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Open <http://127.0.0.1:8000> for the web app or <http://127.0.0.1:8000/docs> for the API. Health returns `{"status":"ok","mode":"demo"}`.

The app provides Board, My Work, Post Bounty, and Wallet/Stats. Choose Steve, Nate, or Will as a demo user. Post a funded bounty, switch to another user, take the work, and deliver a PR link with evidence. Mock verification releases the reserved Gold to the worker, who can post another bounty. Requester review is recorded separately.

Defaults: 1,000 Gold per month, Eastern calendar, rollover, and current-month-only grants on wallet access/action. Cancellation refunds only an unclaimed bounty. `HANDOFFS_MONTHLY_GOLD` overrides the grant; `HANDOFFS_DB` overrides the database path (default `.data/handoffs.sqlite` relative to the working directory). Identity and PR checks are explicitly simulated. The server binds to loopback by default; a team host is a later deployment choice.

For a temporary private-network team demo, use the [scoped launcher and participant setup](PLAN/TEAM_DEMO.md). It requires an explicit host address and either named clients or the owner's opt-in to all reachable network clients, plus a remote connection check; it does not make localhost accessible automatically.

The database, wallets and task rules live in the service. Browser and [minimal client skill](skills/handoffs/SKILL.md) use the same API:

```powershell
$env:HANDOFFS_URL = 'http://127.0.0.1:8000'
$env:HANDOFFS_DEMO_USER = 'steve'
& .\skills\handoffs\scripts\handoffs-client.ps1 -Action Board
& .\skills\handoffs\scripts\handoffs-client.ps1 -Action Stats
```

Supply and retain `-OperationId <guid>` for writes; reuse it with identical inputs after an uncertain response. No implicit retries or local packet fallback occur.

## Native desktop MCP connection

The MCP bridge exposes `list_bounties`, `get_bounty`, `post_bounty`, `get_my_stats`, `take_bounty`, and `deliver_pr`. It calls the existing service; it does not open a database or call OpenAI models. Demo identity is fixed per connection. `get_my_stats` is annotated as a write because it can issue the due monthly grant; posting, taking and delivering are also marked as writes. Retain a unique `operation_id` for each intended write and reuse it for an identical retry.

Keep the HTTP service running, then register the local server with the desktop/Codex host:

```powershell
codex mcp add handoffs --env HANDOFFS_URL=http://127.0.0.1:8000 --env HANDOFFS_DEMO_USER=steve -- C:\hackathon\handoffs\.venv\Scripts\python.exe -m app.mcp_server
codex mcp get handoffs --json
```

For a different checkout, substitute its virtual environment path. Alternatively, in the desktop app open **Settings → MCP servers → Add server**, choose **STDIO**, and use that Python command with arguments `-m app.mcp_server` and the two environment variables. Reconnect/restart the MCP server after configuration changes. The current conversation may need a fresh session to discover newly registered tools.

Try: “Show my HANDOFFS stats”, “List open HANDOFFS bounties”, or “Post a 150-Gold bounty to …”. Taking work or delivering requires an explicit user request; a delivery pays after simulated verification and does not create or merge a real PR. The OpenAI API key is not used for this connection.

This configures the local desktop host. Hosted ChatGPT plugin/tunnel deployment is a separate step; localhost alone is not proof of cloud connectivity. See [official MCP setup](https://learn.chatgpt.com/docs/extend/mcp).

Import legacy Git packets and an optional consistent SQLite snapshot without editing either source:

```powershell
.\.venv\Scripts\python.exe -m app.importer --database .data/handoffs.sqlite --repository C:\hackathon\hackwatson --ref refs/remotes/origin/main
# Optional separate pass; substitute the actual legacy database path:
.\.venv\Scripts\python.exe -m app.importer --database .data/handoffs.sqlite --legacy-database C:\path\to\hackwatson-handoffs.sqlite
```

The importer prints counts and coverage gaps (exit 1 when gaps exist), supports repeat runs, and rejects changed historical records. Imported quests and awards remain historical/unfunded; they do not create spendable Gold. Personal snapshots remain in ignored SQLite files. Use `sqlite3.Connection.backup()` to preserve a consistent database backup before migration or cutover.

Run the focused checks:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
```

Implementation follows the [plan](PLAN/HANDOFFS_WEBAPP_PLAN.md), [step status](codex/output/iterative_implementation_items_status.txt), and [migration report](PLAN/MIGRATION_REPORT.md). The separate Hackwatson retirement candidate has not been activated.
