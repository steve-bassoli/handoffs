# Mission control integration

The dashboard's read-only snapshot is `GET /api/dashboard/live`. An explicit
registered `X-Demo-User` is required; this uses the application's existing demo
identity, not production authentication. Reads do not grant Gold, mutate tasks,
start agents or make provider calls. The response is the v1 live envelope with
additional allowlisted integration context. Receipt time is not agent liveness.

`task` selects a service task. `session` selects only a registered roster session,
under the trusted `HANDOFFS_DASHBOARD_SESSIONS` directory (default: `astra-tree`
beside the task database). There is no latest-session fallback, recursive discovery,
or caller-supplied directory. Only plan, board and summary metadata are read through
the existing confined reader. The actual tree plan format is mapped to agent
name/level/parent; shelves, prompts, directives and final synthesis are excluded.
An unavailable source remains explicitly unavailable. Liveness and interrupted
lease counts remain unknown without independent evidence.

The main navigation includes Dashboard; task detail adds Open dashboard for this
task. `/dashboard?user=<selected-user>&task=<id>&session=<registered-session>`
boots the existing controller against the live snapshot route. User selection is
validated against registered demo users. A previously selected stored user may be
reused; missing or invalid identity never guesses Steve. Task/session selectors
recreate the controller, clear previous-context data and preserve read-only behavior.
The standalone static URL uses the same bootstrap. Back to Tasks returns to the app.

The same snapshot carries `flow` and `ops` projections. Task flow reads at most 101
rows and 50 eligible events per displayed task, exposing only titles, state,
complexity, current claimant, parent relationships and confirmed agent assignment.
Default flow shows 25 recent tasks; a selected hierarchy shows at most 100. Coverage
labels and truncation issues remain visible, and neither assignment history nor
reported activity establishes agent liveness.

Ops reads the sponsor ledger through SELECT-only bounded queries, grouping all
reservation amounts by recorded state. No private ledger notes are exported.
`unknown` retains its full recorded reservation but leaves allocatable headroom
unknown; `overrun` leaves all derived totals unknown. The existing `pending`,
`reported_upper` and `unknown_conservative` meanings remain intact. No provider
balance is inferred and session usage is never subtracted a second time.
Participant Gold reads the wallet account directly without invoking monthly
allocation. Selected-session usage, registered lease observations and Git HEAD
metadata are connected; Codex allowance is unavailable until an authorized source
adapter exists. Lease liveness counts remain unknown. Source identities are opaque
fingerprints; failed observations retain last-good data only for the same identity
in the same browser context and are visibly marked stale. Switching user/task/session
destroys that context. Polling starts no paid work and offers no mutation controls.

Graph controls remain stable when task data is unchanged and regain focus by task
identity when the graph changes. The Ops accounting link also retains keyboard focus
across refresh. Session reading retains the existing 64 KiB per-file bound: oversized
or malformed sources are visibly invalid rather than silently treated as complete.

Integration tasks: live snapshot `8a39479d-5b3f-4b62-9cc2-06ad27960688`, navigation
`b80fc67a-e894-452d-b0e5-7649cb09799b`, flow/Ops
`0bc3a9ee-21d9-49a0-84c2-c2376e6b6392`.
