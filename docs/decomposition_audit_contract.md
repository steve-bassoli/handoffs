# Decomposition audit contract: audit-v1-r1

Status: bob-4 ACK; current-round bob-2 and bob-3 ACKs received.
The coordinator explicitly reconciled all three ACKs for this retry.
Agreement is not artifact conformance, successful tests, application or acceptance.
The accompanying JSON fixture is synthetic, not live audit evidence.
This document and tests/fixtures/decomposition_audit_v1.json are canonical
for this proposed batch; do not substitute worker-local schema variants.

## Payload

All keys are required; no fixture wrapper or per-record level fields.

| Key | Type and meaning |
| --- | --- |
| version | integer 1 |
| source | exact string `Service.hierarchy_violations` |
| checked_at | caller-supplied string |
| scope | caller-supplied display string |
| status | `findings`, `checked_empty`, or `unavailable` |
| violations | array of `{ticket_id: string, message: string}`, or null |
| error | null, or exact string `Audit unavailable` |
| limitations | array of strings |

`findings` requires a nonempty violations array and error=null.
`checked_empty` requires violations=[] and error=null.
`unavailable` requires violations=null and error=`Audit unavailable`.
Failure must never become a clean empty result. Do not expose exception details.
The producer sorts by ticket_id then message and collapses exact duplicates.
The renderer preserves supplied record order rather than normalizing evidence.
The required limitation is exactly:
`Service.detail defaults missing complexity to HIGH.`
Additional limitations may be included without removing that statement.
Timestamps are supplied evidence labels, not independently verified freshness.

## Read-only scope and relay hooks

The producer uses an explicitly authorized injected reader of
`Service.hierarchy_violations`; it adds no endpoint, database setup, writes,
repairs, retries, event mutations, operation mutations or Gold mutations.
Scope is a display label, not a filter or authorization mechanism.
The existing audit reportedly scans all parents: the relay must authorize that
reader's actual disclosure scope, not infer authorization from a scope label.
Unavailable results retain the same source, checked_at, scope and limitations.

The renderer exposes `window.renderDecompositionAudit({audit,onNavigate})`.
It renders supplied evidence only, with safe textContent, visible ticket IDs,
keyboard-operable navigation and no network requests or automatic mounting.
Empty results say `No violations reported`, never `Verified correct`.
Navigation is an optional callback, not permission to mutate a ticket.
The relay owns later import, mounting, reader authorization and endpoint decisions.
No integration is applied by these files; human acceptance remains unresolved.

## Boundary evidence and limits

HIGH splits into more than one HIGH or more than one MEDIUM, never a mix.
MEDIUM splits into more than one LOW. LOW never splits.
Behavioral tests propose two/four-child positives and singleton, mixed,
wrong-level and LOW-parent negatives through both validation and spawn APIs.
Rejected spawns compare complete bounties/events snapshots; a late invalid child
also checks rollback. These are proposed checks, not recorded test successes.

The prior AST guard recognizes only literal first-argument SQL calls to an
attribute named exec_driver_sql, with unquoted INSERT INTO bounties column
lists and an exact case-insensitive parent_id column token. SQL case and
whitespace variants are recognized; similarly named columns are not parent_id.
It does not broaden parsing to quoted identifiers, schemas, alternate INSERT
syntax, UPDATE, dynamic SQL, aliases, helpers or indirect write paths.
Those paths are outside this guard's proof, not established safe.

Every recognized call is first discovered through complete ast.walk traversal.
A separate bounded lexical pass classifies supported placements. Reconciliation
uses AST call identity, not line numbers: two calls on one line remain two sites.
Recognized calls missed by lexical classification become explicit <unhandled>
sites and fail closed. In particular, exception-handler bodies are discovered
but deliberately not lexically classified. No unsupported placement disappears.
Duplicate lexical accounting is an assertion failure.
The prior guard reviewed only app/spawn.py:spawn_children and required discovery.
Unknown or unhandled sites block integration pending review; do not whitelist
an unknown site merely to make the suite pass.

An earlier standalone named validator call is only lexical evidence. It is not
proof of control-flow dominance, valid arguments, validator binding, transaction
correctness or enforcement on every runtime path. Nested scope and unusual
expression placements likewise require human review; this is not a general
Python control-flow or SQL security analysis.
Mutants must retain before/after/comment checks, exception-handler discovery
and same-line per-call accounting checks. Any recognized helper path needs
explicit bounded implementation evidence and mutant coverage, not an exemption.
Existing-source defects must be reported, not repaired outside file ownership.

## Retry blocker and review status

The historical failure identified app/ai.py:661, owner confirm, guarded=False,
as an unreviewed direct child-write site. That classification does not establish
whether runtime validation actually occurs through a helper.
Complete pinned AI.confirm and its relevant pre-write validation context are
unavailable on the supplied shelf. No confirm exemption or guard repair is
proposed. Boundary work remains blocked pending that evidence; do not skip,
xfail or weaken the guard to obtain green tests.

## Relay verification

Run pytest for tests/test_decomposition_boundaries.py,
tests/test_decomposition_audit.py and tests/test_decomposition_audit_view.py
only after resolving and proposing the boundary repair.
Verify producer and renderer use the canonical fixture and required caveat.
Review actual discovered sites and any blockers before integration.
Tests require repository dependencies and Node for renderer checks; none were
executed by this worker. Preserve authorization and unavailable semantics when
choosing integration hooks. No live database audit is authorized by this contract.
