import copy
import json
from pathlib import Path

import pytest

from app import decomposition_visibility as model


FIXTURE = Path(__file__).parent / 'fixtures' / 'decomposition_visibility_v1.json'


def snapshot(parent='HIGH', levels=('MEDIUM', 'MEDIUM')):
    ids = ['P'] + ['C' + str(i) for i in range(len(levels))]
    lineage = [{'id': key, 'parent_id': None if key == 'P' else 'P'}
               for key in ids]
    details = {key: {'complexity': level, 'classification_explicit': True}
               for key, level in zip(ids, (parent,) + tuple(levels))}
    return {'lineage': lineage, 'detailsById': details,
            'coverage': {'complete_parent_ids': ids}}


def ticket(data, key='P'):
    return next(row for row in model.project_decomposition_visibility(**data)
                ['tickets'] if row['id'] == key)


def test_retained_fixture_and_immutability():
    cases = json.loads(FIXTURE.read_text(encoding='utf-8'))['cases']
    for case in cases:
        before = copy.deepcopy(case['input'])
        assert model.project_decomposition_visibility(**case['input']) == case['expected'], case['name']
        assert case['input'] == before


@pytest.mark.parametrize('parent,levels,status', [
    ('HIGH', ('HIGH', 'HIGH'), 'valid'),
    ('HIGH', ('MEDIUM', 'MEDIUM'), 'valid'),
    ('MEDIUM', ('LOW',) * 4, 'valid'),
    ('HIGH', ('HIGH', 'MEDIUM'), 'violation'),
    ('HIGH', ('MEDIUM',), 'violation'),
    ('LOW', ('LOW', 'LOW'), 'violation'),
])
def test_actual_groups(parent, levels, status):
    assert ticket(snapshot(parent, levels))['status'] == status


@pytest.mark.parametrize('change,reason', [
    ('coverage', 'coverage_incomplete'),
    ('parent_field', 'topology_incomplete'),
    ('orphan', 'topology_invalid'),
    ('cycle', 'topology_invalid'),
    ('duplicate', 'topology_invalid'),
    ('classification', 'classification_missing'),
])
def test_incomplete_evidence_never_calls_validator(monkeypatch, change, reason):
    data = snapshot()
    if change == 'coverage':
        data['coverage'] = {}
    elif change == 'parent_field':
        del data['lineage'][0]['parent_id']
    elif change == 'orphan':
        data['lineage'][0]['parent_id'] = 'absent'
    elif change == 'cycle':
        data['lineage'][0]['parent_id'] = 'C0'
    elif change == 'duplicate':
        data['lineage'].append(dict(data['lineage'][0]))
    else:
        data['detailsById']['C0']['classification_explicit'] = False
    def forbidden(*args):
        pytest.fail('incomplete group must not reach policy validation')
    monkeypatch.setattr(model, 'validate_bounty_split', forbidden)
    assert ticket(data)['reasons'] == [reason]


def test_successful_return_is_acceptance(monkeypatch):
    calls = []
    def accept(parent, levels):
        calls.append((parent, levels))
        return None
    monkeypatch.setattr(model, 'validate_bounty_split', accept)
    assert ticket(snapshot())['status'] == 'valid'
    assert calls == [('HIGH', ['MEDIUM', 'MEDIUM'])]


def test_untouched_and_non_authoritative_edges():
    data = snapshot(levels=())
    data['lineage'][0]['children'] = ['invented']
    data['lineage'][0]['dependencies'] = ['invented']
    assert ticket(data)['status'] == 'not_yet_split'


def test_deep_topology_is_iterative_and_bounded():
    rows = [{'id': str(i), 'parent_id': str(i - 1) if i else None}
            for i in range(1500)]
    result = model.project_decomposition_visibility(rows, {}, {})
    assert len(result['tickets']) == 1500
    assert all(row['status'] == 'unknown' for row in result['tickets'])
    with pytest.raises(ValueError):
        model.project_decomposition_visibility([{}] * (model.MAX_TICKETS + 1), {}, {})


def test_unexpected_validator_failure_is_not_hidden(monkeypatch):
    def broken(*args):
        raise RuntimeError('unexpected')
    monkeypatch.setattr(model, 'validate_bounty_split', broken)
    with pytest.raises(RuntimeError):
        ticket(snapshot())
