---
name: iterative-implementation
description: Plan and execute the smallest acceptance-criteria-bound implementation while retaining auditable plan and status artifacts. Use for delegated JIRA implementation or other multi-step code changes where scope must not expand beyond explicit acceptance criteria.
---

# Iterative Implementation

Implement exactly the supplied acceptance criteria and nothing else. Treat them
as both the required outcome and the scope ceiling.

## Plan before editing

Read [references/implementation-steps-template.md](references/implementation-steps-template.md),
inspect only the source needed to resolve the criteria, and write an ordered
plan before changing source files. Every plan item must map to a verbatim
criterion or an unavoidable prerequisite. Exclude opportunistic cleanup,
refactors, hardening, error-path changes, abstractions, documentation, and tests
that do not provide the narrowest evidence for a criterion.

## Complexity gate

Use HIGH, MEDIUM, and LOW only; retired labels are invalid, not aliases.
Every HIGH must have either 2+ HIGH children or exactly 3 MEDIUM children,
never a mixture. HIGH descendants must eventually decompose to MEDIUM and LOW;
do not evade decomposition through an unbounded chain of HIGHs. Every MEDIUM
must have exactly 3 LOW children. LOW is a leaf: no children. Only LOW is
executable and only LOW can result in a Git commit. A genuinely LOW task can be a root.
Do not pad with fake tasks or relabel work to bypass decomposition. If three
meaningful children cannot be defined, ask the human; do not execute the parent.

Retain a JSON plan with `steps`; each item has a unique `id`, bounded `title`,
`complexity`, `files` (exact relative paths, LOW only), and `children`. Retain
criterion mapping and implementation/validation notes on the same items. Run
`python scripts/complexity.py validate --plan <plan-file>` before execution.
This replaces the previous easy/medium-only and automatic HIGH-bounty rule.

A bounty proposal is not a task. Do not create or publish a quest, mutate Git,
or assign the bounty unless the human explicitly approves that specific bounty.
Completing a later bounty does not by itself complete its parent criterion.

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

1. Implement the earliest open LOW leaf only, retaining its parent links.
2. Run its narrow validation and record `done`, `blocked`, or `skipped` with a
   short evidence note.
3. Continue only as permitted by the caller:
   - In an interactive user session, stop for verification after each item.
   - In a delegated executor session explicitly marked continuous, proceed to
     the next item without asking the parent between items.
4. Before committing, compare every changed line with the plan and acceptance
   criteria. Remove any change that is not required.
5. Stage only that LOW leaf's declared files. Commit only its minimal change
   and necessary focused tests through the managed gate:
   `python scripts/complexity.py commit --plan <plan-file> --step <low-id>
   --repository <checkout> --message <subject>`. Never use direct `git commit`
   to bypass this workflow. The gate rejects parents, malformed trees, and
   staged files outside the selected leaf, and records the leaf/plan fingerprint.
   It does not install a global Git hook or grant publication permissions.

Do not add defensive behavior merely because it is easy or prudent. If a
material decision is missing, stop with one concise question instead of
expanding scope.

## Completion

Return the verbatim plan and final status artifacts, the commit SHA, exact
validation results, criterion-by-criterion evidence, and unresolved gaps.
Explicitly state whether every changed path and behavior was planned and
required by the acceptance criteria. Return every bounty proposal verbatim and
identify the blocked parent criterion.
