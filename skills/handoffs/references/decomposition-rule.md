# Handoff reference: generated decomposition teaching

Status: proposed reference only. Existing skill entry points are unchanged.
CONTRACT_V1 pins this generated block to the canonical producer and validator.

<!-- BEGIN GENERATED DECOMPOSITION_TEACHING V1 -->
Source: `app.complexity:DECOMPOSITION,MIN_CHILDREN,validate_task_split`

A HIGH splits into two or more HIGHs or two or more MEDIUMs, never a mix. A MEDIUM splits into two or more LOWs. A LOW never splits. HIGH-to-HIGH decomposition may repeat. Counts follow grounded work, not a fixed three. Structural examples do not authorize agent launches.

- high-two-medium: HIGH -> MEDIUM, MEDIUM [valid]
- medium-four-low: MEDIUM -> LOW, LOW, LOW, LOW [valid]
- high-repeat: HIGH -> HIGH, HIGH; HIGH -> HIGH, HIGH [valid]
- high-mixed: HIGH -> HIGH, MEDIUM [invalid]
- low-split: LOW -> LOW, LOW [invalid]
- high-single: HIGH -> HIGH [invalid]
<!-- END GENERATED DECOMPOSITION_TEACHING V1 -->

## Consumption instructions

Import `build_teaching` and `render_markdown` from `app.decomposition_teaching`.
Consume `build_teaching()` for structured handoffs or UI payloads. Consume
`render_markdown()` for the canonical block; `render_markdown(teaching)` renders
supplied data. Generation performs no writes or model calls. A reviewer must
approve any proposed regeneration or adoption; this reference wires nothing.

The semantic fingerprint covers only `rules` and `min_children` using sorted,
compact, ASCII-escaped JSON encoded as UTF-8 and hashed with SHA-256. It is not a
source-byte hash or validator-integrity proof. It is omitted from this static block.
The repeated HIGH example traces one branch; it does not authorize agent spawning.
A LOW can be an empty plan leaf, but an empty child list is not a valid split.

Run `pytest tests/test_decomposition_teaching_contract.py` after all proposed
producer/reference files are present. Execution has not been asserted.

## Required adoption review, not completed integration

Inspect each mapped entry point in full before proposing any wiring:

- `app/ai.py`
- `app/astra_agents.py`, `app/astra_chat.py`, `app/astra_tree.py`
- `skills/astra/SKILL.md`
- `skills/handoffs/SKILL.md`
- `skills/iterative-implementation/SKILL.md`
- `skills/iterative-implementation/references/implementation-steps-template.md`
- `skills/iterative-implementation/scripts/complexity.py`

These are an inventory of checks still required, not inspected or changed consumers.
Historical prose and legacy parameter names are not automatically active policy.
Only an implementation LOW may later receive a managed commit. Structural examples
do not confer launch, commit, spending, disclosure or human-acceptance authority.
