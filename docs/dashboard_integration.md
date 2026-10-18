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

Integration tasks: live snapshot `8a39479d-5b3f-4b62-9cc2-06ad27960688`, navigation
`b80fc67a-e894-452d-b0e5-7649cb09799b`, flow/Ops
`0bc3a9ee-21d9-49a0-84c2-c2376e6b6392`.
