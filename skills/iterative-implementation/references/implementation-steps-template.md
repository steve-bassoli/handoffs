# Implementation Plan Artifact

Retain JSON with a `steps` array. Each node contains `id`, `title`, `complexity`,
`children`, and `files`, plus the criterion/implementation/validation notes below.
HIGH has exactly three MEDIUM children; MEDIUM has exactly three SMALL children.
SMALL has no children. LOW normalizes to SMALL. Only SMALL leaves declare files,
execute changes, and commit; parents have an empty files array. A genuinely SMALL
root needs no artificial parents. Never pad with fake tasks.

Record these additional fields on each step:

```text
id: <stable-id>
criterion: <verbatim acceptance criterion or unavoidable prerequisite>
objective: <smallest observable change needed>
source: <relevant existing file and symbol>
target: <file and symbol to change>
implementation: <minimal edit only>
complexity: <HIGH, MEDIUM, or SMALL>
validation: <narrowest proof for this criterion>
exclusions: <nearby behavior deliberately left unchanged>
status: open
```

The status artifact uses the same ids with `open`, `done`, `blocked`, or
`skipped`, plus one short evidence note. Do not create plan items for optional
improvements.

Decompose HIGH and MEDIUM before execution. If a decision or dependency is still
blocked, retain a proposal instead of publishing a new task:

```text
bounty: <stable-id>
parent-criterion: <verbatim criterion>
objective: <bounded blocked outcome>
reason: <unresolved decision or dependency after decomposition>
acceptance: <narrowest proof>
reward: <proposed GOLD and XP>
status: proposed
```

The proposal remains an artifact until the human explicitly approves publishing
that specific bounty.
