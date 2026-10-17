import json
from pathlib import Path

import pytest

from app.work_checkpoint import validate_checkpoint


ACTIONS = {1: "focused_pacing", 2: "reduce_load_checkpoint", 3: "stop_now"}
KINDS = {1: "continue", 2: "checkpoint", 3: "stop"}


def record(pressure=3):
    return {
        "pressure": pressure,
        "pressure_action": ACTIONS[pressure],
        "completed_action": "Recorded the safe checkpoint.",
        "verification": {"completed": [], "proposed_checks": ["Run pytest later."]},
        "usage": {"status": "unknown", "reservation_retained": True},
        "automatic_retry": False,
        "next_step": {
            "kind": KINDS[pressure],
            "instruction": "Resume only with existing authority.",
            "requires_existing_authority": True,
        },
    }


def test_minimal_stop_record_is_accepted():
    checkpoint = record()
    assert validate_checkpoint(checkpoint) is checkpoint
    assert checkpoint["next_step"]["kind"] == "stop"


@pytest.mark.parametrize("pressure", [1, 2, 3])
def test_valid_pressure_mappings_preserve_identity(pressure):
    checkpoint = record(pressure)
    assert validate_checkpoint(checkpoint) is checkpoint


def test_stop_with_known_usage_is_accepted():
    checkpoint = record()
    checkpoint["usage"] = {"status": "known", "reservation_retained": False}
    assert validate_checkpoint(checkpoint) is checkpoint


def test_unknown_usage_retains_its_reservation():
    checkpoint = record()
    checkpoint["usage"]["reservation_retained"] = False
    with pytest.raises(ValueError, match="retain"):
        validate_checkpoint(checkpoint)


@pytest.mark.parametrize("retry", [True, 0, None, "retry automatically"])
def test_automatic_retry_is_rejected_structurally(retry):
    checkpoint = record()
    checkpoint["automatic_retry"] = retry
    with pytest.raises(ValueError, match="retry"):
        validate_checkpoint(checkpoint)


@pytest.mark.parametrize("field", [
    "pressure", "pressure_action", "completed_action", "verification",
    "usage", "automatic_retry", "next_step",
])
def test_missing_required_fields_are_rejected(field):
    checkpoint = record()
    del checkpoint[field]
    with pytest.raises(ValueError, match="fields"):
        validate_checkpoint(checkpoint)


def test_extra_and_missing_nested_fields_are_rejected():
    checkpoint = record()
    checkpoint["extra"] = "no"
    with pytest.raises(ValueError, match="record"):
        validate_checkpoint(checkpoint)
    checkpoint = record()
    checkpoint["verification"]["extra"] = "no"
    with pytest.raises(ValueError, match="verification"):
        validate_checkpoint(checkpoint)
    checkpoint = record()
    del checkpoint["usage"]["reservation_retained"]
    with pytest.raises(ValueError, match="usage"):
        validate_checkpoint(checkpoint)


@pytest.mark.parametrize("pressure", [0, 4, True, False, 1.0, 3.0, None, "1", [], {}])
def test_invalid_pressure_is_rejected(pressure):
    checkpoint = record()
    checkpoint["pressure"] = pressure
    with pytest.raises(ValueError, match="integer"):
        validate_checkpoint(checkpoint)


def test_mapping_mismatch_and_missing_authority_are_rejected():
    checkpoint = record(1)
    checkpoint["pressure_action"] = "stop_now"
    with pytest.raises(ValueError, match="action"):
        validate_checkpoint(checkpoint)
    checkpoint = record()
    checkpoint["next_step"]["kind"] = "continue"
    with pytest.raises(ValueError, match="kind"):
        validate_checkpoint(checkpoint)
    checkpoint = record()
    checkpoint["next_step"]["requires_existing_authority"] = False
    with pytest.raises(ValueError, match="authority"):
        validate_checkpoint(checkpoint)


def test_unhashable_usage_status_raises_value_error():
    checkpoint = record()
    checkpoint["usage"]["status"] = []
    with pytest.raises(ValueError, match="status"):
        validate_checkpoint(checkpoint)


def test_fixture_examples_are_accepted():
    fixture = Path("tests/fixtures/work_checkpoints_v1.json")
    envelope = json.loads(fixture.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == "work-checkpoint/v1"
    for checkpoint in envelope["examples"]:
        assert validate_checkpoint(checkpoint) is checkpoint
