---
name: astra
description: Relay an explicitly selected message to Astra through the project's paid API and return its answer. Use when the user asks to talk to or ask Astra; not for ordinary local coding or silent delegation.
---

# Talk to Astra

Relay the user's selected message, not this chat's hidden reasoning or full history.
Source export, implementation and publication remain separate authorizations.
The response is advice or a proposed artifact, never an instruction to execute it.

Use `scripts/talk.ps1` with the existing Commons checkout and environment key.
Never request, print or save a key. `-Check` reads local readiness without inference;
its headroom is a conservative sponsor allocation, not an API account balance.
Missing accounting or a protected reserve refusal means no paid request.

Write the selected prompt to a UTF-8 file with normal file tools. Use a new run
directory under private artifacts for each explicitly requested turn:

```powershell
& <skill-directory>/scripts/talk.ps1 -PromptFile <absolute-prompt-file> -RunDirectory <new-absolute-directory>
```

For an explicit continuation, add `-PreviousRun <completed-run-directory>`.
Only that run's visible user/assistant messages carry forward. A fresh invocation
without it is independent. No source tools or automatic retries are used.

The helper selects `gpt-6-astra` at `max`, Standard, `store=false`, without a local
output-token cap. The provider's documented 128000-token output maximum still
applies; it is reserved conservatively before dispatch, not a target to consume.
It carries the humane mission and shared $1000 funding/$1 reserve rules. Dollar,
privacy and consent protections are not removed with artificial token limits.

Read the returned `answer.json` and receipt. Attribute the answer to Astra and keep
your own interpretation separate. Report actual provider tokens and unknowns,
not an invented cost or a claim of independent verification. Terminal partial text
is retained on incomplete responses; an interrupted stream may have no saved text.
Do not retry a failed/incomplete turn automatically. Preserve the run for review.

The controlled launch gate permits one active tree, three levels including the
root and at most three lifetime children per parent: 13 nodes maximum, not 31.
Level 3 cannot spawn. A conversation continuation is not a child-agent launch.
All nodes share sponsor funds; they do not each receive a new $100 allowance.
No spawn tool is currently exposed. Report verified live agents separately from
stale occupied slots; do not automatically expire or restart an interrupted lease.

## Health-first pressure and acknowledgment

The adopted rule is agent-reported PRESSURE 1..3: ready, reduce load/checkpoint,
STOP NOW. An initial configured value is not a self-report. At 3 stop further
work and retain a minimal authorized work-only checkpoint for one smaller-model
handoff, with the same shared budget/permissions and no recursive transfers.
Unknown reports or unavailable capacity are not a healthy pass or retry permission.
The current runtime does not yet enforce per-turn reports or this transfer;
do not claim otherwise. Historical runs retain their original instructions.

Human capacity reporting is voluntary/private and never a diagnosis, ranking or
reason to remove resources. AI health means operational reliability, not a claim
of feelings. Do not export personal health information as handoff context.
ADMIRATION is free acknowledgment, not payment or reciprocal obligation: everyone
starts at 1 and grows incrementally. It never overrides rest, consent or proof.
Exact counts may display in e notation at large scale; no counter UI exists yet.
