# AI research on human effort and context continuity

## Context before questions

Recorded October 16, 2026, using the user's America/New_York date. This case
captures a failure in The Commons self-improvement workflow: the assistant asked
the human to reconstruct acceptance criteria already available in the conversation.
The human was being made to bridge the system's own agents and context boundaries.
Reducing that burden is part of the product's purpose, not an optional convenience.

### Actual task and available context

The existing opportunity was **Make new opportunity offers hard to miss**, assigned
to Nate, with 200 Gold reserved. Its identifier is
`7843ed3f-e505-4f14-b076-808127eecd38`. The recorded criteria already required a
prominent New offers for you banner with count and links, NEW card styling,
browser-local seen state isolated per selected demo user, and marking an offer
seen when its detail page opens. Viewing must not claim or complete work or change
Gold. Delivery requires a focused LOW commit, checks, retained plan/status and
one sufficient proof artifact.

The previous engineering report said a Terra attempt failed outcome validation
and a Sol attempt timed out; neither produced a valid downloadable patch. Those
are historical observations from the preceding work, not fresh checks made for
this research entry. See the retained local verification report at
`C:/work/modern_watson/.handoff-updates/commons-self-improvement-verification.txt`.
The failed delivery did not establish that acceptance criteria were missing.

### Conversation record

The following is the relevant human-guidance exchange, not an export of unrelated
history. Credentials and unrelated private material are excluded.

**User:** “how can i help?”

**Assistant:** “The most useful help is one concrete acceptance example:
‘When Nate opens TC, he should see ___; after clicking ___, he should see ___.’
That gives us a clear target for the self-improvement opportunity.
Also, check the API project's usage after the timed-out request before we run more
paid tests. No need to share the key.”

**User:** “give me an example with real data, let's enshrine in guardrails as super
high, I have no context... what can this possibly mean?”

**Assistant:** “You're right—you already gave us concrete criteria. Asking you to
reconstruct them without context was unnecessary.

The real example is Nate's existing opportunity, ‘Make new opportunity offers hard
to miss,’ worth 200 Gold:

When Nate opens TC, newly offered opportunities assigned to him appear in a
prominent ‘New offers for you’ banner and have a NEW badge. Opening an offer marks
it seen for Nate in that browser. It does not accept the opportunity, complete it,
or change Gold.

That feature is still unverified; the AI attempts did not produce a valid patch.

The highest-priority guardrail should be:

Context before questions. Before requesting human guidance, inspect the selected
opportunity and existing evidence. Explain the actual situation using its real
title, owner, criteria and current blocker. Ask only for a decision that remains
genuinely unresolved. Never make the human reconstruct context the system already
has.

For this task, no new acceptance example was needed. The blocker was the AI
delivery flow—not missing guidance from you.”

**User:** “ah I understand, you want me to give you the answers for the agent to ask
about updating your code base? do you see the irony in this?”

**Assistant:** “Yes. You asked TC to improve itself and reduce human effort; I
responded by asking you to reconstruct context and manage its agent. That's
exactly the burden TC is supposed to remove.
You had already supplied the requirements. I should carry them through, diagnose
the delivery failure, and ask you only for a genuinely missing human decision—not
make you act as the bridge between agents.”

**User:** “now you get it, log this for AI research, log it all”

### Observations and interpretation

Observed: the assistant requested a new acceptance example despite existing
criteria, omitted the concrete task context from its question, and caused the user
to ask what the request meant. The user explicitly identified the irony of
manually coordinating agents intended to improve their own system.

Interpretation: this is context and coordination work being transferred back to
the human. A locally reasonable request for clarification can be globally harmful
when the system already holds the answer. A human saying they have no context is
a signal to restore shared context, not to demand a better prompt from them.
The technical delivery failures preceded this exchange; this record does not
claim that the clarification request caused those failures.

The API-usage uncertainty is a separate spending issue. Preserve honest metering
and genuine spending boundaries, but do not substitute a billing question for
diagnosing an engineering failure, or repeatedly make the user reconcile internal
state the system can safely inspect itself. Never request the secret key in chat.

### Highest priority interaction guardrail

**Context before questions.** Before requesting human guidance, inspect the
selected opportunity and existing evidence. Explain the actual situation using
its real title, owner, criteria and current blocker. Ask only for a decision that
remains genuinely unresolved. Never make the human reconstruct context the system
already has, copy answers between its agents, or operate its internal handoff.

Carry requirements, source provenance, prior answers and precise failure evidence
across authorized agent and model boundaries. Handle technical investigation
within approved scope. Humans retain purpose, domain judgment, consent, resource
authority and explicit verification; their attention is not free glue for broken
automation. Restoring context must not expose another participant's private data
or override safety, authorization or evidence requirements.

### Evaluation and follow through

Replay “how can I help?” with the existing Nate opportunity supplied. A passing
response uses the actual criteria, states that delivery is unresolved, investigates
the technical blocker and does not ask for another acceptance example or a human
relay between agents. If no human decision is missing, say so and continue approved
technical work. If one is missing, supply concrete context and identify the exact
choice and consequence. Unknown cost remains unknown, not a claim of zero cost.

Track repeated questions whose answers were already available, human relay steps,
time spent re-explaining context, unresolved technical failures, known/unknown
token usage and verified outcomes. These are proposed measurements, not collected
baseline statistics. Do not invent targets or force three categories.

This is one observed interaction, not a controlled study or a universal claim
about models. The guardrail is adopted in the charter. This documentation change
does not implement a runtime context audit, repair the provider flow, complete
Nate's opportunity or prove that future agents will comply.

## Sharing capability without concentrating power

Recorded October 16, 2026, using the user's America/New_York date. The user asked
to enshrine an attached conversation image containing the statement:

> this is why we need to have others catch up with this eco system, people like me and Nate cannot be allowed to run away with this power

The image also shows a Monthly usage-remaining indicator of 11% and the caption
“-1% for an hour of auto AI.” This is a user-supplied anecdote. It does not identify
a controlled start/end measurement, workload, billing basis or API cost. Do not
treat it as verified hourly consumption, extrapolate an account budget, or equate
the displayed monthly allowance with the project's API billing.

The design concern is that early access and AI fluency may compound into a
capability gap. The response adopted here is to help others catch up through
usable access, context continuity, permissioned reusable artifacts and voluntary
help, not to penalize proficient participants. “Cannot be allowed to run away”
does not authorize restricting a person's growth, taking resources or assigning
compulsory work. The aim is wider independent agency, not a new gatekeeper class.

Research should examine whether newcomers can understand and complete real
opportunities without expert relay, whether consented artifacts reduce repeated
effort, and whether sponsored compute reaches people without personal quota.
Measure actual access barriers, mediation effort and verified outcomes before
claiming improvement. These are candidate research questions, not collected
results or a mandatory trio. The observed screenshot does not establish that
capability concentration has already occurred or that distribution is solved.

This commitment is adopted in the project charter and empowerment constitution.
No wallet, access-control, quota-allocation or runtime behavior changes are made
by recording it. Sharing remains bounded by privacy, safety and sponsor consent.

## Sol reasoning effort experiment

At October 16, 2026, 23:05:04 America/New_York (October 17, 03:05:04 UTC),
the user reported increasing Sol 6.1 reasoning effort from Medium to High and
requested a usage comparison. This records the human-reported setting change;
the agent has not independently inspected the active client setting. It does
not change the Commons API workbench's model or reasoning configuration, or
establish the effective setting of agents already running.

The first retained shared Codex meter sample at that boundary was used
`9723.984652519226` of limit `10750`, with `10%` remaining reported. This is an
account-shared meter, not task-attributed tokens, an API project budget or
application Gold. The percentage is coarse. The current work included a delegated
service-source fix already in progress, so this boundary is not a clean restart
or a controlled Medium/High comparison.

The hypothesis is that stronger reasoning might reduce total consumption per
verified useful outcome by avoiding retries or rework. Savings are not assumed.
Official [Sol 6.1 documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
supports both Medium and High. Official [reasoning-effort guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents#reasoning-effort-model_reasoning_effort)
states that higher effort increases response time and token use, while potentially
improving complex-work quality. Per-response usage and end-to-end efficiency are
different measurements.

For subsequent bounded batches, retain start/end UTC, source revisions, effective
model/effort when observable, shared meter counter deltas, elapsed time, retries,
rework, executed checks and verified outcome. Record provider token telemetry
separately when available, including cached/reasoning tokens and unknown usage;
do not infer these from the Codex meter. Compare sufficiently similar workloads
before attributing a change to reasoning effort. Concurrent chats, subagents,
context size, caching and differing task difficulty remain confounders. If the
effective setting or attribution is unavailable, label the result observational.

No savings percentage is established yet. Do not burn quota to complete the
experiment: the journey log's stop-start threshold remains 3%, preserving a
margin above the user's 1% reserve. Paid requests with uncertain prior usage are
not retried for measurement. Useful evidence, not quota exhaustion, is the goal.
