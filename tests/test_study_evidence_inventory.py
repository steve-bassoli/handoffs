import json
from pathlib import Path

import pytest

from app.study_evidence_inventory import build_inventory


def record(**changes):
    item = {'operation': 'projects', 'transport': 'REST',
            'binding': 'GET /api/v1/projects', 'reference': 'note-1',
            'outcome': 'pass', 'verification': 'reported',
            'verification_reference': None, 'provenance': 'synthetic test',
            'synthetic': True}
    item.update(changes)
    return item


def cell(inventory, operation, transport):
    return next(item for item in inventory['cells']
                if item['operation'] == operation and item['transport'] == transport)


def test_empty_input_has_nine_explicit_gaps():
    inventory = build_inventory([])
    assert inventory['schema_version'] == 1
    assert inventory['mode'] == 'offline_inventory'
    assert len(inventory['cells']) == 9
    assert all(item['state'] == 'gap' and item['evidence'] == []
               for item in inventory['cells'])


def test_exact_duplicates_collapse_without_upgrading_reported():
    inventory = build_inventory([record(), record()])
    item = cell(inventory, 'projects', 'REST')
    assert item['state'] == 'evidence'
    assert len(item['evidence']) == 1
    assert item['evidence'][0]['verification'] == 'reported'
    assert item['evidence'][0]['verification_reference'] is None


def test_repeated_reference_with_contradiction_is_retained_as_conflict():
    inventory = build_inventory([record(), record(outcome='fail')])
    item = cell(inventory, 'projects', 'REST')
    assert item['state'] == 'conflict'
    assert len(item['evidence']) == 2
    assert {entry['outcome'] for entry in item['evidence']} == {'pass', 'fail'}


def test_unresolved_and_incompatible_non_rest_bindings_remain_visible():
    inventory = build_inventory([
        record(transport='SOAP', binding=None, reference='soap-gap'),
        record(transport='MCP', binding='tool.one', reference='mcp-1'),
        record(transport='MCP', binding='tool.two', reference='mcp-2'),
    ])
    assert cell(inventory, 'projects', 'SOAP')['binding'] is None
    mcp = cell(inventory, 'projects', 'MCP')
    assert mcp['binding'] is None and mcp['state'] == 'conflict'
    assert len(mcp['evidence']) == 2


def test_wrong_rest_binding_is_a_review_conflict_not_a_rewritten_claim():
    inventory = build_inventory([record(binding='GET /invented')])
    item = cell(inventory, 'projects', 'REST')
    assert item['state'] == 'conflict'
    assert item['binding'] == 'GET /api/v1/projects'
    assert item['evidence'][0]['binding'] == 'GET /invented'


def test_invalid_identifiers_and_verification_claims_raise_value_error():
    with pytest.raises(ValueError):
        build_inventory([record(operation=[])])
    with pytest.raises(ValueError):
        build_inventory([record(verification='verified')])
    with pytest.raises(ValueError):
        build_inventory([record(verification_reference='unreviewed-note')])


def test_synthetic_false_is_rejected_without_relabeling():
    with pytest.raises(ValueError, match='synthetic must be true'):
        build_inventory([record(synthetic=False)])


def test_canonical_fixture_round_trips_from_flattened_cell_evidence():
    path = Path(__file__).parent / 'fixtures' / 'study_evidence_inventory_v1.json'
    fixture = json.loads(path.read_text(encoding='utf-8'))
    records = [dict(evidence, operation=cell['operation'],
                    transport=cell['transport'])
               for cell in fixture['cells'] for evidence in cell['evidence']]
    assert build_inventory(records) == fixture
