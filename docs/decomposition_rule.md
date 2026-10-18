# Canonical decomposition teaching

Status: proposed standalone reference; no existing consumer is wired by this file.
The marked block is generated teaching under CONTRACT_V1, not an independent policy table.

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

## Consume and verify

Import `build_teaching` and `render_markdown` from `app.decomposition_teaching`.
Use `build_teaching()` for structured data; use `render_markdown()` for this exact
marked block, or `render_markdown(teaching)` to render a supplied payload.
Generation is offline: no writes or model calls. Regeneration is a reviewed source
proposal, never permission to overwrite consumers automatically.

`fingerprint` is SHA-256 over UTF-8 JSON containing only `rules` and `min_children`,
with sorted keys, compact separators and ASCII escaping. It is not a source-file
hash, proof of validator integrity, or authority. The static block omits the digest.
The repeated HIGH example is an ordered branch trace, not a launch graph.
An empty LOW is a plan leaf; passing an empty list to the split validator is not a split.

Run `pytest tests/test_decomposition_teaching_contract.py` after the producer and
both references are present. The test pins the fixture, validates examples against
the canonical validator, and checks reference and policy-drift mutations.
No successful execution is asserted here.

## Adoption inventory: checks still required

The following mapped entry points require separate full inspection and integration
review; this proposal neither changes them nor claims they already consume teaching:

- `app/ai.py`
- `app/astra_agents.py`, `app/astra_chat.py`, `app/astra_tree.py`
- `skills/astra/SKILL.md`
- `skills/handoffs/SKILL.md`
- `skills/iterative-implementation/SKILL.md`
- `skills/iterative-implementation/references/implementation-steps-template.md`
- `skills/iterative-implementation/scripts/complexity.py`

Distinguish historical prose and legacy parameter names from active policy before
proposing adoption. Do not rewrite history as evidence of current behavior.
Only an implementation LOW may later qualify for a managed commit; teaching does
not grant commit, launch, spending, publication or human-acceptance authority.
