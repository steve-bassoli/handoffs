"""Pure v1 normalization for caller-supplied saved-round metadata."""
from collections.abc import Mapping
from datetime import date


_MISSING_DATE = "missing_recorded_date"
_INVALID_DATE = "invalid_recorded_date"
_MALFORMED = "malformed_record"
_DUPLICATE = "duplicate_round_id"


def normalize_round_index(records, source_ref=None):
    """Return a v1 envelope from an iterable of candidate mappings."""
    if not isinstance(source_ref, (str, type(None))) or source_ref == "":
        raise ValueError("source_ref must be a nonempty string or None")
    result = {
        "schema_version": 1,
        "records": [],
        "issues": [],
        "provenance": {
            "source_ref": source_ref,
            "availability": "available" if source_ref is not None else "source_unavailable",
        },
    }
    try:
        candidates = iter(records)
    except TypeError:
        result["issues"].append(_issue(0, _MALFORMED, None))
        return result

    seen = set()
    for index, raw in enumerate(candidates):
        record, codes, round_id = _normalize(raw)
        result["issues"].extend(_issue(index, code, round_id) for code in codes)
        if record is None:
            continue
        if round_id in seen:
            result["issues"].append(_issue(index, _DUPLICATE, round_id))
            continue
        seen.add(round_id)
        result["records"].append(record)
    result["records"].sort(
        key=lambda item: (item["recorded_date"] is None,
                          item["recorded_date"] or "", item["round_id"])
    )
    return result


def _normalize(raw):
    if not isinstance(raw, Mapping):
        return None, [_MALFORMED], None
    round_id = raw.get("round_id")
    public_id = round_id if isinstance(round_id, str) else None
    recorded_date, date_code = _date_value(raw.get("recorded_date"))
    valid = (
        isinstance(round_id, str) and bool(round_id)
        and isinstance(raw.get("lesson"), str) and bool(raw["lesson"])
        and isinstance(raw.get("evidence_state"), str) and bool(raw["evidence_state"])
        and _artifacts_ok(raw.get("artifacts"))
        and _provenance_ok(raw.get("provenance"))
    )
    if not valid:
        codes = ([] if date_code is None else [date_code]) + [_MALFORMED]
        return None, codes, public_id
    return {
        "round_id": round_id,
        "recorded_date": recorded_date,
        "artifacts": [{"reference": item["reference"], "resolution": item["resolution"]}
                      for item in raw["artifacts"]],
        "lesson": raw["lesson"],
        "evidence_state": raw["evidence_state"],
        "provenance": dict(raw["provenance"]),
    }, ([] if date_code is None else [date_code]), round_id


def _date_value(value):
    if value is None:
        return None, _MISSING_DATE
    if not isinstance(value, str):
        return None, _INVALID_DATE
    try:
        return (value, None) if date.fromisoformat(value).isoformat() == value else (None, _INVALID_DATE)
    except ValueError:
        return None, _INVALID_DATE


def _artifacts_ok(items):
    return isinstance(items, list) and all(
        isinstance(item, Mapping) and isinstance(item.get("reference"), str)
        and bool(item["reference"]) and isinstance(item.get("resolution"), str)
        and item["resolution"] in ("resolved", "unresolved")
        for item in items
    )


def _provenance_ok(value):
    return (isinstance(value, Mapping) and isinstance(value.get("source_ref"), str)
            and bool(value["source_ref"]) and value.get("attribution") == "reported"
            and value.get("verification") == "unverified")


def _issue(index, code, round_id):
    return {"index": index, "code": code, "round_id": round_id}
