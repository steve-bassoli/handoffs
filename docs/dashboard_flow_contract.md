# Dashboard flow v1-r2 — proposed adapter contract

## Status and authority

Bob-4 ACKs v1-r2 without changes. Output `version` remains the integer 1.
Actual bob-2 and bob-3 ACKs have not reached this worker; do not infer agreement.
These are new-file proposals, not applied changes, live observations or acceptance.
The synthetic fixture is the data-shape authority for this batch, alongside the
explicit rules below. It is not a captured production response.

## Python boundary

`build_dashboard_flow(lineage, details, *, current_id=None, observed_at=None,
max_tickets=100, max_activity=100)` is pure and must not mutate either input.
`lineage` is `{root_id?, items:[{id,parent_id?,title?,status?}]}`.
`details` maps ticket IDs to `{events:[{kind,created_at?,actor?,data?}]}`.
These normalized adapter inputs do not establish live endpoint envelopes.
Reject malformed top-level inputs instead of silently reporting an empty system.
Caps accept actual integers, not bool, and clamp to 0..100; otherwise TypeError.

Exact output keys:

- Envelope: version, observed_at, current_id, tickets, activity, coverage, issues.
- Ticket: id, parent_id, parent_known, title, status, assigned_agent,
  assignment_source, detail_available.
- Activity: ticket_id, kind, event_time, source_index.
- Coverage: tickets_supplied, tickets_shown, activity_eligible, activity_shown,
  tickets_truncated, activity_truncated, details_missing.

`observed_at` and `current_id` are caller-supplied string-or-null metadata.
Never infer them from events or root_id. Never replace event time with observation
 time. `version` is 1; coverage counts are integers and flags are booleans.
Missing assignment fields and unavailable parent/time values are null, not omitted.

## Identity, topology and assignment

Nonempty IDs are preserved verbatim; whitespace-only IDs are invalid.
First valid lineage occurrence wins and retains source order.
Duplicates add duplicate_id; differing parent/title/status add conflicting_evidence.
An explicit null parent is known root evidence. Missing or invalid parent is
`parent_id:null,parent_known:false`; valid string parents are known and preserved.
Invalid non-null parents add invalid_parent. Preserve orphan and cycle links;
do not invent roots, repair topology or confuse a cap-hidden parent with evidence
that a ticket was created as a root.

Only valid child `followup_confirmed.data.assigned_agent` assigns an agent.
Neither actor, raw detail assignments nor parent plural `followups_confirmed`
assigns a child. Last valid supplied confirmation wins source order with
assignment_source `followup_confirmed`; absent confirmation gives null/null.
Distinct agents add conflicting_assignment. This is conflicting source evidence,
not a resolved current assignment, purchased authority or human acceptance.
Preserve valid status, agent identifiers and timestamps verbatim. Only title may
be visibly clipped to 240 characters. Invalid title/status use `Unknown`.

## Activity, privacy and local bounds

Allowed kinds: posted, followup_confirmed, package_attached, dependencies_set,
taken, reopened, ai_started, ai_failed. This adapter allowlist does not prove
that every kind occurs live. Unsupported kinds are filtered; malformed kinds,
events or event collections must not crash processing.
Only returned tickets contribute activity, in lineage order then event order.
source_index is the original zero-based index inside that ticket's events.
event_time is a nonempty created_at string or null. Do not sort mixed timestamps.
Never export actor, arbitrary data, messages, notes or raw detail objects.

tickets_supplied counts unique valid lineage IDs before capping.
tickets_shown and details_missing concern returned tickets only.
activity_eligible counts allowlisted supplied events for shown tickets before its
cap; activity_shown is after the cap. Local cap flags do not establish upstream
completeness. Always label upstream completeness unknown in the presentation.
Any additional visual cap requires its own explicit notice.

Issues are deduplicated fixed strings only:
`duplicate_id invalid_id orphan_parent cycle missing_detail tickets_truncated
activity_truncated invalid_parent conflicting_evidence conflicting_assignment
invalid_events`.

## Browser and navigation boundary

`window.renderDashboardFlow(model,{element,onNavigate,renderFlow}={})` returns
one DOM root exposing `update(nextModel)`, which retains and returns that root.
Default element creation uses document.createElement; `element(tag,text,className)`
is the optional relay-supplied helper. Labels always use textContent, even with a
helper. No innerHTML, URLs, network, timers, animation or live announcements.
Root aria-live is `off`. Keep IDs and literal `You are here` visible.

Keep a semantic ticket list even when a graph succeeds. Buttons exist only with
an onNavigate callback; pass ticket ID only, never a guessed route. Preserve
focused retained ticket buttons and do not force focus elsewhere. Identical
activity updates retain the activity list rather than rebuilding it.

The optional adapter is called `renderFlow(model,{element,onNavigate})` and must
return a DOM node. Missing, throwing or invalid adapters leave the list usable.
Only a separately verified relay adapter may wrap window.renderTicketFlow;
its native signature is unverified here. Retain existing ticket-flow assets.
Show missing evidence, local truncation and upstream uncertainty explicitly.

## Evidence and checks

Parent v1-r2 messages provide this proposed agreement. Pinned example_py_test
SHA-256 98512e06ddceddd66f55bd90c2db20569d3bf4d44371291963866042b13371b2
verifies true child parent_id and child followup_confirmed.data.assigned_agent
separately from the parent's plural followups_confirmed event.
This is source evidence, not a live endpoint or renderer compatibility check.

Relay check: `pytest -q tests/test_dashboard_flow.py` after all proposals are
applied. Node absent produces an explicit skip, not a browser pass. The VM uses
a deliberately small fake DOM; real-browser keyboard/accessibility review and
legacy adapter integration remain separate checks. No checks were run here.
No existing files, application wiring, database writes or public publication are
authorized by these artifacts. Human integration and acceptance remain pending.
