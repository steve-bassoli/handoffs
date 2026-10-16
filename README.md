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

## Luna bounty execution

Every bounty detail has an **Artifacts** section before acceptance, with individual
downloads and **Download all artifacts (ZIP)**. These read-only downloads include
stored requirements, history, imported packet files, posted source attachments,
and existing AI inputs/results when present. They never claim work or call a model.
External references are listed separately, not fetched or included automatically.
For legacy imports, canonical goal/criteria are projected from the preserved
specification, root `context.md` contains that full specification, and the recorded
completion actor is shown separately from the historical assignment.
Every export includes a checksummed `handoff.json`, visible missing-input warnings,
and a response template. Supplied source is not a claim of complete or live-tested
readiness. ZIP bytes are stable while the stored inputs are unchanged.
Attach a focused source ZIP while posting to make those files available for review
before anyone accepts; Luna can reuse that source when the bounty is later started.

Participants can attach **Source / supporting evidence** or a **Response from a
fresh session** on the bounty page, including on completed historical bounties.
The ZIP must contain UTF-8 files and root `manifest.json` with `schema_version: 1`,
the matching `task_id`, and `files` listing every other file's relative `path` and
lowercase `sha256`. Limits: 200 files / 2 MB unpacked; no secrets or nested ZIPs.
Attach the original bounty ZIP with a response to verify its `input_sha256` and
bounty ID; without it, linkage is explicitly unverified. Uploads preserve status,
are auditable/idempotent, and never run code, pay Gold, start AI, or create tasks.
Support files under `source/` can be reused by a later Luna run; response contents
are evidence, not automatically applied source. Downloads include both packages.
Use `/#bounty=<id>` to link directly to a bounty page.

To package selected committed source without copying a dirty working tree or
fetching a repository:

```powershell
.\.venv\Scripts\python.exe -m app.packages --repository C:\path\to\repo --ref <full-commit> --bounty-id <id> --path src/example.py --notes setup-and-checks.md --output support.zip
```

Repeat `--path` for each required file. The builder records repository, exact
revision, selected paths, and original blob hashes; it refuses to overwrite output.
The optional notes should state prerequisites, exact checks/exit codes, and any
outstanding live verification. The builder does not execute supplied code.

Set `OPENAI_API_KEY` in the server environment and restart the server. The default
test model is `gpt-6-luna`; `HANDOFFS_AI_MODEL` can select another explicitly chosen
model. The key is used only in the server's Authorization header.

Open a bounty and choose **Start with Luna**. Attach a focused ZIP of UTF-8 source
files (up to 200 files / 2 MB unpacked), excluding secrets, Git data, and dependency
trees. Luna can list/read the supplied files, asks at most three questions total,
and records API calls, tokens, elapsed time, questions and answers in the task.
Repository URLs and context links are references; this prototype does not fetch
private repositories or execute the generated code on the host.

A fix ZIP contains `START_HERE.md`, the patched `workspace/`, `changes.patch`, task
criteria and run history. Drop it into a fresh Codex chat for local verification.
Use **Confirm locally verified** with evidence to close the task. Generated test
commands are explicitly unexecuted until the developer runs them.

Complexity is enforced in the engine: **HIGH → either 2+ HIGHs or exactly 3 MEDIUMs;
MEDIUM → exactly 3 LOWs**. HIGH cannot mix child levels, and its descendants must
eventually reach LOW. Only HIGH/MEDIUM/LOW are valid labels. A LOW root is valid; filler tasks
are not. Invalid or missing delivery plans cannot publish a fix. The hierarchy is
displayed with the run and included in the fix ZIP alongside the standalone guard.
Only LOW leaves may produce commits through the managed commit command:

```powershell
python app/complexity.py validate --plan implementation-plan.json
python app/complexity.py commit --plan implementation-plan.json --step <low-id> --repository <checkout> --message "Apply bounded change"
```

The gate checks the full decomposition and rejects parent commits or staged files
outside the selected leaf, then records its ID and plan fingerprint in the commit.
This governs the engine/executor workflow, not arbitrary Git commands elsewhere;
no global Git hook is installed. Decomposition alone never publishes new bounties.

If a fix cannot be produced, the attempt closes with proposed follow-ups. Select
and confirm the exact tasks to create; proposals alone never create tasks. Child
tasks retain the parent link and inherit source/context when started without a new
ZIP. The expandable task tree and event history show the whole chain. These AI
actions neither pay rewards nor reserve new Gold for children. Restarted in-flight
turns require an explicit retry; answered and completed runs survive restart.

API routes under `/api/v1/bounties/{id}`: `ai/start`, `ai/answers`, `ai/retry`,
`ai/confirm-followups`, `ai/complete`, `ai/artifact`, and `lineage`. Writes use the
same operation ID contract as the existing service. The existing demo identity
selector is still simulated; the model key stays on the server.

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

## JIRA to review PR

The migrated [JIRA-to-PR skill](skills/jira-to-pr/SKILL.md) prepares a source-pinned disposable checkout using the packaged [iterative implementation contract](skills/iterative-implementation/SKILL.md). Its PR creation command, `python -m app.jira_pr`, removes the issue key from the title and rejects remaining JIRA-shaped keys before calling GitHub. Issue linkage stays in branch/body. This is a local execution workflow, not a new web-app button or permission to create a PR from a bounty preview. Legacy Git-packet and local XP/reward paths are retired, not copied into the service.

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
