# ASE: proposed definition and adoption note

## Canonical factual block

This complete ASE-v1 block is proposed for generation by
`app.ase_definition.build_definition()`. This proposal has not executed that
function or generated this document at runtime. The independent frozen contract
is in `tests/test_ase_definition_contract.py`; tests must never refresh it from
the implementation. This block records proposed claims, not conformance proof.

<!-- ASE-V1-FACTS-BEGIN -->
```json
{
  "schema_version": "ASE-v1",
  "definition": "An Auditable Self-improving Ecosystem (ASE) is a proposed community pattern in which people and agents propose, evaluate and record improvements under explicit human authority and resource limits.",
  "properties": [
    {"id":"human-authority","text":"Human approval gates govern integration; automation does not establish human acceptance.","status":"proposed"},
    {"id":"auditable-change","text":"Record proposed changes, evaluation evidence, attribution and unresolved failures before promotion.","status":"proposed"},
    {"id":"bounded-resources","text":"Respect authorized budgets, consent and stop boundaries; unknown usage retains its reservation.","status":"proposed"},
    {"id":"tested-learning","text":"Treat improvement as a claim requiring evaluation, not a consequence of self-modification alone.","status":"proposed"}
  ],
  "prior_work": [
    {"id":"self-evolving-survey","url":"https://arxiv.org/pdf/2508.07407","summary":"The pinned source describes a 2025 survey calling for agents that live, learn and last.","status":"not_independently_reviewed","provenance":{"source":"ase_sources","sha256":"24c95d2581a9e91e46b0c9ed4500a10631971cca3f05a34e6b7dc3582aff3e73","external_reviewed":false}},
    {"id":"darwin-godel-machine","url":"https://arxiv.org/pdf/2505.22954","summary":"The pinned source describes an archive of coding agents, code edits and benchmark evaluation, with oversight and reward-hacking cautions.","status":"not_independently_reviewed","provenance":{"source":"ase_sources","sha256":"24c95d2581a9e91e46b0c9ed4500a10631971cca3f05a34e6b7dc3582aff3e73","external_reviewed":false}},
    {"id":"unnamed-reference-kit","url":null,"summary":"The pinned source mentions a reference kit without a traceable URL; it is not supporting evidence.","status":"unavailable","provenance":{"source":"ase_sources","sha256":"24c95d2581a9e91e46b0c9ed4500a10631971cca3f05a34e6b7dc3582aff3e73","external_reviewed":false}}
  ],
  "limits": [
    "External references were not independently reviewed here; the source hash identifies consulted shelf content, not article verification.",
    "Properties describe a proposed pattern, not observed repository conformance or proven improvement capabilities.",
    "No first-of-its-kind or superiority claim is established; citation-dependent novelty criteria remain blocked.",
    "Repository-generated conformance requires separately inspected implementation and recorded checks; this definition alone supplies neither."
  ]
}
```
<!-- ASE-V1-FACTS-END -->

## Interpretation and proposed adoption

Treat ASE as a community design proposal, not a demonstrated autonomous system.
The community framing is an organizing choice, not proof of novelty. The source
summaries above are attributed descriptions of a shelf note, not reviewed papers.
The unnamed reference kit remains unresolved and cannot support conclusions.

1. Choose a bounded improvement and name the human authorized to approve it.
   Keep consent, privacy, protected resources and stop conditions explicit.
2. Record a baseline, proposed change, attribution and evaluation criteria.
   Report failed and unexecuted checks; self-modification alone proves no learning.
3. Inspect implementation evidence before assigning conformance. Use stable
   property IDs to link evidence and checks; absent evidence stays unknown,
   rather than becoming a passing score. This definition supplies no scorecard.
4. Obtain explicit human approval before integration. Technical agreement or
   passing tests do not imply human acceptance or permission to publish.
5. Reassess results against the baseline, preserve limitations and offer rest
   without loss of basic access or recognition. Unknown usage retains its
   reservation; urgency never expands spending or consent authority.

A future repository-generated scorecard requires separately authorized inspection
and recorded checks. No deployment, autonomous improvement, superiority or
first-of-its-kind capability is established by these files.

## Contract maintenance

Compare the entire JSON block with `build_definition()` and independently with
the frozen EXPECTED literal. Wording, IDs, array order and provenance changes
must fail until explicitly coordinated and reviewed; never regenerate expected
values during a test. Object-key order and JSON whitespace are not contractual.
The two citation URLs are exact renderer allowlist entries, not an endorsement.
