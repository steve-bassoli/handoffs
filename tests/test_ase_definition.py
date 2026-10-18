"""Offline checks; full wording equality belongs to the shared contract test."""
import json

from app.ase_definition import build_definition


SOURCE_HASH = '24c95d2581a9e91e46b0c9ed4500a10631971cca3f05a34e6b7dc3582aff3e73'


def test_schema_and_nested_types():
    model = build_definition()
    assert set(model) == {
        'schema_version', 'definition', 'properties', 'prior_work', 'limits',
    }
    assert model['schema_version'] == 'ASE-v1'
    assert isinstance(model['definition'], str) and model['definition']
    assert isinstance(model['properties'], list) and len(model['properties']) == 4
    for prop in model['properties']:
        assert set(prop) == {'id', 'text', 'status'}
        assert all(isinstance(value, str) and value for value in prop.values())
    assert isinstance(model['prior_work'], list) and len(model['prior_work']) == 3
    for record in model['prior_work']:
        assert set(record) == {'id', 'url', 'summary', 'status', 'provenance'}
        for key in ('id', 'summary', 'status'):
            assert isinstance(record[key], str) and record[key]
        assert record['url'] is None or isinstance(record['url'], str)
        assert isinstance(record['provenance'], dict)
    assert isinstance(model['limits'], list) and len(model['limits']) == 4
    assert all(isinstance(item, str) and item for item in model['limits'])
    assert json.loads(json.dumps(model)) == model


def test_stable_unique_ids_and_proposed_properties():
    model = build_definition()
    assert [p['id'] for p in model['properties']] == [
        'human-authority', 'auditable-change', 'bounded-resources', 'tested-learning',
    ]
    assert [r['id'] for r in model['prior_work']] == [
        'self-evolving-survey', 'darwin-godel-machine', 'unnamed-reference-kit',
    ]
    ids = [item['id'] for key in ('properties', 'prior_work') for item in model[key]]
    assert len(ids) == len(set(ids))
    assert {p['status'] for p in model['properties']} == {'proposed'}
    assert 'proposed community pattern' in model['definition']
    assert 'not observed repository conformance' in model['limits'][1]


def test_exact_citation_provenance_and_unavailable_evidence():
    records = build_definition()['prior_work']
    assert [record['url'] for record in records] == [
        'https://arxiv.org/pdf/2508.07407',
        'https://arxiv.org/pdf/2505.22954',
        None,
    ]
    assert [record['status'] for record in records] == [
        'not_independently_reviewed', 'not_independently_reviewed', 'unavailable',
    ]
    for record in records:
        assert record['provenance'] == {
            'source': 'ase_sources',
            'sha256': SOURCE_HASH,
            'external_reviewed': False,
        }
        assert record['provenance']['external_reviewed'] is False
    assert 'not supporting evidence' in records[2]['summary']
    assert 'not article verification' in build_definition()['limits'][0]


def test_returns_independent_nested_values():
    baseline = build_definition()
    changed = build_definition()
    assert changed == baseline
    for key in ('properties', 'prior_work', 'limits'):
        assert changed[key] is not baseline[key]
    for key in ('properties', 'prior_work'):
        for left, right in zip(changed[key], baseline[key]):
            assert left is not right
    provenances = [record['provenance'] for record in changed['prior_work']]
    assert len({id(value) for value in provenances}) == len(provenances)
    changed['properties'][0]['text'] = 'changed'
    provenances[0]['source'] = 'changed'
    assert provenances[1]['source'] == 'ase_sources'
    changed['prior_work'].append({})
    changed['limits'].clear()
    changed['schema_version'] = 'changed'
    assert build_definition() == baseline
