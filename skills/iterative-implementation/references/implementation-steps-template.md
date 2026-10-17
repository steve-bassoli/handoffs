# Implementation Plan Artifact

Retain JSON with a `steps` array. Each node contains `id`, `title`, `complexity`,
`children`, and `files`, plus the criterion/implementation/validation notes below.
HIGH has multiple HIGH children or multiple MEDIUM children, without mixing levels.
Descendants eventually reach MEDIUM, which has multiple LOW children. A split has
at least two meaningful children, not a prescribed total. Never force three.
LOW has no children. Only HIGH/MEDIUM/LOW are valid labels.
Only implementation LOW leaves declare commit files; verification LOW leaves retain
evidence instead. Parents have an empty files array. A genuinely LOW
root needs no artificial parents. Never pad with fake tasks.

Record these additional fields on each step:

```text
id: <stable-id>
criterion: <verbatim acceptance criterion or unavoidable prerequisite>
objective: <smallest observable change needed>
source: <relevant existing file and symbol>
target: <file and symbol to change>
implementation: <minimal edit only>
complexity: <HIGH, MEDIUM, or LOW>
work_type: <implementation or verification; required for LOW>
parent_criteria: <zero-based criterion indexes this child contributes to>
validation: <narrowest proof for this criterion>
exclusions: <nearby behavior deliberately left unchanged>
status: open
```

The status artifact uses the same ids with `open`, `done`, `blocked`, or
`skipped`, plus one short evidence note. Do not create plan items for optional
improvements.

For each proposed split, retain a rationale (the compatible API field is still
named `why_three` regardless of child count): explain its distinct responsibilities,
criterion coverage, dependency order, and how the results satisfy the parent.
All parent criteria must be covered. Cite retained evidence and existing tasks so
the split does not manufacture duplicate work. A label alone does not establish
that a leaf is small; each LOW needs one bounded, independently verifiable outcome.
One implementation LOW owns one minimal commit for its immutable plan/leaf receipt.
Verification LOWs own report artifacts and no commit files. Keep proposed checks
separate from actual observations, including any human approval still required.

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
