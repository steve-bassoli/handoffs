# Understanding ASE adoption locally

An Auditable Self-improving Ecosystem (ASE) is a proposed pattern, not a
certification. The definition supplies proposed properties; the narrow
scorecard supplies scoped observations. The adoption model connects them
without treating a passing probe as deployed enforcement or learning.

## Local inspection and boundaries

Read `app/ase_definition.py`, `app/ase_conformance.py` and
`app/ase_adoption.py` offline. Inspect scorecard scope, reasons, source paths,
SHA-256 fingerprints and conflicts, not just status. A pass concerns only the
named narrow check; partial evidence remains incomplete or conflicting. A gap
means insufficient evidence, not proof that a capability is absent. Source
changes invalidate saved fingerprints: rebuild the scorecard and review again.
The adoption builder itself performs no network access, source reads or writes.
It reports supplied fingerprints; it cannot authenticate current source bytes.

The generated blocks below describe a synthetic empty root, NOT this checkout.
Their candidate contents are UNEXECUTED. Contract tests compare the claims
with the existing definition and actual empty-root scorecard, and compare the
checklist with the adoption model. The live-source mutation test separately
checks that stale stronger claims and stale fingerprints cannot survive a
change to synthetic code evidence. These tests are not a live deployment audit.

## Generated claims — candidate, UNEXECUTED
```ase-adoption-claims
{"definition":"An Auditable Self-improving Ecosystem (ASE) is a proposed community pattern in which people and agents propose, evaluate and record improvements under explicit human authority and resource limits.","capabilities":[{"id":"decomposition","label":"Decomposition","property_refs":["auditable-change","tested-learning"],"status":"gap","evidence":[],"conflicts":[]},{"id":"human_gates","label":"Human Gates","property_refs":["human-authority"],"status":"gap","evidence":[],"conflicts":[]},{"id":"humane_limits","label":"Humane Limits","property_refs":["bounded-resources"],"status":"gap","evidence":[],"conflicts":[]}]}
```

## Generated checklist — candidate, UNEXECUTED
```ase-adoption-checklist
[{"id":"inspect","action":"Inspect the supplied definition and narrow scorecard offline.","verification":"Record scope, source fingerprints, gaps and conflicts; this model performs no source inspection.","next_step":"Select one bounded issue, or keep a work-only REST checkpoint."},{"id":"propose","action":"Describe a bounded implementation LOW with owned files and explicit acceptance criteria.","verification":"Confirm consent, resource limits and separate implementation authority; no automatic launch or commit.","next_step":"Present proposed source changes for authorized review."},{"id":"test","action":"Request authorization for named local tests before execution.","verification":"Record actual commands, results, failures, unknown usage and unexecuted checks; never retry unknown usage automatically.","next_step":"Refresh evidence after source changes, then request separate human acceptance."},{"id":"rest","action":"REST at capacity with a minimal work-only checkpoint.","verification":"Record completed work, failures, unknowns and unexecuted checks without personal health details.","next_step":"Resume only within authorized capacity; REST preserves access and recognition."}]
```

## Proposed local commands — UNEXECUTED

From the checkout root, after a human authorizes testing:

```text
python -m pytest -q tests/test_ase_adoption.py tests/test_ase_explainer_view.py tests/test_ase_adoption_contract.py
python -m pytest -q
python -m app.ase_conformance --repo-root .
```

These commands require the existing project environment. They do not install
packages, launch agents or authorize additional spending. The Node-vm renderer
tests skip cleanly if Node is unavailable; that is an unexecuted renderer check,
not a pass. There are no Windows/POSIX platform skips. The scorecard should only
inspect a stable, authorized local checkout; its documented fallback is not a
sandbox against hostile concurrent filesystem changes.

## Standalone view

`window.renderAseExplainer(model)` consumes only a supplied adoption model and
returns a detached section using textContent. It does not fetch evidence,
recompute checks, attach itself to a host page, or add routes. No launch,
payment, acceptance or settings controls are provided. A host integration would
be separate authorized work. Structural validation is not source verification.

## Human approval, recognition and access

Implementation authority permits proposed source changes, not live database
writes, public disclosure, child publication or inferred human acceptance.
Testing needs authorization; passing tests do not establish human acceptance.
Unresolved evidence is not human acceptance. A bounded implementation LOW may
later receive a managed commit only under separate authority.

REST preserves access and recognition. Appreciation does not buy authority or
replace proof. ADMIRATION is freely given without debit to the giver, payment,
reciprocal obligation or purchased authority. GROWTH records demonstrated
learning and verified contribution; it cannot be bought, transferred or spent.
Game Credits start at 1000000 and ADMIRATION at 1; neither is real dollars or
extra API spending authority. No debt, compulsory work or resource seizure is
part of adoption.

## No-personal-quota reading policy

People without personal AI quota must be able to read the local guide and
inspect exported text without buying AI access, supplying an API key or
accepting work obligations. This is a reading policy, not proof of an already
integrated public reading surface. Do not include keys or private human health
details in exports. Carry authorized work context in checkpoints rather than
requiring people to relay between agents. Human capacity reporting is voluntary
and private; a work-only REST checkpoint records actions, verification and next
steps, failures, unknowns and unexecuted checks without personal health details.
