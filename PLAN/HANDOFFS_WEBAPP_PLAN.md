# HANDOFFS Web Application Prototype Plan

## Status

Proposed for Steve's review. This repository contains planning only; implementation does not begin until Steve approves the decisions at the end of this document.

## Goal

Extract the HANDOFFS concept from `nate-viniconis/hackwatson` into an independently owned application at `steve-bassoli/handoffs`. Deliver a runnable web prototype for creating quests, assigning work, viewing a board, recording append-only status events, returning results, and showing player rewards.

## Prototype principles

- Prefer the smallest understandable stack over production architecture.
- Keep task truth, identity, and authorization separate from cosmetic game presentation.
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
- `reward_events`: idempotent gold and XP awards tied to proof.
- `gold_spend_events`: idempotent approved spending records.
- `capacity_readings`: optional time-bounded quota snapshots.
- `external_links`: source issue, pull request, repository, revision, and evidence fingerprints.

Task status is derived from ordered valid events rather than updated destructively. Cosmetic aliases and rewards never establish task ownership or permissions.

## Core prototype workflows

1. Create a targeted or open quest.
2. List open quests and a user's current tasks.
3. Preview one quest without claiming it.
4. Assign or claim an open quest.
5. Record working, blocked, or completed status with an immutable result.
6. Acknowledge and explicitly accept or reject returned evidence.
7. Award an idempotent reward only from accepted or otherwise verified proof.
8. Search task metadata and history.
9. Show a plain board by default, with Tavern presentation as an optional view.
10. Import legacy Hackwatson packets and events with provenance and validation warnings.

## Migration approach

### What moves

- Domain behavior encoded in the HANDOFFS skills and PowerShell helpers.
- SQLite profile, search, capacity, relationship, and reward behavior.
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
- Add focused tests for event ordering, immutable results, open assignment, and authorization boundaries.

Gate: Steve can run the app locally and the API proves the task lifecycle without legacy integration.

### Phase 2: useful web board

- Add plain open/current task views, task preview, task creation, status updates, and result entry.
- Add player profiles and optional Tavern presentation.
- Add rewards only after accepted or verified proof.

Gate: the end-to-end lifecycle works through the browser using only the new repository.

### Phase 3: legacy extraction

- Implement the read-only Hackwatson importer.
- Reconcile imported counts, event histories, results, relationships, profiles, and rewards.
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
- Rewards are idempotent and cannot be earned from selection, claiming, blocking, or unaccepted completion alone.
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
5. Scope order: build the plain task lifecycle first; add Tavern presentation second; defer JIRA, Outlook, quota, and PR automation.

Approval of this plan authorizes implementation only after Steve explicitly says to proceed. Requested changes should be incorporated into this plan before code is added.
