# Proposal: retire energy; bobs only say when they should rest (task bb4bcf2c)

Author: the relay, for Steve (2026-10-19: "Energy? I think that dies too.").

Approve in Decisions: you and Nate each Accept the card; the second Accept writes and commits the files.
SHA-256 of `agent-rules.json`: `faa360cc1c4e3360e639f2e79e75fd626cecf080dd1f68b711667aa2ec4cd71f`

## The change

Only these six texts change; everything else is byte for byte the same.

- **COMMONS_RULES**: drops "Report your energy as full, steady or low (low: lighten the load and checkpoint)." It keeps "Set rest to true when you should stop: stop work and return a minimal authorized work-only checkpoint …".
- **PRESSURE_RULES** (key name unchanged): "Rest may change priority and pacing, never consent, spending authority or verification requirements." and "Rest describes observable working conditions, not a claim that a model has feelings." The urgency guard stays word for word.
- **SHARED**: "rest is true only when you should stop."
- **COORDINATOR_PREFIX, LEAD_PREFIX, WORKER_PREFIX**: reply fields end with "rest" instead of "energy, rest".
