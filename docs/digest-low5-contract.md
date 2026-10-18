# Decision digest LOW-5 — implementation checkpoint

Status: proposed contract, not an implemented endpoint. Do not expose decision controls until implementation and verification pass.

## Observed evidence

- `app/digest.py` discovers pending signoffs, intake refusals and claimant-eligible closure candidates. It does not execute decisions.
- Signoff approve/reject updates decision metadata, not protected downstream state. Its existing endpoint permits prototype-auto; the digest endpoint must not inherit that bypass.
- `Service.execute` checks and caches actor/key/fingerprint results and commits the operation result with domain mutations. Its default non-AI path also grants monthly Gold: a digest action must explicitly bypass that unrelated allocation.
- `Service.event` adds resolved principal metadata and server time. The available shelf does not establish whether a signoff ID is a valid events.task_id.
- Intake override checks signed-in-human identity, note, unclaimed open/blocked state and refusal matching current canonical text. It recomputes the current hash; it does not compare a supplied revision field itself.
- Human acceptance permits demo/prototype paths in other entry points. Digest authorization must be stricter and run before cache lookup.
- Recommendations.current and build_digest open their own read connections. Calling them unchanged inside a decision transaction does not establish a single authoritative transaction snapshot.
- The proof implementation and database schema are not available here. The supplied wrapper signatures establish how to request review/completion, not how to establish current proof identity or its complete side-effect contract.

## Required API

POST /api/v1/digest/decide

Body: {kind, id, revision, decision: yes|no|change, note, recommendation_id: string|null}. Reject extra fields. Require a nonblank bounded note, exact IDs and an Idempotency-Key. Bound signoff notes to the existing 2000-character contract; task notes may use the existing 4000-character limit.

Require principal=human, matching user_id/actor and nonempty principal_id before consulting the operation cache. Reject demo-header, relay, codex and agent even with the prototype door off. Never accept actor, server time, principal identity or advice content from the body.

Exclude policy decisions and signoffs whose action is rule_texts. Existing executors retain their independent authorization requirements.

## Durable source semantics

| Source | Yes | No | Change |
|---|---|---|---|
| signoff | Existing approve metadata, decision_mode=human; do not consume approval | Existing reject metadata | Durable change-request event with note; retain pending signoff and display note |
| intake_veto | Existing human override, after exact submitted/current text-hash comparison | Durable intake_veto_upheld event with note and text hash; task state blocked; digest projection recognizes this resolution for that refusal | Durable task change-request event with note; preserve task state and waiting item |
| human_close | Require an authoritative current proof, record accepted human review, then complete through existing wrappers | Record rejected human proof review with note; preserve open work for rework, not completion | Durable task change-request event with note; preserve source state |

For intake No, retain the refusal and upheld event in task history; suppression in the digest is only a projection of the blocked source outcome. Scope resolution to the specific screening event and text hash so a later screening can require a new decision. Keep its note visible in task detail.

For intake No, reuse the current-text, unclaimed and open/blocked eligibility gates before mutation. Never block already completed or claimed work merely because historical screening remains discoverable.

For human_close, reuse claimant, live-task, complexity, child, proof and acceptance gates. Do not fabricate proof, attach synthetic evidence or reuse do_close_human, which manufactures a profile and proof attachment. Missing current proof must return 409 with message 'no current proof'. Whether an independent reviewer may close work claimed by another human must follow authoritative existing proof rules, not a new inferred permission.

## Transaction and cache design

1. Add a distinct digest_decide Service action with strict human authorization before cache lookup. Include resolved principal_id in its internal fingerprinted payload to prevent another session sharing an actor from retrieving an earlier decision as its own.
2. Preserve the client key in the operation cache. Derive a stable, actor-scoped operation ID from actor plus key, or introduce an explicit stored ID after schema review. Bind that ID in the audit and response. Never report it as an existing schema field.
3. Exempt this action from grant_month. Do not perform model calls or background scheduling.
4. Under the existing serialized write transaction, derive source eligibility and revision using the same connection. Refactor digest discovery to support transaction-owned reads rather than wrapping nested independent connections.
5. Compare revision before mutation. On mismatch return 409 with current_revision. If the item is no longer eligible, return 409 with current_revision null and a reason rather than inventing a revision.
6. Read the public recommendation snapshot using the same connection. A nonnull recommendation_id must match the current recommendation for exactly kind/id/revision; mismatch returns 409. Null means the user submitted without advice: record a null snapshot, never silently substitute newly arrived advice. Previously displayed but superseded advice requires refresh under this contract.
7. Apply the source-specific domain operation and append exactly one digest_decided containing kind, id, revision, decision, note, recommendation_id, recommendation_snapshot, decided_by, principal_id, operation_id and server decided_at. Use the same transaction for source events, signoff metadata, audit and cached result.
8. Resolve signoff audit storage before coding: if events.task_id references tasks, use a separately migrated digest audit ledger rather than fake task IDs or fabricated tasks. Include the source-specific change note in subsequent digest reads.
9. Cache only committed success. Exact retries return the original result and emit no new events. Changed payload/principal binding with the same key returns conflict. Unknown request outcomes retain the original key; never automatically retry with a new key.

## Verification matrix for tests/test_digest_decide.py

Use real database transactions and authoritative proof fixtures for integration tests; mocks alone cannot verify currentness or rollback.

- All nine source/decision combinations, domain state and note visibility.
- No credentials, demo header, relay, agent and codex; repeat with door off/prototype-auto active and with an already cached key. Assert zero mutations and audit rows.
- Protected rule_texts and unsupported policy kinds rejected.
- Missing/blank key and note; extra fields; invalid kind/decision/revision.
- Stale signoff hash, changed task text, changed closure event sequence and changed children return 409/current_revision; ineligible sources return explicit conflict.
- Missing, obsolete and current proofs; claimant violations; proof acceptance/completion failures. Verify the required missing-proof response.
- Available/unavailable advice, explicit null, wrong item/revision, superseded advice, concurrent replacement; audit excludes private requester context and raw provenance.
- Exact duplicate returns byte-equivalent decision data with one audit; changed payload/key reuse conflicts; concurrent duplicates commit once.
- Inject failures after domain mutation, on digest audit insertion and on operation-cache insertion. Each must roll back domain mutation, source events, audit and cache. For closure, completion failure must also roll back accepted proof review.
- Intake No blocks the task durably, removes only the resolved refusal from digest and does not erase history. Later screening is rediscovered.
- Change remains pending with a visible note, and changes the closure revision where events define revision.
- Assert no monthly allocation, Gold transfer, publishing, mode change, signoff consumption or background AI invocation from any decision.

## Release gate

Apply proposals only after reviewing the proof-currentness API, proof completion side effects, database schema and signoff audit destination. Then implement the endpoint and test file, run focused and regression checks, and obtain explicit human review for foundation locks. This document is not acceptance, test evidence, a managed commit or permission to execute downstream actions.
