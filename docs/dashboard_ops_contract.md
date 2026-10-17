# dashboard_ops_v1/R2 — canonical candidate

## Review boundary

The parent R2 accounting message was clipped mid-sentence. The visible interface
below is preserved; the accounting failure and stale-retention interpretations
are candidates requiring the missing tail and renewed teammate ACKs. This is not
an assertion of completed agreement, deployed integration, tests or acceptance.
ACK record: bob-4 accepts the visible interface; no full-contract ACK from
bob-2 or bob-3 has been received. Do not silently change this revision.

## Public interfaces

- `normalize_ops(raw, previous=None) -> snapshot`: pure; no I/O or input mutation.
- `read_ledger(path, adapter=None, limit=1000) -> source_result`.
- `read_git(repo, runner=subprocess.run) -> source_result`.
- `window.renderDashboardOps(snapshot, helpers) -> DOM root`.
- `helpers.element(tag, text, className)` creates elements; variable text uses
  `textContent`, never `innerHTML`.

A source result is `{status: 'ok'|'unavailable', data: object|null,
error_code: string|null}`. It is not a full source envelope. Integration owns
source identity and observation metadata; no refresh or assembly export exists.

## Snapshot

Root keys: `version:1`, `policy`, `sources`, `tests`.
Policy is `{protected_cents:100, sponsor_guard_cents:199800,
tests_gated_before_commit:true}`. Tests is always
`{status:'not_recorded', provenance:null}`; incoming proof claims cannot override it.

Sources are exactly `ledger`, `session_usage`, `wallet`, `codex`, `leases`, `git`.
Each envelope has `status:'ok'|'stale'|'unavailable'`, nullable string `source_id`,
`observed_at`, `last_attempt_at`, `error_code`, and `data:object|null`.
Raw observations use ok/unavailable. Stale is produced from previous snapshots.
Missing sources become unavailable, not observed zeroes. Do not export arbitrary
extra raw fields. Error codes are sanitized categories, not exception text.
Source IDs are opaque non-secret identities, never private filesystem paths.
Observation timestamps are supplied evidence, not invented refresh timestamps.

### Source data

- ledger raw: `{ceiling_cents:int|null, baseline_cents:int|null,
  reservations_complete:boolean, holds:[{id:string,
  state:'pending'|'reported_upper'|'unknown_conservative', held_cents:int}],
  provenance:string|null}`.
- ledger normalized adds `held_upper_bound_cents`, `source_headroom_cents`,
  `guarded_headroom_cents`, each integer or null.
- session_usage: `{reported_upper_cents:int|null}`.
- wallet: `{gold:number|null}`; no invented initial participant balance.
- codex: `{amount:number|null, unit:string|null}`.
- leases: `{records:[{id:string,state:string,evidence:string|null}],
  verified_live_count:int|null, interrupted_occupied_count:int|null}`.
  Non-null counts require authorized evidence. Admission, PID existence or roster
  membership does not establish liveness. Interrupted occupied leases stay separate.
- git: `{commit:null|{hash:string, committed_at:string}}`.

## Accounting and display

Cents are nonnegative integers, excluding booleans and floats, no larger than
9007199254740991. Hold IDs are nonempty and unique. Completeness attests that all
relevant holds are present and baseline and reservations are disjoint.

All three hold states retain their full held amounts. For complete valid data:

```
held_upper_bound_cents = sum(held_cents)
source_headroom_cents = ceiling_cents - baseline_cents - held_upper_bound_cents
guarded_headroom_cents = min(ceiling_cents, 199800) - baseline_cents - held_upper_bound_cents
```

Do not clamp negative results or subtract session usage again. The candidate
fixture makes all three derived amounts null on invalid, missing, incomplete or
ambiguous accounting. Confirm this interpretation with the restored R2 tail.
Derived totals must also remain safely representable across Python/JavaScript;
aggregate-overflow treatment needs an explicit follow-up check.

Display cents as dollars divided by 100 with two decimal places, preserving sign;
null means unknown, not $0.00. Display the protected 100 cents separately. The
sponsor commitment is $1999, of which at most $1998 may be allocated. Source
headroom above that cap is not additional spending permission. Reservations and
reported usage are upper bounds, not billed costs or verified balances.

Participant Gold and Codex allowance remain independent resources, not sponsor
spending authority. Game Credits are not real dollars or API authorization.
ADMIRATION and GROWTH do not purchase authority. Do not infer participant values.

## Retention candidate

On failed observation, retain previous data only for the same nonempty source_id.
Mark it stale, preserve its original observed_at, and use the failed attempt's
last_attempt_at/error_code. Changed or missing identity must not inherit another
source's data. Stale values are not fresh observations and do not establish that
funds are currently available. This interpretation requires renewed ACKs.

## Read-only readers

SQLite opens an existing path using mode=ro; missing files are never created.
No adapter means unavailable. Adapter receives `query(sql, parameters=())` for
bounded SELECT-only reads and returns the raw ledger shape. Swallowed query
failures, incomplete/truncated reads and missing reservations_complete=true
cannot produce success. No database writes, public disclosure or live mutations
are authorized by this proposal.

Git uses exactly `['git','--no-pager','log','-1','--format=%H%x09%cI',
'--no-decorate']`, shell=False, timeout=2, through the injected runner. Validate
bounded hash/time output. Success contains only commit hash/time; failures have
null data. No subjects, bodies, source contents or automatic retry.

## Verification and operations

A commit proves neither passing tests nor human acceptance. Label test gating as
policy, not run evidence. Tests remain 'not recorded' until authorized integration
introduces independently grounded evidence under a reviewed contract revision.

Unknown chargeable usage retains its reservation. Never automatically retry an
operation with unknown chargeable usage. A git or ledger read failure is not a
license to retry a chargeable operation or release its hold. Keys stay private.
Use https://platform.openai.com/usage or authorized Costs API accounting;
https://platform.openai.com/api-keys is not a balance page.

Fixture values are synthetic and contain no live financial or personal data.
The fixture base deep-merges with each case's raw override; lists replace lists.
previous_from references an earlier normalized case. Expected values are selected
assertions, not permission to omit other required snapshot fields.

Relay checks: run `pytest -q tests/test_dashboard_ops.py`; Node absence must be
reported as a skip and missing JS coverage. Review DOM harness compatibility,
aggregate overflow, valid-read truncation and failure sanitization separately.
No checks described here have been executed by this worker.
