# Study evidence inventory v1-r2

This is an **offline inventory**, not a compatibility certificate. It records synthetic, caller-supplied claims. It does not call REST, SOAP, or MCP services, execute payloads, or infer SOAP/MCP bindings from REST.

## Envelope and cells

The canonical fixture is `{ "schema_version": 1, "mode": "offline_inventory", "cells": [...] }`. Cells are ordered by `projects`, `project_studies`, and `study_detail`; each operation is ordered `REST`, `SOAP`, `MCP`.

REST cell bindings are exactly:

- `GET /api/v1/projects`
- `GET /api/v1/projects/{projectId}/studies`
- `GET /api/v1/studies/{studyId}`

SOAP and MCP bindings are unresolved unless evidence supplies a nonempty binding. The fixture intentionally keeps them `null`.

## Evidence fields and scalar rules

Every evidence record has `binding`, `reference`, `outcome`, `verification`, `verification_reference`, `provenance`, and `synthetic`. `synthetic` must be `true`; `reference` and `provenance` are nonempty text; `binding` is either `null` or nonempty text.

`reported` requires `verification_reference: null`. `verified` requires a nonempty text `verification_reference`. A verified label remains a caller claim in this offline fixture; it is not proof that a route was executed or is compatible.

## States

An empty evidence list is `gap`. Evidence is `conflict` when outcomes disagree, multiple distinct nonempty evidence bindings occur, or REST evidence binding differs from its supplied route. Otherwise it is `evidence`.

A REST evidence mismatch does **not** alter the canonical REST cell binding: with `state: "conflict"`, it is valid contradictory evidence. A noncanonical REST cell binding is invalid. Passing fixture validation proves only that this synthetic inventory follows v1-r2, never live compatibility.
