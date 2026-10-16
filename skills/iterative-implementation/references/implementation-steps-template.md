# Implementation Plan Artifact

Record one section per step:

```text
id: <stable-id>
criterion: <verbatim acceptance criterion or unavoidable prerequisite>
objective: <smallest observable change needed>
source: <relevant existing file and symbol>
target: <file and symbol to change>
implementation: <minimal edit only>
complexity: <easy or medium>
validation: <narrowest proof for this criterion>
exclusions: <nearby behavior deliberately left unchanged>
status: open
```

The status artifact uses the same ids with `open`, `done`, `blocked`, or
`skipped`, plus one short evidence note. Do not create plan items for optional
improvements.

If a required item is high complexity, omit it from the executable queue and
append this proposal instead:

```text
bounty: <stable-id>
parent-criterion: <verbatim criterion>
objective: <bounded blocked outcome>
reason: <why this cannot be one easy or medium step>
acceptance: <narrowest proof>
reward: <proposed GOLD and XP>
status: proposed
```

The proposal remains an artifact until the human explicitly approves publishing
that specific bounty.
