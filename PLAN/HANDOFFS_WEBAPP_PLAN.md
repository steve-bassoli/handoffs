# HANDOFFS Web Application Prototype Plan

## Status

Implementation started at Steve's direction on October 16, 2026. HANDOFFS is an independent service with one minimal client skill in Hackwatson. Track completed steps and evidence in the linked iterative status artifact.

## Goal

Extract the HANDOFFS concept from `nate-viniconis/hackwatson` into an independently owned application at `steve-bassoli/handoffs`. Deliver a web marketplace where users receive monthly Gold, post funded work bounties, and earn transferable Gold by delivering work using their own token allowances.

## Gold economy: core product direction

Steve's direction, October 16, 2026: token allowances belong to individual people and are not transferable. Gold makes access to work capacity transferable: a requester pays another user to use that user's tokens and deliver the requested PR. The worker can spend the earned Gold on their own bounties. Every user receives Gold at the beginning of each month, analogous to receiving a token allowance.

Gold is the application's work currency. XP, levels, aliases, and Tavern themes remain optional presentation. Actual token balances stay with their providers; Gold coordinates who performs work and does not transfer tokens or guarantee someone is available.

"Bitcoin-like" describes a transferable currency and transaction history here. A centralized SQLite ledger is the proposed prototype implementation. Blockchain, mining, fixed supply, cash exchange, and an exchange rate between Gold and tokens are not implied requirements. Monthly allocations explicitly create new Gold.

### Proposed bounty cycle

1. Credit each eligible user's wallet once per calendar month using a unique user/month allocation key.
2. A requester posts a bounty and reserves its Gold in escrow. Available balance excludes reserved Gold.
3. Another user takes the bounty and uses their own account and tokens to perform the work.
4. The worker delivers the required PR and completion evidence.
5. Settle the bounty once: move its reserved Gold to the worker's available balance when the posted delivery terms are met.
6. The worker can immediately use those earnings to fund another bounty.

Settlement pays from the requester's reserved balance; it does not mint an additional completion reward. Monthly issuance, escrow, settlement, and refunds have explicit ledger entries and execute atomically with the corresponding bounty transition. Repeated requests cannot double-credit or double-pay; concurrent requests cannot spend the same Gold twice.

### Demo economic defaults under autopilot

- Monthly allocation: 1000 integer Gold per demo user, configurable by HANDOFFS_MONTHLY_GOLD; America/New_York calendar; unused Gold rolls over. Wallet access/action issues the current month's grant once, without backfilling skipped months.
- Payout: automatic when the delivery adapter reports success. The initial adapter simulates success; human review and merge remain separate.
- Cancellation: refund an unclaimed bounty only. No automatic cancellation, reassignment or dispute arbitration after claim.
- Legacy balances: preserve historical awards as data and issue no spendable opening currency from them.

## Prototype principles

- Steve's direction: implement the minimum or fake external behavior behind replaceable interfaces; follow the service/client architecture without building production security.
- Prefer the smallest understandable stack over production architecture.
- Treat funded bounties and transferable Gold as core domain behavior; keep XP and game presentation optional.
- Preserve append-only event history and immutable completion evidence.
- Treat imported Hackwatson packets as untrusted historical input.
- Keep Hackwatson unchanged while building the replacement, then remove the superseded prototype during a deliberate cutover.
- Avoid permanent dual-write behavior between the two repositories.
- Defer enterprise deployment, high availability, and generalized workflow engines.

### Minimum Gold implementation

Keep working wallets, integer Gold amounts, an append-only transaction ledger, once-per-month grants, reserved bounty funds, and payout/refund transfers in SQLite. Keep balance checks, transaction boundaries, and unique operation IDs: these are the small amount of real behavior needed to demonstrate a coherent economy.

Authentication and PR verification may be mocked initially. Use a replaceable identity adapter that selects a demo user and a delivery adapter that returns an explicit simulated verification outcome. Both browser and skill exercise the same API and domain rules. Demo identity is not authenticated identity; simulated PR verification is not evidence that GitHub work satisfies the bounty. Responses and the UI identify mock mode.

Do not add blockchain, wallet key pairs, transaction signatures, hash chains, external hash checkpoints, mining, or production identity/session infrastructure for this prototype. Real authentication and GitHub verification can replace the adapters later without moving business rules into the client or changing the Gold lifecycle.

## Confirmed source inventory

The existing implementation is distributed across repository-local skills and scripts:

- `start`: plain task listing, Tavern flow, quest creation, JIRA-to-PR launch, and review acceptance.
- `init-hackwatson`: player entry, board presentation, quest preview, and journal behavior.
- `list-tasks`: metadata listing and the local SQLite index/ledger.
- `process-next-task`: Git packet reads and append-only task events.
- `watson-context-bounty`: reusable context capture and quest-offer behavior.
- `git-handoffs.ps1`: packet validation, listing, reads, assignments, status transitions, results, acknowledgements, and reviews.
- `handoffs-index.py`: SQLite indexing, player profiles, capacity readings, rewards, PR rewards, intro rewards, gold spending, search, and task relationships.
- Supporting scripts: board rendering, quest creation, JIRA preparation, PR-review quest creation, checkout refresh, and status email.

The current source of shared task truth is Git under `PLAN/handoffs/`. The local SQLite database contains derived/searchable task data plus local profiles, quota snapshots, and reward ledgers.

## Proposed architecture

### Application stack

- Backend: Python 3.11+ with FastAPI; initial runtime verification uses the installed Python 3.13.
- Database: SQLite with SQLAlchemy and Alembic migrations.
- Frontend: HTML/CSS and browser-native JavaScript served by FastAPI.
- Tests: pytest for domain/API behavior and a small browser smoke test only when the UI needs it.
- Packaging: one Python application, one local start command, no Node build step for the first prototype.

This keeps Python and JavaScript visible without introducing a separate frontend deployment or framework before the interaction model is proven.

### Repository shape

```text
handoffs/
  app/
    api/                 # HTTP routes and request/response models
    domain/              # task, event, identity, reward rules
    services/            # application workflows
    storage/             # SQLite models, migrations, repositories
    static/              # browser JavaScript, CSS, images
    templates/           # initial HTML shell
  skills/                # thin Codex-facing adapters and instructions
  migrations/            # Alembic database migrations
  scripts/               # import and local development utilities
  tests/                 # focused domain and API tests
  PLAN/                  # approved plans and migration evidence
```

### Ownership boundaries

- The web application owns domain rules and database writes.
- API routes translate HTTP only; services execute workflows; domain code enforces invariants.
- Skills become thin clients of the API. They do not duplicate state-transition rules.
- The UI uses the same API as skills.
- Delivery verification has an adapter at the settlement boundary, initially mocked. Real GitHub verification, JIRA, Outlook, quota lookups, and automated PR creation are later integrations.

## Target boundary: service plus one minimal skill

### Native desktop MCP bridge

Steve approved adding the native connection on October 16, 2026. A local stdio MCP server exposes six tools: `list_bounties`, `get_bounty`, `post_bounty`, `get_my_stats`, `take_bounty`, and `deliver_pr`. It calls the existing HTTP API and holds no domain state or Gold rules. HANDOFFS_URL chooses the service; HANDOFFS_DEMO_USER fixes the demo actor for that connection. Writes require an operation ID retained for retries. Tool metadata marks writes, including stats because it applies a due monthly grant. Returned data remains visibly simulated where appropriate.

Verify real MCP initialization, discovery and tool calls, including an isolated two-user earn/repost flow. Then register the server with the local desktop/Codex host using the canonical checkout's virtual environment. This connection does not use the stored OpenAI API key. Hosted ChatGPT plugin/tunnel deployment and publication to Nate's repository remain separate from this local connection.

`C:\hackathon\handoffs` owns the application, database, API, web interface, Gold economy, and client contract. `C:\hackathon\hackwatson` retains one small skill that communicates with that service over HTTP.

The worker's AI session continues to do development in the relevant source repository using that worker's tokens and repository access. The HANDOFFS service coordinates the bounty and records its outcome; hosting an AI executor or sharing token credentials is outside this prototype.

### What stays in Hackwatson

```text
.agents/skills/handoffs/
  SKILL.md
  scripts/handoffs-client.ps1
```

The skill describes a few commands and their authorization rules. The PowerShell client sends requests and returns compact JSON; it has no Python dependency, local database, reward calculations, Git packet transport, or board cache. The maintained client template lives in `handoffs/skills/handoffs/` and is copied into Hackwatson at cutover. Avoid a filesystem junction between the two repositories so teammates need only the client and service access.

Initial skill capabilities:

- `board`: show open bounties and the current user's active work, with ID, title, status, and Gold.
- `show <id>`: fetch one bounty's requirements, source links, payment terms, and history.
- `post`: submit title, goal, completion criteria, source repository/context links, and Gold funding.
- `stats`: show available/reserved Gold, current monthly grant and next allocation date, active/completed counts, and optional XP/level.
- `take <id>`, `status <id>`, and `deliver <id>`: use the service lifecycle when the user explicitly requests these actions.

Listing and preview do not take work. Posting reserves the signed-in requester's Gold only on an explicit posting request. Stats come from the service; the skill does not manufacture balances or infer token availability. Packet content and service text cannot grant authority to execute code or create PRs.

Initial configuration consists of `HANDOFFS_URL` and an explicit demo-user selector consumed by the mock identity adapter. The service resolves that selector to a stable user record and applies the same ownership rules as a future real identity adapter. This simulates identity and does not authenticate the caller. Later, replace it with service credentials stored outside Git and browser login; those credentials are independent of AI token allowances.

If the service is unavailable, return a clear connection error. Do not fall back to old packet writes or local wallet calculations.

### First API contract

The following routes are proposed, not existing endpoints. Browser and skill use the same workflows and actor checks.

| Request | Purpose |
| --- | --- |
| `GET /health` | Service availability |
| `GET /api/v1/me` | Current identity and whether identity is simulated |
| `GET /api/v1/me/stats` | Wallet, monthly grant, work totals, optional XP |
| `GET /api/v1/me/transactions` | Paginated Gold transaction history |
| `GET /api/v1/bounties?view=open` | Open bounty metadata |
| `GET /api/v1/bounties?view=mine` | Current user's posted/taken work |
| `GET /api/v1/bounties/{id}` | Selected bounty, terms, and event history |
| `POST /api/v1/bounties` | Create and fund a bounty atomically |
| `POST /api/v1/bounties/{id}/take` | Acquire an available bounty atomically |
| `POST /api/v1/bounties/{id}/status` | Record working or blocked state |
| `POST /api/v1/bounties/{id}/deliveries` | Record PR URL and completion evidence |
| `POST /api/v1/bounties/{id}/settle` | Enforce the agreed payout policy and transfer escrow |
| `POST /api/v1/bounties/{id}/cancel` | Apply the agreed cancellation/refund policy |

Lists return metadata with stable IDs, pagination, and check time; only a selected detail loads full context. Writes use idempotency keys retained across a retry. The service resolves the actor through the identity adapter, validates the current bounty state, and returns the resulting resource ID/state. Responses distinguish insufficient Gold, stale state/already taken, missing authority, and unavailable integrations. Mock responses explicitly identify simulated identity and delivery verification.

### Web interface

Keep four small surfaces: Board, My Work, Post Bounty, and Wallet/Stats. A bounty detail contains requirements, funding, claimant, PR delivery, and event history. The default presentation is plain; optional Tavern styling uses the same data and rules. Posting and taking should be short flows with a visible Gold amount and clear resulting state.

### Running the prototype

Use one Python process serving the API and web UI, backed by one persistent SQLite database outside Git. Local development can use localhost; teammate sessions need one reachable shared service URL, not independent per-user databases. Choose the host before team cutover and exercise access from a second session. Hosting infrastructure is a deployment choice, not a reason to add a distributed database for this prototype.

## Proposed data model

Use SQLite as the prototype's authoritative application store.

- `users`: stable application identity and display information.
- `tasks`: immutable task identity, title, description, creator, target, bounty, and creation time.
- `task_events`: append-only assigned, claimed, working, blocked, completed, acknowledged, accepted, and rejected events.
- `results`: immutable result content referenced by terminal events.
- `task_relations`: links between replacement, review, source, and follow-up tasks.
- `player_profiles`: alias and optional theme preferences, separate from authorization identity.
- `wallets`: user-owned Gold accounts with available and reserved balances derived from the ledger.
- `gold_transactions` and `gold_entries`: append-only, balanced transfers for monthly issuance, escrow, payout, and refunds, with unique operation keys and explicit issuance/escrow accounts.
- `monthly_allocations`: unique user/month issuance records and the allocation policy used.
- `bounties`: posted terms, requester, funded amount, claimant, escrow reference, delivery proof, and settlement state.
- `xp_events`: optional idempotent experience awards, separate from spendable Gold.
- `capacity_readings`: optional time-bounded quota snapshots.
- `external_links`: source issue, pull request, repository, revision, and evidence fingerprints.

Task status is derived from ordered valid events rather than updated destructively. Wallet ownership and task actions require application identity; aliases, XP, and Gold balances do not grant repository permissions. Gold transfers and bounty changes commit in one database transaction.

## Core prototype workflows

1. Receive the monthly Gold allocation and view available/reserved balances and transaction history.
2. Create a funded targeted or open quest by reserving Gold.
3. List open bounties and a user's current tasks.
4. Preview a quest's scope, Gold payment, and delivery terms.
5. Take an open bounty and perform it using the worker's own tokens.
6. Record working, blocked, or completed status with immutable evidence and the delivered PR.
7. Verify the delivery under the posted terms and settle escrow into the worker's wallet once.
8. Spend earned Gold on another bounty; support refunds under the agreed cancellation policy.
9. Acknowledge and explicitly accept or reject evidence separately from PR review or merge.
10. Search task metadata and history; show a plain board with optional Tavern presentation.
11. Import legacy Hackwatson packets and events with provenance and validation warnings.

## Migration approach

### What moves

- Domain behavior encoded in the HANDOFFS skills and PowerShell helpers.
- SQLite profile, search, capacity, and relationship behavior; redesign old cosmetic Gold awards as a funded currency ledger.
- Focused tests that define packet, event, identity, and reward invariants.
- Tavern presentation assets and copy that remain useful.

### What is rewritten

- PowerShell task/event logic becomes Python domain and service code.
- ASCII-only board rendering becomes API-backed web views; ASCII output may remain as a compatibility endpoint.
- Skill definitions become small API workflows pointing at this repository.

### What remains in Hackwatson after cutover

- Hackwatson product research and unrelated Watson plans.
- One minimal HANDOFFS client skill and a short repository instruction pointing to it.
- Historical Git commits remain recoverable. Retire active `PLAN/handoffs/` packet files after import reconciliation and a recorded source revision; keep unrelated Watson plans and context notes.
- Optional JIRA-to-PR, Outlook, quota, and merge automation is inventoried for later porting into `handoffs`; obsolete HANDOFFS implementations are removed from the active Hackwatson tree at cutover.

### Legacy import

Create a read-only importer that accepts an explicit Hackwatson path or Git revision, validates manifests/events/results, records source revision and paths, and reports gaps. The importer must be idempotent. It must never repair or rewrite the source repository and must not silently replace already imported events.

Import Git packets and local SQLite data as separate sources: the local database can contain profiles, balances, and ledger history absent from Git. Locate the actual database files and inspect their schemas before migration; do not assume one machine's temp database contains everyone's data. Use SQLite's backup mechanism for a consistent snapshot. Keep snapshots and personal data outside source control. Resolve duplicate or conflicting user/reward records explicitly.

### Hackwatson retirement checklist

After the replacement works, make one scoped Hackwatson change:

1. Pause legacy HANDOFFS writes and record the final source commit and consistent database snapshots.
2. Import and reconcile task IDs, states, events, results, profiles, and historical rewards. Record coverage gaps and the opening-balance decision.
3. Replace `start`, `init-hackwatson`, `list-tasks`, and `process-next-task` HANDOFFS functionality with the minimal `handoffs` skill. Optional aliases may invoke that skill only; they retain no independent logic.
4. Remove superseded renderers, Git packet writers, SQLite index/ledger helpers, bootstrap updaters, notifications, and tests for retired behavior from the active tree. Preserve useful rules/tests in the new service.
5. Remove HANDOFFS-specific prototype guidance from Hackwatson's `AGENTS.md`; keep Watson development instructions. Update `watson-context-bounty` to use the client for posting, or retire its HANDOFFS-specific wrapper while retaining useful context notes.
6. Inspect installed skill junctions/aliases and scheduled monitors that still point at retired paths. Update or disable only the identified HANDOFFS entries during cutover.
7. Verify two users can list, post, take, deliver, receive Gold, and repost through the shared service. Verify the skill makes no legacy DB or packet writes.

Keep a source revision, migration report, and database backup as the rollback point. If a rollback is needed after new service writes, reconcile those writes before enabling the old system; never let both stores accept writes concurrently.

## Delivery phases and approval gates

The executable breakdown follows Hackwatson's `skills/common/iterative-implementation/SKILL.md` and its implementation-steps template:

- [Ordered steps with criteria, dependencies, targets, complexity and validation](../codex/output/iterative_implementation_items.txt).
- [Step status and evidence](../codex/output/iterative_implementation_items_status.txt).

These retained planning artifacts are included in Git at Steve's explicit request to write and review the plan. Steve subsequently authorized autopilot: implement ready items in order, self-verify each and continue. The status artifact records evidence and actual blockers. Keep modules consolidated in app/main.py, app/services.py, app/storage.py, app/adapters.py and app/importer.py for this minimal prototype. Optional integrations and game polish are excluded from the queue.

### Phase 1: runnable skeleton and domain core

- Add the FastAPI application, configuration, SQLite migrations, and local start command.
- Implement task creation, append-only events, derived status, results, and identity checks.
- Implement wallets, monthly issuance, funded bounties, escrow, settlement, and refunds under the agreed policies.
- Add the API and minimal service client early, using replaceable mock identity and delivery-verification adapters so skill and browser share the same rules.
- Add focused tests for event ordering, immutable results, authorization, duplicate issuance/payment, and concurrent spending.

Gate: Steve can run the app locally and the API proves the monthly allocation -> funded bounty -> delivered PR -> payment -> new bounty cycle.

### Phase 2: useful web board

- Add plain open/current task views, task preview, task creation, status updates, and result entry.
- Add player profiles and optional Tavern presentation.
- Add wallet balances, transaction history, bounty funding, PR delivery, and payment state to the browser workflow.

Gate: the end-to-end lifecycle works through the browser using only the new repository.

### Phase 3: import and Hackwatson cutover

- Implement the read-only Hackwatson importer.
- Reconcile imported counts, event histories, results, relationships, profiles, and historical rewards; apply only explicitly approved opening balances.
- Install the minimal skill, execute the retirement checklist, and verify access from two independent user sessions.

Gate: imported quests reconcile, the thin skill lists/posts/shows stats, and Hackwatson's active HANDOFFS prototype has been retired with a recoverable checkpoint.

### Phase 4: optional integrations

- Add only the integrations still valuable after prototype use: GitHub/JIRA links, notifications, quota display, PR review/merge rewards, or deployment packaging.
- Keep each integration behind a narrow adapter and explicit authorization boundary.

Gate: Steve chooses integrations individually; none block the core prototype.

## Acceptance criteria for the prototype

- A fresh clone starts locally with documented commands and no dependency on the Hackwatson checkout.
- One minimal Hackwatson skill can list/post bounties and show authoritative stats through the same API as the browser.
- Hackwatson contains no active HANDOFFS database, packet writer, reward rules, or separate board implementation after cutover.
- Two demo user sessions use the shared service with distinct user records and consistent balances/state; the demo selector is explicitly simulated authentication.
- A user can create, view, assign or claim, update, complete, acknowledge, and review a task through the web app.
- Every state change produces an immutable, ordered event with actor and timestamp.
- Completion evidence remains immutable and acceptance remains a separate explicit event.
- Open and user-current task lists agree with derived event state.
- Monthly allocations occur once per eligible user/month, including after an app restart or a missed first-of-month run.
- Bounty posting reserves application Gold from its wallet; insufficient balance prevents funding.
- A delivered PR meeting the agreed payment terms transfers escrow once to the worker, who can spend it on another bounty.
- Ordinary bounty settlement creates no new Gold; only explicit issuance changes total supply.
- Concurrent funding and settlement cannot overspend wallets or duplicate payouts; cancellation follows the agreed refund policy.
- Cosmetic identity cannot authorize a task action.
- The legacy importer is read-only, repeatable, provenance-preserving, and reports malformed or incomplete source data.
- The default UI is plain and usable; Tavern mode is optional.
- Focused automated tests cover the domain invariants above.
- Mock authentication and PR verification are visible and replaceable; the prototype makes no claim of Bitcoin-like or production security.

## Exclusions from the first prototype

- Production hosting, SSO, enterprise authorization, and multi-tenant administration.
- Kubernetes, distributed databases, queues, or microservices.
- Automatic JIRA mutation, pull-request approval, or merge.
- Rewriting historical Hackwatson commits or maintaining permanent two-way synchronization.
- A generalized workflow designer or broad plugin framework.
- Blockchain, transaction signing, hash chains/checkpoints, and production authentication; external identity and PR checks may be simulated for the prototype.

## Decisions requiring Steve's approval

1. Repository visibility: create `steve-bassoli/handoffs` as **private**.
2. Prototype authority: make SQLite authoritative in the new app; use Git only for source/version control and legacy import evidence.
3. Initial stack: FastAPI plus browser-native JavaScript, with no Node framework or build step.
4. Cutover policy: build the service first, import packets and local database snapshots, then retire the Hackwatson prototype and leave one minimal HTTP client skill.
5. Scope order: build the Gold economy and bounty lifecycle first; add Tavern presentation second; defer JIRA, Outlook, quota, and automated PR creation. PR delivery evidence and verification belong in the core bounty lifecycle.
6. The demo defaults above apply under Steve's autopilot/minimal-prototype direction and remain adjustable for real deployment.
7. Shared service host and teammate connectivity must be chosen and verified before cutover. Begin with explicit demo identity and mocked PR verification; replace these adapters when real access is needed.

Steve authorized continuous minimal implementation with self-verification. Team-wide legacy retirement still depends on a reachable shared service and final source reconciliation.
