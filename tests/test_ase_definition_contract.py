"""Frozen ASE-v1: change only through explicit coordinated review."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.ase_definition import build_definition


EXPECTED = json.loads(r'''
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
''')


def canonical_json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def assert_same_json(actual, expected):
    assert canonical_json(actual) == canonical_json(expected)


def documented_definition():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "ase_definition.md").read_text(encoding="utf-8")
    opening = "<!-- ASE-V1-FACTS-BEGIN -->\n```json\n"
    closing = "\n```\n<!-- ASE-V1-FACTS-END -->"
    assert text.count(opening) == 1
    assert text.count(closing) == 1
    start = text.index(opening) + len(opening)
    end = text.index(closing, start)
    return json.loads(text[start:end])


def test_model_matches_frozen_contract():
    assert_same_json(build_definition(), EXPECTED)


def test_documentation_matches_frozen_contract():
    assert_same_json(documented_definition(), EXPECTED)


def test_complete_documented_block_matches_model():
    assert_same_json(documented_definition(), build_definition())


def test_false_to_zero_provenance_drift_is_rejected():
    altered = deepcopy(EXPECTED)
    altered["prior_work"][0]["provenance"]["external_reviewed"] = 0
    assert altered == EXPECTED  # Demonstrate the ordinary-equality loophole.
    with pytest.raises(AssertionError):
        assert_same_json(altered, EXPECTED)


def test_object_key_order_and_json_whitespace_are_not_contractual():
    reordered = dict(reversed(list(EXPECTED.items())))
    reformatted = json.loads(json.dumps(reordered, indent=4))
    assert_same_json(reformatted, EXPECTED)


def test_array_order_is_contractual():
    altered = deepcopy(EXPECTED)
    altered["properties"].reverse()
    with pytest.raises(AssertionError):
        assert_same_json(altered, EXPECTED)
