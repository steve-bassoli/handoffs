# Dashboard live contract v1 — retry verification

Proposal only: no routing, static integration or live writes are applied.
Canonical fixture: tests/fixtures/dashboard_live_v1.json, unchanged from SHA-256
251a54fd9910c8bb6c77d992cdec2db4b4614d3842b9677d19075fbb1f2f87f9.
Current receipts: bob-2 and bob-3 explicitly ACKed that fixture and the original
contract SHA-256 037a4d7b7013a6ab60c1f36def8c59cbd84daf436785a3a7b589f78ced420795;
bob-4 ACKs the same shape/interfaces. Coordinator confirms all three current ACKs.
This document updates verification notes, not the agreed schema or interfaces.
Technical agreement is not human acceptance. No checks were executed here.

## Envelope and honesty
Exact top-level keys: schema_version, observed_at, sources, agents, mode, session.
schema_version is 1. observed_at is caller-supplied UTC observation time.
sources contains roster, mode, plan, board, summary, each exactly:
{status: available|missing|invalid|unavailable, observed_at, event_at: string|null}.
Observation time is not event time; filesystem mtime is never an event timestamp.
Browser received_at is local receipt time, neither source observation nor freshness.

Agent keys: id (unique nonempty string <=200), reported_activity (string <=80|null),
live_confirmed (boolean|null), interrupted_occupied_lease (boolean|null),
pressure (integer 1|2|3|null), source ('roster'), event_at (string|null).
Sort lexically by id; duplicate IDs invalidate the roster.
Reported activity does not establish live confirmation or an interrupted lease.
Only explicit authorized evidence may supply those booleans.
PRESSURE describes operational reliability, not personal health; 3 means STOP NOW.
mode: {value: manual|light|heavy|max|null, agents: nonnegative integer|null,
automated_writes: boolean|null, source: 'mode'}.
session: {id: string|null, plan: object|null, board: object|null, summary: object|null}.
Null means unknown/unsupported, not zero, false or an empty confirmed population.
Booleans are not numeric counts. Source availability is independent per source.
The synthetic fixture includes unfinished work, missing files, unavailable mode,
PRESSURE 3, unconfirmed activity, explicit interrupted-lease evidence and hostile text.

## Python and confined reading
build_snapshot(*, roster=None, mode=None, session=None, observed_at)
Roster input: {available:true,items:[{id,state,pressure,event_at?,live_confirmed?,
interrupted_occupied_lease?}]}; state supplies reported_activity only.
Raw mode supplies mode, agents, automated_writes. Unsupported values remain unknown.
Missing inputs are unavailable; malformed supplied structures are invalid.
Malformed source status, including [], must normalize to invalid, never raise TypeError.

read_session_metadata(session_id, *, base_dir, max_bytes=65536)
returns {id,sources:{plan,board,summary},plan,board,summary}.
Reader source records contain status/event_at; builder adds observed_at.
No selected session means null metadata and unavailable session sources.
Only selected-directory plan.json, board.jsonl and summary.json may be read.
No discovery, recursion, latest-session fallback, receipts or arbitrary paths.
Reject unsafe empty, absolute, traversal or separator-containing IDs with ValueError.
max_bytes is a nonboolean integer 1..65536; each file read is bounded to max_bytes+1.
Malformed, oversized, symlink/reparse or special sources report invalid.
Absent selected directory/files report missing independently; missing summary is normal.
Genuinely unsupported secure confinement reports unavailable, not a successful read.
Supported secure Windows reading must preserve the canonical available plan and missing
board/summary states. Do not capability-skip or weaken full-envelope equality.
A resolve-then-open check alone is not proof against replacement races.
Relay must review platform handle confinement and replacement-race behavior separately.

Plan input/output: {agents:[{name,level,parent}]}, copying those keys only.
Strings are bounded to 200; level string|integer|null, parent string|null.
Board is JSONL: nonblank records must be objects with bounded nonempty event.
Output: {event_count,last_event_at,pressure_stop_count}; count every valid record.
last_event_at and board source event_at use the LAST PHYSICAL EVENT's at_utc,
returning null if absent/unsupported there; never scan backward for an earlier time.
Only exact event='pressure_stop' increments pressure_stop_count, not unique agents.
Zero recognized stops is not proof nobody stopped.
Summary allowlist: elapsed_minutes (finite nonnegative number|null), requests
(nonnegative integer|null), upper_bound_cents_for_reported_usage (finite nonnegative
number|null), unknown_usage (boolean|null), stopped_agents (bounded identifiers).
Summary source event_at comes from at_utc. Numeric unknown_usage, including 0, is null.
Exclude messages, prose summaries, prompts, directives, secrets, wallet data,
personal health and arbitrary nested metadata. Adapters remain proposals, not proof
that production source schemas have these meanings.

## Browser hooks
window.createDashboard(root, options) returns register(slot,renderer), pause(),
resume(), destroy(). Slots live|flow|ops use data-dashboard-slot.
renderer(element,snapshot,viewState) immediately receives retained data or null.
viewState keys: stale, paused, authentication (booleans), error (string|null),
received_at (number|null). Registration must not require replacing stable controls.
Options: endpoint, headers, fetch, setTimeout, clearTimeout, now, document.
Explicit nonempty same-origin endpoint required; omitted/empty means no requests.
Identity comes from authorized injected headers, never a guessed X-Demo-User.
Use credentials:'same-origin', redirect:'error'; never display identity values.
Configured construction reads immediately; at most one request is in flight.
Foreground target 2500ms AFTER settlement; hidden minimum 10000ms.
Failures back off with a 60000ms ceiling. Invalid nested envelopes retain last-good
snapshot and mark stale/error. 401/403 latch authentication stop; resume cannot clear it.
Pause prevents scheduling. Destroy ignores late results.
Controls: data-dashboard-pause, data-dashboard-resume, data-dashboard-status.
Use textContent, semantic headings, stable keyboard controls and reduced motion.
Hostile fixture strings must appear literally in rendered output, not disappear
because a renderer threw. No spend, mode, launch or other mutation actions.
No transport abort/request timeout or automatic age-based stale policy is guaranteed;
an unresolved request occupies the single-flight slot. Receipt is not liveness proof.

## Proposed integration and verification matrix
Relay may propose one authenticated read-only /api/dashboard/live snapshot route,
using an explicitly authorized selected session and trusted base_dir, plus a static
page with authorized endpoint/headers injection. No wiring is included here.

| Criterion | Offline check |
| --- | --- |
| Synthetic honesty boundaries | canonical fixture and test_complete_envelope |
| Windows exact envelope | same full equality, no capability-based skip |
| Validation and bounded reads | test_reader_validation_and_bound |
| Selected-directory/file escape | test_symlink_confinement, two cases |
| Privacy and event-time semantics | test_metadata_allowlist_and_event_time |
| Malformed status and unknown evidence | test_malformed_status_and_unknowns |
| Browser rendering and identity | VM default renderers, literal hostile strings, injected headers |
| Single-flight, stale, hidden/backoff | VM deferred fetch, repeated resume, malformed response, timers |
| Authentication stop | VM 401 and 403 with attempted resume |

Unexecuted command: pytest -q tests/test_dashboard_live.py
Run on supported Windows and POSIX with all sibling proposals present.
Node is invoked by pytest using vm, fake DOM/fetch/timers; no live services.
Missing Node explicitly skips browser checks. Missing symlink privileges explicitly
skip only affected symlink cases; neither is a pass. The fake DOM is not a browser
security/accessibility proof. Timeout/subprocess failure fails the browser test.
Remaining checks: replacement races, instrumentation of actual byte-read ceilings,
full malformed matrix, destruction races, real browser focus/accessibility,
route authorization, production adapters and platform confinement implementation.
Human decisions: endpoint/auth binding, trusted root, supported platforms and
stale-age/timeout policy. Unknown usage retains its reservation; this dashboard
grants no spending or launch authority and never exports personal health details.
