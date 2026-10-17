# Work checkpoint v1

The authoritative data shape and synthetic examples are in
`tests/fixtures/work_checkpoints_v1.json`. This is a work-only checkpoint,
not permission to resume, spend, launch agents, or infer human acceptance.
All example activity and verification statements are fictional demonstrations,
not evidence that this proposal was applied or tested. No personal data is included.

## Shape

The envelope has exactly `schema_version: "work-checkpoint/v1"` and
`examples`, a list of records. Each record has exactly:

- `pressure`: integer 1, 2, or 3; booleans are invalid.
- `pressure_action`: the fixed value in the table below.
- `completed_action`: nonempty text describing completed work.
- `verification`: exactly `completed` and `proposed_checks`, each a list
  of nonempty strings. Either list may be empty.
- `usage`: exactly `status` (`known` or `unknown`) and boolean
  `reservation_retained`. Unknown usage requires `reservation_retained: true`.
- `automatic_retry`: exactly `false`.
- `next_step`: exactly `kind`, nonempty `instruction`, and
  `requires_existing_authority: true`.

No additional fields are allowed, including personal health information,
credentials, numeric cost estimates, or inferred acceptance.

| Pressure | Meaning | pressure_action | next_step.kind |
| --- | --- | --- | --- |
| 1 | Ready; focused pacing | focused_pacing | continue |
| 2 | Reduce load and checkpoint | reduce_load_checkpoint | checkpoint |
| 3 | STOP NOW | stop_now | stop |

## Pause and resume

At 2, reduce scope and leave a useful checkpoint. At 3, stop work and
return only a minimal authorized work-only checkpoint for review or a
smaller-model handoff. Do not recursively hand off to evade a stop.
A STOP record may have known or unknown usage; unknown usage is not a
universal STOP requirement. Any unknown usage retains its reservation,
and must never trigger an automatic retry.

Resume requires existing authority and capacity. A checkpoint is neither
new authority nor evidence of consent, spending permission, integration
permission, or completed verification. Pressure changes pacing, never
verification or consent requirements. Rest removes neither access nor recognition.

## Verification and usage honesty

`verification.completed` reports only checks actually completed by the
record's producer. `proposed_checks` lists unexecuted checks; displaying
or saving a proposal does not move it into completed verification.
The reduced-load and STOP examples deliberately have no completed checks.

`usage.status` is only a qualitative checkpoint state. This schema does
not report per-ticket tokens, credits, dollar cost, balances, or available
spending authority. Known status alone proves none of those quantities.
Unknown accounting must not become zero usage or a released reservation.
This fixture does not establish any live operational accounting.

## Proposed relay checks

Run `pytest -q tests/test_work_checkpoint_contract.py` after application,
then the validator and renderer test modules. Fixture tests check exact
fields, types, fixed mappings, retained unknown reservations, STOP safety,
and separate completed versus proposed verification. They do not prove
that free text is truthful or that authorization exists.

Render text inertly using `textContent`; no retry, launch, acceptance,
or spending controls are authorized by this contract. Integration and
human acceptance remain unresolved decisions for the authorized relay.
