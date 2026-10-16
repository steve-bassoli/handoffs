# The Commons

Ask freely. Share freely. Build together.

Human-guided AI software development through voluntary contribution and shared
learning. Formerly HANDOFFS; the existing `handoffs` package, `HANDOFFS_*`
configuration, MCP names, API routes, database and artifact identifiers remain
unchanged. This is a public-identity update, not an economic or data migration.

The [project charter](PROJECT_CHARTER.md) defines the
Watson REST/MCP, Gremlins and The Commons target, the rule of three, and one sufficient
proof artifact before LOW completion. It distinguishes the target from current
prototype enforcement.

The [empowerment constitution](PLAN/EMPOWERMENT_CONSTITUTION.md) establishes the
human purpose: voluntary Opportunities, unconditional daily Credits with a
protected reserve, reusable Knowledge and nonspendable Growth. No punitive resource
loss or work requirement for basic allocation. This is adopted design policy;
the current Gold/monthly-grant behavior and legacy technical identifiers remain
unchanged. No-obligation resource sharing and Growth recognition remain targets.

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

The app provides Opportunities, My Work, Post Opportunity, Gremlins, and Wallet/Stats. Choose Steve, Nate, or Will as a demo user. Volunteer for an opportunity, pin context, submit one sufficient proof and request AI review. Explicit human LOW verification is required before completion releases reserved demo Gold. A PR link cannot bypass this gate. Requester PR review remains separate.

Defaults: 1,000 Gold per month, Eastern calendar, rollover, and current-month-only grants on wallet access/action. Cancellation refunds only an unclaimed bounty. `HANDOFFS_MONTHLY_GOLD` overrides the grant; `HANDOFFS_DB` overrides the database path (default `.data/handoffs.sqlite` relative to the working directory). Identity and PR checks are explicitly simulated. The server binds to loopback by default; a team host is a later deployment choice.

For a temporary private-network team demo, use the [scoped launcher and participant setup](PLAN/TEAM_DEMO.md). It requires an explicit host address and either named clients or the owner's opt-in to all reachable network clients, plus a remote connection check; it does not make localhost accessible automatically.

Standing workflow: automatically deploy verified local change batches to the
existing port-8000 service using the [pinned local publisher](PLAN/TEAM_DEMO.md#routine-publishing).
Preserve the configured database and approved listeners. Remote pushes, public
hosting, new network exposure and unsafe data migrations are not covered by that
instruction; failures must be reported rather than calling a local commit live.

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
Use `/#opp=<id>` to link directly to an opportunity page. Existing `/#bounty=<id>` links still work.

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

New bounties default to HIGH; select HIGH/MEDIUM/LOW explicitly when posting.
Participants can reopen a completed record without an existing AI run as HIGH
for decomposition. This appends an audited event and preserves previous completion,
assignment, attachments and Gold; it never erases or repays the earlier work.

Open a bounty and choose **Propose child bounties with Luna** for HIGH/MEDIUM,
or **Start with Luna** for LOW. Attach a focused ZIP of UTF-8 source
files (up to 200 files / 2 MB unpacked), excluding secrets, Git data, and dependency
trees. Luna can list/read the supplied files, asks at most three questions total,
and records API calls, tokens, elapsed time, questions and answers in the task.
Repository URLs and context links are references; this prototype does not fetch
private repositories or execute the generated code on the host.

A fix ZIP contains `START_HERE.md`, the patched `workspace/`, `changes.patch`, task
criteria and run history. Drop it into a fresh Codex chat for local verification.
Use **Confirm locally verified** with evidence to close the task. Generated test
commands are explicitly unexecuted until the developer runs them.

Complexity is enforced in the engine: **HIGH → exactly 3 HIGHs or exactly 3 MEDIUMs;
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
no global Git hook is installed. Each implementation leaf/immutable plan fingerprint
can produce one managed commit; existing receipts are checked across local refs,
and managed commits are serialized. Verification leaves cannot commit. Rewriting
history or changing the approved plan to evade receipts is not permitted; this
guard is not enforcement over arbitrary Git clients. Decomposition alone never publishes new bounties.

Three is the design primitive, not a quota for filler. Every proposal set must
explain `why_three`, give each child a `work_type` (`implementation` or `verification`)
and zero-based `parent_criteria`, and cover all parent criteria. Review prior
evidence and existing prerequisites before proposing work. Facts, safety, human
decisions and the at-most-three question budget are not overridden by this rule.
The engine checks structure and coverage; humans still review semantic boundaries.

Implementation LOWs deliver exactly one executable LOW plan leaf and a minimal
patch. Verification LOWs use the separate `evidence` outcome: report files under
`evidence/` (.md/.txt/.json/.csv), proposed checks and review instructions, no
patch, executable plan or forced commit. Prepared evidence is downloadable before
human confirmation, but never means checks ran or acceptance was granted. Both
outcomes remain ready for explicit human verification; no reward is issued by AI.
Existing history and drafts are not rewritten. Older proposal sets lacking the
current rationale/type/coverage contract remain inspectable but fail approval.

HIGH/MEDIUM bounties cannot deliver implementations. Luna processes the original
requirements, attached fresh-session responses, provenance, and current support
evidence into typed child-bounty proposals, not merely plan nodes. The same strict
split rules apply to those proposals. A LOW bounty cannot create child bounties.
Proposals leave the parent `awaiting_approval`, with no child tickets created.
Approve the entire valid set; partial approval is rejected. Child
tasks retain the parent link and inherit source/context when started without a new
ZIP. Creation moves the parent to `decomposed`, not completed: children alone are
not integrated acceptance evidence. The expandable task tree and event history show the whole chain. These AI
actions neither pay rewards nor reserve new Gold for children. Restarted in-flight
turns require an explicit retry; answered and completed runs survive restart.

API routes under `/api/v1/bounties/{id}`: `ai/start`, `ai/answers`, `ai/retry`,
`ai/confirm-followups`, `ai/complete`, `ai/artifact`, `reopen`, and `lineage`. Writes use the
same operation ID contract as the existing service. The existing demo identity
selector is still simulated; the model key stays on the server.

## Context and proof

The bounty page projects **Posted → Claimed → Closed**, retaining detailed status
and disposition. Cancellation is not successful verification. Context declares
SIM/ORA/LIVE targets and WRAP/REPLACE/RETIRE migration intent, baseline/candidate
revisions, environment and Known (with source), Assumed and Unknown shelves.
Declarations do not prove execution. Mapper/Maker/Breaker are responsibilities,
not an automatically launched agent fleet. Link shared prerequisites rather than
copying tasks; the constellation rejects ancestry/dependency cycles.

One immutable primary proof is directly viewable/downloadable on a closed bounty
and in its artifact ZIP. Text/JSON is limited to 200 KB; PNG/JPEG/MP4 to 8 MB.
Replacements preserve history. Changed intent, source, profile or prerequisite
receipts make proof stale. Pin revisions and environment before attaching proof.

**Request AI proof review** explicitly calls the server-side provider without tools
or execution privileges, returning pass/fail/inconclusive for every criterion.
`HANDOFFS_PROOF_MODEL` overrides `HANDOFFS_AI_MODEL`. Missing access, provider errors,
inconsistent verdicts and unsupported MP4 review fail closed as inconclusive.
Text/JSON and PNG/JPEG are supported by the adapter; provider access is tested only
with fixtures. Restarted reviews require explicit retry, never automatic spending.
The separate LOW human decision is not another artifact. HIGH/MEDIUM acceptance
needs three verified children, shared prerequisites and separate integration proof.
Historical closures without proof remain historical.

Routes under `/api/v1/bounties/{id}`: `POST profile`, `POST dependencies`,
`GET constellation`, `POST proofs`, `GET proofs/{proof_id}`, `POST proof-review`,
`POST proof-human`, `POST complete`. Writes require operation IDs. `ai/complete`,
PR delivery and settlement enforce the same gate.

## Gremlins offline prototype

The **Gremlins** tab compares supplied Legacy/REST/MCP results, state and effects
against explicit expectations. Mimic detects mismatches; Saboteur injects a private
in-memory defect to check detection; Witness packages the comparison and a named
quirk's reproducer, preservation rule and source in one hashed report. Discrepancies
can draft a question, never create a bounty automatically.
`POST /api/v1/gremlins/{mimic|saboteur|witness}` performs the same computation.

Results are SIM-only with `watson_executed: false`. This checks supplied claims,
not their authenticity, and runs no Watson, application adapters or Oracle.
Independently curate expected behavior. Never submit secrets or live records.

Run the separate real read-only stdio MCP server with
`.\.venv\Scripts\python.exe -m app.gremlins_mcp`. Its three tools are `mimic`,
`saboteur` and `witness_report`; no HTTP service or API key is needed. Registration
in a desktop host is a separate explicit step.

## Native desktop MCP connection

The MCP bridge exposes `list_bounties`, `get_bounty`, `post_bounty`, `get_my_stats`, `take_bounty`, `deliver_pr`, and `get_bounty_context`. It calls the existing service; it does not open a database or call OpenAI models. Demo identity is fixed per connection. `get_my_stats` is annotated as a write because it can issue the due monthly grant; posting, taking and delivering are also marked as writes. Retain a unique `operation_id` for each intended write and reuse it for an identical retry.

Keep the HTTP service running, then register the local server with the desktop/Codex host:

```powershell
codex mcp add handoffs --env HANDOFFS_URL=http://127.0.0.1:8000 --env HANDOFFS_DEMO_USER=steve -- C:\hackathon\handoffs\.venv\Scripts\python.exe -m app.mcp_server
codex mcp get handoffs --json
```

For a different checkout, substitute its virtual environment path. Alternatively, in the desktop app open **Settings → MCP servers → Add server**, choose **STDIO**, and use that Python command with arguments `-m app.mcp_server` and the two environment variables. Reconnect/restart the MCP server after configuration changes. The current conversation may need a fresh session to discover newly registered tools.

Try: “Show my HANDOFFS stats”, “List open HANDOFFS bounties”, or “Post a 150-Gold bounty to …”. Taking work or delivering requires an explicit user request. Delivery requires the service proof gate as well as simulated PR verification and does not create or merge a real PR. The OpenAI API key is not used by the MCP bridge.

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
