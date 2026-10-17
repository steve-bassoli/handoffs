import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "work_checkpoints_v1.json"
RECORD_KEYS = {
    "pressure", "pressure_action", "completed_action", "verification",
    "usage", "automatic_retry", "next_step",
}
PAIRS = {
    1: ("focused_pacing", "continue"),
    2: ("reduce_load_checkpoint", "checkpoint"),
    3: ("stop_now", "stop"),
}


def load_examples():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(data) == {"schema_version", "examples"}
    assert data["schema_version"] == "work-checkpoint/v1"
    assert isinstance(data["examples"], list)
    return data["examples"]


def assert_text(value):
    assert isinstance(value, str)
    assert value.strip()


def test_examples_have_exact_safe_shape():
    examples = load_examples()
    assert len(examples) == 3
    for record in examples:
        assert set(record) == RECORD_KEYS
        assert type(record["pressure"]) is int
        assert record["pressure"] in PAIRS
        assert_text(record["completed_action"])
        verification = record["verification"]
        assert set(verification) == {"completed", "proposed_checks"}
        for values in verification.values():
            assert isinstance(values, list)
            for value in values:
                assert_text(value)
        usage = record["usage"]
        assert set(usage) == {"status", "reservation_retained"}
        assert usage["status"] in {"known", "unknown"}
        assert type(usage["reservation_retained"]) is bool
        step = record["next_step"]
        assert set(step) == {
            "kind", "instruction", "requires_existing_authority",
        }
        assert_text(step["instruction"])
        assert step["requires_existing_authority"] is True
        assert record["automatic_retry"] is False


def test_has_exactly_one_example_for_each_pressure():
    examples = load_examples()
    assert sorted(record["pressure"] for record in examples) == [1, 2, 3]
    for record in examples:
        assert (record["pressure_action"], record["next_step"]["kind"]) == PAIRS[
            record["pressure"]
        ]


def test_unknown_usage_retains_its_reservation():
    unknown = [
        record for record in load_examples()
        if record["usage"]["status"] == "unknown"
    ]
    assert unknown
    assert all(record["usage"]["reservation_retained"] is True
               for record in unknown)


def test_stop_is_a_non_retry_authorized_checkpoint():
    stop = next(record for record in load_examples() if record["pressure"] == 3)
    assert stop["pressure_action"] == "stop_now"
    assert stop["next_step"]["kind"] == "stop"
    assert stop["automatic_retry"] is False
    assert stop["next_step"]["requires_existing_authority"] is True
    # Unknown usage is covered separately; STOP itself also permits known usage.


def test_examples_keep_proposed_checks_separate_from_completed_verification():
    examples = load_examples()
    for record in examples:
        verification = record["verification"]
        assert verification["proposed_checks"]
        assert not (set(verification["completed"])
                    & set(verification["proposed_checks"]))
    for record in examples:
        if record["pressure"] in (2, 3):
            assert record["verification"]["completed"] == []
