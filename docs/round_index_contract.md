# Round index v1 contract

## Evidence boundary

`tests/fixtures/round_index_v1.json` is the authoritative v1 example. It is
empty because the pinned round-one report is unavailable. No historical lesson,
date, author, or artifact reference is asserted; those remain unresolved until
an authorized report is supplied.

## Envelope and producer

Output has `schema_version: 1`, `records`, `issues`, and `provenance`.
`normalize_round_index([], source_ref=None)` returns the exact fixture. Its
producer input is `normalize_round_index(records, source_ref=None)`, where
`records` is any iterable of candidate mappings, not an input envelope. It does
no filesystem discovery. `source_ref` must be null or a nonempty string; an
empty string or another type raises `ValueError`. A nonempty source reference
sets envelope availability to `available`; availability is not verification.

## Retained records

Each retained record has nonempty string `round_id`, `lesson`, and
`evidence_state`; `recorded_date` is null or Gregorian `YYYY-MM-DD`; and it
has `artifacts` and `provenance`. Each artifact is
`{ "reference": nonempty string, "resolution": "unresolved"|"resolved" }`.
Record provenance is `{ "source_ref": nonempty string, "attribution":
"reported", "verification": "unverified" }`. Reported is attribution, not
proof; resolved is not verification; unknown evidence states are preserved.

## Issues, dates, and order

Issue objects are `{ "index": integer, "code": string, "round_id":
string|null }`. Codes are `malformed_record`, `missing_recorded_date`,
`invalid_recorded_date`, and `duplicate_round_id`.

A record malformed in a field other than `recorded_date` is excluded with
`malformed_record`. Missing dates are retained as null with
`missing_recorded_date`. Invalid non-null dates are retained as null with
`invalid_recorded_date`; date invalidity alone is not `malformed_record`.
Therefore an invalid-date record remains eligible to be the first retained
round ID. The first retained `round_id` in input order wins; a later retained
duplicate is excluded with `duplicate_round_id`. Retained records sort by
non-null date ascending, null dates last, then `round_id` ascending.

## Safety rule

Interrupted usage whose outcome or accounting is unknown is not permission to
retry. This is a normative safety rule, not reported historical evidence.
