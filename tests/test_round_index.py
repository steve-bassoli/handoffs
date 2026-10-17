import pytest

from app.round_index import normalize_round_index


def record(round_id, recorded_date="2024-01-02", **changes):
    value = {
        "round_id": round_id,
        "recorded_date": recorded_date,
        "artifacts": [{"reference": "round-one-report", "resolution": "unresolved"}],
        "lesson": "Keep evidence separate from verification.",
        "evidence_state": "reported",
        "provenance": {"source_ref": "round-one-report", "attribution": "reported",
                       "verification": "unverified"},
    }
    value.update(changes)
    return value


def test_empty_input_matches_source_unavailable_envelope():
    assert normalize_round_index([], None) == {
        "schema_version": 1, "records": [], "issues": [],
        "provenance": {"source_ref": None, "availability": "source_unavailable"},
    }


def test_invalid_date_is_retained_as_null_not_malformed():
    index = normalize_round_index([record("r2", "not-a-date")], "caller-report")
    assert index["records"][0]["recorded_date"] is None
    assert index["issues"] == [{"index": 0, "code": "invalid_recorded_date", "round_id": "r2"}]
    assert index["provenance"]["availability"] == "available"


def test_missing_dates_sort_last_and_unknown_evidence_state_survives():
    index = normalize_round_index([
        record("z", None), record("b", "2024-01-01", evidence_state="pending-external"),
        record("a", "2024-01-01"),
    ])
    assert [item["round_id"] for item in index["records"]] == ["a", "b", "z"]
    assert index["records"][1]["evidence_state"] == "pending-external"
    assert index["issues"] == [{"index": 0, "code": "missing_recorded_date", "round_id": "z"}]


def test_invalid_date_first_record_survives_and_wins_later_duplicate():
    index = normalize_round_index([
        record("same", "not-a-date"), record("same", "2024-02-02"),
    ], "caller-report")
    assert index["records"] == [record("same", None)]
    assert index["issues"] == [
        {"index": 0, "code": "invalid_recorded_date", "round_id": "same"},
        {"index": 1, "code": "duplicate_round_id", "round_id": "same"},
    ]


def test_first_valid_duplicate_wins_and_iterable_input_is_supported():
    candidates = (item for item in [
        record("same", "2024-02-01"), record("same", "2024-02-02"),
    ])
    index = normalize_round_index(candidates, "caller-report")
    assert [item["recorded_date"] for item in index["records"]] == ["2024-02-01"]
    assert index["issues"] == [{"index": 1, "code": "duplicate_round_id", "round_id": "same"}]


def test_empty_lesson_and_unhashable_artifact_metadata_are_malformed():
    index = normalize_round_index([
        record("empty", lesson=""),
        record("artifact", artifacts=[{"reference": "x", "resolution": []}]),
    ])
    assert index["records"] == []
    assert index["issues"] == [
        {"index": 0, "code": "malformed_record", "round_id": "empty"},
        {"index": 1, "code": "malformed_record", "round_id": "artifact"},
    ]


def test_valid_normalized_record_matches_contract_shape():
    index = normalize_round_index([record("r1")])
    assert index["records"] == [record("r1")]


@pytest.mark.parametrize("source_ref", ["", 3, []])
def test_invalid_envelope_source_ref_is_rejected_explicitly(source_ref):
    with pytest.raises(ValueError, match="source_ref"):
        normalize_round_index([], source_ref)
