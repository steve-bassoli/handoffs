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

Every executable plan item must declare `complexity: easy` or `complexity:
medium`. Never put a high-complexity item in the implementation queue and never
implement it under the current plan. Instead, add one `bounty` proposal to the
retained plan artifact with its parent criterion, bounded objective, reason it
is high complexity, narrow acceptance check, and proposed reward. Mark the
parent item blocked on that proposal.

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

1. Implement the earliest open plan item only.
2. Run its narrow validation and record `done`, `blocked`, or `skipped` with a
   short evidence note.
3. Continue only as permitted by the caller:
   - In an interactive user session, stop for verification after each item.
   - In a delegated executor session explicitly marked continuous, proceed to
     the next item without asking the parent between items.
4. Before committing, compare every changed line with the plan and acceptance
   criteria. Remove any change that is not required.
5. Commit only the minimal implementation and its necessary focused tests.

Do not add defensive behavior merely because it is easy or prudent. If a
material decision is missing, stop with one concise question instead of
expanding scope.

## Completion

Return the verbatim plan and final status artifacts, the commit SHA, exact
validation results, criterion-by-criterion evidence, and unresolved gaps.
Explicitly state whether every changed path and behavior was planned and
required by the acceptance criteria. Return every bounty proposal verbatim and
identify the blocked parent criterion.
