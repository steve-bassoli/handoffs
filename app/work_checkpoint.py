"""Validation for inert, work-only checkpoint records."""

_RECORD_KEYS = {
    "pressure", "pressure_action", "completed_action", "verification",
    "usage", "automatic_retry", "next_step",
}
_VERIFICATION_KEYS = {"completed", "proposed_checks"}
_USAGE_KEYS = {"status", "reservation_retained"}
_NEXT_STEP_KEYS = {"kind", "instruction", "requires_existing_authority"}
_PRESSURE_ACTIONS = {
    1: "focused_pacing",
    2: "reduce_load_checkpoint",
    3: "stop_now",
}
_NEXT_KINDS = {1: "continue", 2: "checkpoint", 3: "stop"}


def _fail(message):
    raise ValueError(message)


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != expected:
        _fail("invalid %s fields" % name)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        _fail("%s must be non-empty text" % name)


def _text_list(value, name):
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        _fail("%s must be a text list" % name)


def validate_checkpoint(record):
    """Return record when it has the explicit safe checkpoint shape."""
    _keys(record, _RECORD_KEYS, "record")
    pressure = record["pressure"]
    if type(pressure) is not int or pressure not in _PRESSURE_ACTIONS:
        _fail("pressure must be an integer from 1 through 3")
    if record["pressure_action"] != _PRESSURE_ACTIONS[pressure]:
        _fail("pressure action does not match pressure")
    _text(record["completed_action"], "completed_action")

    verification = record["verification"]
    _keys(verification, _VERIFICATION_KEYS, "verification")
    _text_list(verification["completed"], "verification.completed")
    _text_list(verification["proposed_checks"], "verification.proposed_checks")

    usage = record["usage"]
    _keys(usage, _USAGE_KEYS, "usage")
    status = usage["status"]
    if not isinstance(status, str) or status not in {"known", "unknown"}:
        _fail("usage.status is not allowlisted")
    if type(usage["reservation_retained"]) is not bool:
        _fail("usage.reservation_retained must be boolean")
    if status == "unknown" and not usage["reservation_retained"]:
        _fail("unknown usage must retain its reservation")

    if record["automatic_retry"] is not False:
        _fail("automatic retry is forbidden")
    next_step = record["next_step"]
    _keys(next_step, _NEXT_STEP_KEYS, "next_step")
    if next_step["kind"] != _NEXT_KINDS[pressure]:
        _fail("next-step kind does not match pressure")
    _text(next_step["instruction"], "next_step.instruction")
    if next_step["requires_existing_authority"] is not True:
        _fail("next step requires existing authority")
    return record
