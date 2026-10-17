import copy
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "study_evidence_inventory_v1.json"
OPS = ("projects", "project_studies", "study_detail")
TRANSPORTS = ("REST", "SOAP", "MCP")
ROUTES = {
    "projects": "GET /api/v1/projects",
    "project_studies": "GET /api/v1/projects/{projectId}/studies",
    "study_detail": "GET /api/v1/studies/{studyId}",
}
FIELDS = {"binding", "reference", "outcome", "verification",
          "verification_reference", "provenance", "synthetic"}


def inventory():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def valid_text(value):
    return isinstance(value, str) and bool(value)


def expected_state(cell):
    evidence = cell["evidence"]
    if not evidence:
        return "gap"
    outcomes = {item["outcome"] for item in evidence}
    bindings = {item["binding"] for item in evidence if item["binding"]}
    mismatch = cell["transport"] == "REST" and any(
        value != ROUTES[cell["operation"]] for value in bindings)
    return "conflict" if len(outcomes) > 1 or len(bindings) > 1 or mismatch else "evidence"


def validate_inventory(data):
    if data.get("schema_version") != 1 or data.get("mode") != "offline_inventory":
        raise ValueError("wrong envelope")
    cells = data.get("cells", [])
    expected = [(op, transport) for op in OPS for transport in TRANSPORTS]
    if [(cell.get("operation"), cell.get("transport")) for cell in cells] != expected:
        raise ValueError("cells must be complete and ordered")
    for cell in cells:
        evidence = cell.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError("evidence must be a list")
        bindings = set()
        for item in evidence:
            if set(item) != FIELDS or item["synthetic"] is not True:
                raise ValueError("synthetic evidence fields required")
            if not all(valid_text(item[key]) for key in ("reference", "provenance")):
                raise ValueError("reference and provenance required")
            if item["outcome"] not in {"pass", "fail"} or item["verification"] not in {"reported", "verified"}:
                raise ValueError("invalid outcome or verification")
            binding = item["binding"]
            if binding is not None and not valid_text(binding):
                raise ValueError("binding must be null or nonempty text")
            reference = item["verification_reference"]
            if item["verification"] == "reported" and reference is not None:
                raise ValueError("reported reference must be null")
            if item["verification"] == "verified" and not valid_text(reference):
                raise ValueError("verified reference must be nonempty text")
            if binding is not None:
                bindings.add(binding)
        if cell["transport"] == "REST":
            if cell.get("binding") != ROUTES[cell["operation"]]:
                raise ValueError("REST cell binding must be supplied route")
        elif cell.get("binding") != (next(iter(bindings)) if len(bindings) == 1 else None):
            raise ValueError("non-REST binding selection is invalid")
        if cell.get("state") != expected_state(cell):
            raise ValueError("state does not reflect evidence")


def test_canonical_fixture_validates():
    validate_inventory(inventory())


@pytest.mark.parametrize("mutate", [
    lambda d: d["cells"].pop(),
    lambda d: d["cells"][0]["evidence"][0].update(synthetic=False),
    lambda d: d["cells"][0]["evidence"][0].update(verification_reference=""),
    lambda d: d["cells"][0]["evidence"][0].update(binding=""),
    lambda d: d["cells"][6]["evidence"][0].update(verification_reference="not-null"),
])
def test_validator_rejects_invalid_contract_data(mutate):
    data = copy.deepcopy(inventory())
    mutate(data)
    with pytest.raises(ValueError):
        validate_inventory(data)


def test_rest_evidence_binding_mismatch_is_valid_conflict():
    data = copy.deepcopy(inventory())
    cell = data["cells"][0]
    cell["evidence"][0]["binding"] = "GET /wrong"
    cell["state"] = "conflict"
    validate_inventory(data)


def test_rest_mismatch_mislabeled_evidence_is_rejected():
    data = copy.deepcopy(inventory())
    data["cells"][0]["evidence"][0]["binding"] = "GET /wrong"
    with pytest.raises(ValueError):
        validate_inventory(data)


def test_noncanonical_rest_cell_binding_is_rejected():
    data = copy.deepcopy(inventory())
    data["cells"][0]["binding"] = "GET /wrong"
    with pytest.raises(ValueError):
        validate_inventory(data)
