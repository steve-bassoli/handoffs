---
name: iterative-implementation
description: Plan and execute the smallest acceptance-criteria-bound implementation while retaining auditable plan and status artifacts. Use for delegated JIRA implementation or other multi-step code changes where scope must not expand beyond explicit acceptance criteria.
---

# Iterative Implementation

Implement exactly the supplied acceptance criteria and nothing else. Treat them
as both the required outcome and the scope ceiling.

For Watson modernization and HANDOFFS work, read the
[project charter](../../PROJECT_CHARTER.md). It defines Watson REST/MCP, Gremlins,
the audit trail and the single-proof completion contract. Do not treat target
capabilities as implemented or turn the charter into extra acceptance criteria
for unrelated work.

## Plan before editing

Read [references/implementation-steps-template.md](references/implementation-steps-template.md),
inspect only the source needed to resolve the criteria, and write an ordered
plan before changing source files. Every plan item must map to a verbatim
criterion or an unavoidable prerequisite. Exclude opportunistic cleanup,
refactors, hardening, error-path changes, abstractions, documentation, and tests
that do not provide the narrowest evidence for a criterion.

## Complexity gate

Use HIGH, MEDIUM, and LOW only; retired labels are invalid, not aliases.
Every HIGH has multiple HIGH children or multiple MEDIUM children, never a
mixture. HIGH descendants must eventually decompose to MEDIUM and LOW;
do not evade decomposition through an unbounded chain of HIGHs. Every MEDIUM
has multiple LOW children. A split has at least two meaningful children; never
force three. LOW is a leaf: no children. Only LOW is
executable. An implementation LOW owns one minimal managed commit; a
verification LOW produces auditable evidence, not a forced commit. A genuinely
LOW task can be a root.
Do not pad with fake tasks or relabel work to bypass decomposition. If a meaningful
split cannot be defined, reconsider the boundary or classification.
Ask only for genuinely missing information; do not execute the parent.

Consider alternatives only when a real design decision warrants them; never force
three. Choose the smallest grounded boundary. No universal count applies to
questions, choices, proofs or resources. This supersedes the historical exact-three
task count. Explain why the selected responsibilities cover the parent, map each child
to parent criterion indexes, and preserve dependencies and existing prerequisite
task references. Do not duplicate work already satisfied by retained evidence.
Three never overrides facts, safety, approval requirements, or the question budget.

Retain a JSON plan with `steps`; each item has a unique `id`, bounded `title`,
`complexity`, `files` (exact relative paths, implementation LOW only), and `children`.
LOW items declare `work_type`: `implementation` or `verification`; verification
leaves have empty commit files. Retain
criterion mapping and implementation/validation notes on the same items. Run
`python -m app.complexity validate --plan <plan-file>` from The Commons checkout
before execution. Exported fix ZIPs include `tools/complexity.py`; there use
`python tools/complexity.py` for the same validation and commit actions instead.
Do not assume another target repository contains the Commons module.
This replaces the previous easy/medium-only and automatic HIGH-task rule.

A proposed task is not authorized work. Do not create or publish a quest, mutate Git,
or assign the task unless the human explicitly approves that specific task.
Completing a later task does not by itself complete its parent criterion.

## Artifacts

Write the queue and mutable status files to the artifact paths supplied by the
caller. If the caller supplies no paths, use:

- `codex/output/iterative_implementation_items.txt`
- `codex/output/iterative_implementation_items_status.txt`

Keep these artifacts out of the implementation commit unless the user
explicitly requests otherwise. Retain them until the parent or user verifies
the final diff against the plan. Return both files verbatim in the result so
they remain available in conversation context. A concise cleaned plan may be
included in the commit body, but it does not replace the retained artifacts.

## Execution

1. Execute the earliest ready LOW leaf only, retaining its parent links and
   respecting human-only decisions. Implement its minimal change or prepare its
   evidence artifact according to `work_type`.
2. Run its narrow validation and record `done`, `blocked`, or `skipped` with a
   short evidence note.
3. Continue only as permitted by the caller:
   - For approved HANDOFFS outcomes, the project's standing human-guided AI mandate
     permits continuous ready LOW execution unless the user requests a checkpoint.
     Keep human LOW verification, participant consent, spending and deployment
     authority separate; the mandate cannot supply those approvals. Stop for a
     material scope, authority or risk decision and follow the project charter.
   - In other interactive sessions without continuous delegation, stop for
     verification after each item.
   - In a delegated executor session explicitly marked continuous, proceed to
     the next item without asking the parent between items.
4. Before committing, compare every changed line with the plan and acceptance
   criteria. Remove any change that is not required.
5. For implementation only, stage that LOW leaf's declared files. Commit its minimal change
   and necessary focused tests through the managed gate:
   `python -m app.complexity commit --plan <plan-file> --step <low-id>
   --repository <checkout> --message <subject>`. Never use direct `git commit`
   to bypass this workflow. The gate rejects parents, malformed trees, and
   staged files outside the selected leaf, verification leaves, and repeat commits
   for the same leaf/plan fingerprint. It records that receipt and serializes
   managed commits. Keep the approved plan immutable; changing it to evade a
   receipt is prohibited. This is not a global Git hook or publication permission.
6. For authorized Commons implementation work, finish STAGE, COMMIT, PUSH under
   the charter's standing Git publication policy. After the managed commit, push
   to the verified intended remote/branch only when tests and the entire outgoing
   history are cleared for that destination. Confirm remote delivery by SHA.
   A local commit or deployment is not a completed push. Preserve unrelated work;
   do not force-push, silently merge/rebase, create filler commits or bypass a
   prior publication rejection. Retain/report a specific blocker when unsafe,
   unauthorized or rejected. This does not supply human proof acceptance.

For verification-only work, retain source locators, exact checks, observed results
and unexecuted commands separately. An API-generated report is prepared evidence,
not proof that tests ran or that a human accepted it. No filler commits or invented
passes. Parent completion still requires integrated acceptance evidence.

Do not add defensive behavior merely because it is easy or prudent. If a
material decision is missing, stop with one concise question instead of
expanding scope.

## Completion

For a Watson/HANDOFFS LOW task, retain one sufficient primary proof artifact
(video, image or text) linked to its criteria and relevant source/run provenance.
It must be directly accessible from the closed LOW and inspectable by AI. AI
reviews the proof; the human explicitly verifies the outcome before completion.
Do not require multiple proof forms or silently reinstate the retired two-video
gate. Missing or inconclusive proof leaves the task unresolved. Prepared
reports and unexecuted checks are not passing evidence. If the runtime cannot
enforce this gate yet, report that gap rather than claim verified closure.

Return the verbatim plan and final status artifacts, the commit SHA, exact
validation results, criterion-by-criterion evidence, and unresolved gaps.
Explicitly state whether every changed path and behavior was planned and
required by the acceptance criteria. Return every task proposal verbatim and
identify the blocked parent criterion.
