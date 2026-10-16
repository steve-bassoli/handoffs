# HANDOFFS Web Application Prototype Plan

## Status

Proposed for Steve's review. This repository contains planning only; implementation does not begin until Steve approves the decisions at the end of this document.

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

### Economic decisions still open

- Monthly allocation amount, eligibility, calendar timezone, and whether unused Gold rolls over. Proposed default: a configurable equal allocation, calendar months in America/New_York, and balances that roll over.
- Payout trigger: Steve described delivering a PR. Proposed default: payment on verified delivery meeting the posted bounty terms; PR review and merge remain separate. Decide whether requester acceptance is required before payment.
- Cancellation, abandonment, and disputes: define when escrow is refunded or reassigned, including what happens after work has begun.
- Legacy balances: old cosmetic awards are historical data. Do not silently turn them into spendable currency; choose an explicit opening-balance policy.

## Prototype principles

- Prefer the smallest understandable stack over production architecture.
- Treat funded bounties and transferable Gold as core domain behavior; keep XP and game presentation optional.
- Preserve append-only event history and immutable completion evidence.
- Treat imported Hackwatson packets as untrusted historical input.
- Keep the old repository unchanged during extraction.
- Avoid permanent dual-write behavior between the two repositories.
- Defer enterprise deployment, high availability, and generalized workflow engines.

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

- Backend: Python 3.12 with FastAPI.
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
- GitHub, JIRA, Outlook, and quota lookups sit behind optional integration adapters.

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

### What stays behind initially

- Hackwatson product research and unrelated Watson plans.
- Existing `PLAN/handoffs/` history, which remains unchanged and is imported through a read-only tool.
- JIRA-to-PR automation, Outlook email, live quota reads, and merge monitoring until the core workflow is stable.

### Legacy import

Create a read-only importer that accepts an explicit Hackwatson path or Git revision, validates manifests/events/results, records source revision and paths, and reports gaps. The importer must be idempotent. It must never repair or rewrite the source repository and must not silently replace already imported events.

## Delivery phases and approval gates

### Phase 1: runnable skeleton and domain core

- Add the FastAPI application, configuration, SQLite migrations, and local start command.
- Implement task creation, append-only events, derived status, results, and identity checks.
- Implement wallets, monthly issuance, funded bounties, escrow, settlement, and refunds under the agreed policies.
- Add focused tests for event ordering, immutable results, authorization, duplicate issuance/payment, and concurrent spending.

Gate: Steve can run the app locally and the API proves the monthly allocation -> funded bounty -> delivered PR -> payment -> new bounty cycle.

### Phase 2: useful web board

- Add plain open/current task views, task preview, task creation, status updates, and result entry.
- Add player profiles and optional Tavern presentation.
- Add wallet balances, transaction history, bounty funding, PR delivery, and payment state to the browser workflow.

Gate: the end-to-end lifecycle works through the browser using only the new repository.

### Phase 3: legacy extraction

- Implement the read-only Hackwatson importer.
- Reconcile imported counts, event histories, results, relationships, profiles, and historical rewards; apply only explicitly approved opening balances.
- Add compatibility skill adapters that call the new API.

Gate: representative existing quests appear correctly without modifying Hackwatson.

### Phase 4: optional integrations

- Add only the integrations still valuable after prototype use: GitHub/JIRA links, notifications, quota display, PR review/merge rewards, or deployment packaging.
- Keep each integration behind a narrow adapter and explicit authorization boundary.

Gate: Steve chooses integrations individually; none block the core prototype.

## Acceptance criteria for the prototype

- A fresh clone starts locally with documented commands and no dependency on the Hackwatson checkout.
- A user can create, view, assign or claim, update, complete, acknowledge, and review a task through the web app.
- Every state change produces an immutable, ordered event with actor and timestamp.
- Completion evidence remains immutable and acceptance remains a separate explicit event.
- Open and user-current task lists agree with derived event state.
- Monthly allocations occur once per eligible user/month, including after an app restart or a missed first-of-month run.
- Bounty posting reserves real wallet Gold; insufficient balance prevents funding.
- A delivered PR meeting the agreed payment terms transfers escrow once to the worker, who can spend it on another bounty.
- Ordinary bounty settlement creates no new Gold; only explicit issuance changes total supply.
- Concurrent funding and settlement cannot overspend wallets or duplicate payouts; cancellation follows the agreed refund policy.
- Cosmetic identity cannot authorize a task action.
- The legacy importer is read-only, repeatable, provenance-preserving, and reports malformed or incomplete source data.
- The default UI is plain and usable; Tavern mode is optional.
- Focused automated tests cover the domain invariants above.

## Exclusions from the first prototype

- Production hosting, SSO, enterprise authorization, and multi-tenant administration.
- Kubernetes, distributed databases, queues, or microservices.
- Automatic JIRA mutation, pull-request approval, or merge.
- Editing old Hackwatson packets or maintaining permanent two-way synchronization.
- A generalized workflow designer or broad plugin framework.

## Decisions requiring Steve's approval

1. Repository visibility: create `steve-bassoli/handoffs` as **private**.
2. Prototype authority: make SQLite authoritative in the new app; use Git only for source/version control and legacy import evidence.
3. Initial stack: FastAPI plus browser-native JavaScript, with no Node framework or build step.
4. Cutover policy: leave Hackwatson unchanged and perform a read-only, one-way import after the new lifecycle works.
5. Scope order: build the Gold economy and bounty lifecycle first; add Tavern presentation second; defer JIRA, Outlook, quota, and automated PR creation. PR delivery evidence and verification belong in the core bounty lifecycle.
6. Resolve the economic decisions above before implementing issuance and settlement policy.

Approval of this plan authorizes implementation only after Steve explicitly says to proceed. Requested changes should be incorporated into this plan before code is added.
