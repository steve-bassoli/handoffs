import json
from pathlib import Path

import pytest

from app.round_index import normalize_round_index


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/round_index_v1.json"
CONTRACT = ROOT / "docs/round_index_contract.md"


def fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def record(round_id, date):
    return {
        "round_id": round_id,
        "recorded_date": date,
        "lesson": "reported lesson",
        "evidence_state": "unknown",
        "artifacts": [{"reference": "report section", "resolution": "unresolved"}],
        "provenance": {
            "source_ref": "round-one-report",
            "attribution": "reported",
            "verification": "unverified",
        },
    }


def test_fixture_is_empty_source_unavailable_envelope():
    assert fixture_payload() == {
        "schema_version": 1,
        "records": [],
        "issues": [],
        "provenance": {"source_ref": None, "availability": "source_unavailable"},
    }


def test_normalizer_empty_default_matches_authoritative_fixture():
    assert normalize_round_index([]) == fixture_payload()


def test_source_ref_must_be_nonempty_when_supplied():
    with pytest.raises(ValueError):
        normalize_round_index([], "")
    assert normalize_round_index([], "authorized-report")["provenance"] == {
        "source_ref": "authorized-report",
        "availability": "available",
    }


def test_invalid_date_first_record_wins_duplicate_and_is_retained():
    result = normalize_round_index([record("r1", "not-a-date"), record("r1", "2024-01-01")])
    assert result["records"] == [
        {**record("r1", "not-a-date"), "recorded_date": None}
    ]
    assert [issue["code"] for issue in result["issues"]] == [
        "invalid_recorded_date", "duplicate_round_id"
    ]


def test_contract_states_provenance_and_no_retry_rule():
    text = CONTRACT.read_text(encoding="utf-8")
    for required in (
        "`round_id`", "`recorded_date`", "`artifacts`", "`lesson`",
        "`evidence_state`", "\"attribution\":\n\"reported\"",
        "\"verification\": \"unverified\"", "`invalid_recorded_date`",
        "`duplicate_round_id`", "not permission to\nretry",
    ):
        assert required in text
