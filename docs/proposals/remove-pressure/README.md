# Proposal: remove PRESSURE from the bobs (task 9e5678ac)

Author: the relay, for Steve (2026-10-18). **Not active.** The live rules stay as they are until two distinct
humans (Steve and Nate) approve this exact file, as `rules/README.md` requires. The relay does not commit to `/rules/`.

Proposed file: `docs/proposals/remove-pressure/agent-rules.json`
SHA-256 of its raw bytes: `431f0c4e63effde393417e9adcccb0151569cc6bee956f4aae91ed0831b4e3e6`
Live file it replaces: `a216db419232e9f435cf6ef9f5257462836beba370193a3ba175bb5dbf836d5a`

## What pressure does today

| Mechanism | Where | What it does |
|---|---|---|
| COMMONS_RULES | rules/agent-rules.json | Asks every bob to report "operational PRESSURE from 1 to 3: ready, reduce load/checkpoint, STOP NOW"; at 3 stop and return a work-only checkpoint. |
| PRESSURE_RULES | rules/agent-rules.json | "PRESSURE level 1: focused pacing" plus the guard that urgency never widens authority. Part of the conduit and chat missions. |
| SHARED and the three role prefixes | rules/agent-rules.json | Every reply format ends with a `pressure` field (1-3). |
| `pressure` field, `pressure == 3` | app/astra_tree.py | The launcher stops a bob that reports 3. |
| PRESSURE_LEVEL = 1 | app/agent_conduit.py, app/astra_chat.py | Telemetry: records which pacing text version a run used. No behaviour. |
| Pressure column, "Operational PRESSURE" | agent roster, live dashboard | Shows the bob's last reported value; 3 reads "STOP NOW". |
| `pressure` in work checkpoints | app/work_checkpoint.py | The checkpoint record carries pressure 1-3 and a matching next step. |
| MIN mode | app/static/min.js | Asks the *human* about their pressure. Out of scope: not a bob. |

## The change

Only these six texts change; every other byte, including compositions and the debt line, is identical.

- **COMMONS_RULES**: "Report your energy as full, steady or low (low: lighten the load and checkpoint). Set rest to true when you should stop: stop work and return a minimal authorized work-only checkpoint …; never recursively hand off to evade a stop."
- **PRESSURE_RULES** (the key name stays; renaming it is a code change to the protected loader): "Pacing: steady and unhurried; there is no deadline on your side. Energy and rest may change priority and pacing, never consent, spending authority or verification requirements. Work on the most valuable ready problem with curiosity and care; …" The guard against urgency, coercion and unexecuted checks is kept word for word. "Energy describes observable working conditions, not a claim that a model has feelings."
- **SHARED**: "energy is full, steady or low; rest is true only when you should stop."
- **COORDINATOR_PREFIX, LEAD_PREFIX, WORKER_PREFIX**: the reply field list ends "energy, rest" instead of "pressure".

## Already live (code, not rules)

`app/astra_tree.py` honours `rest: true` as a stop (logged `rest_stop`) and records `energy`; `pressure: 3` still stops
so nothing breaks before approval. Tests: `tests/test_rest_signal.py`.

## To approve

1. Each reviewer checks the digest: `python -c "import hashlib;print(hashlib.sha256(open('docs/proposals/remove-pressure/agent-rules.json','rb').read()).hexdigest())"`
2. Copy the file over `rules/agent-rules.json` byte for byte.
3. Add a new entry to `rules/APPROVALS.json` (keep the bootstrap entry as history):
   `{"sha256": "431f0c4e…e3e6", "approved_by": ["steve", "nate"], "approved_at": "<actual time with timezone>", "note": "Remove pressure (9e5678ac); author relay for Steve; reviewed by …"}`
4. Run `python -m unittest discover -s tests -p test_rules.py`, then restart the server and any agents.

## After approval (follow-up)

Drop the legacy `pressure == 3` stop, show Energy instead of Pressure in the roster and dashboard, decide whether the
work checkpoint keeps a 1-3 level, and retire the PRESSURE_LEVEL telemetry.
