"""Pure-model checks; all fixtures are synthetic, not checkout certification."""
import copy

import pytest

from app.ase_adoption import build_adoption
from app.ase_definition import build_definition
from app.ase_conformance import build_scorecard


def fixture_card():
    def row(identity, status, path):
        evidence = [{'path': path, 'sha256': 'a' * 64, 'kind': 'source'}]
        if status == 'pass':
            evidence.append({'path': path, 'sha256': 'a' * 64, 'kind': 'behavior'})
        return dict(id=identity, status=status, scope='Synthetic scope', reason='Synthetic evidence',
                    evidence=evidence, conflicts=[])
    return dict(schema_version='ase-narrow-v1', scope='Synthetic fixture, not live evidence',
                properties=[row('decomposition', 'pass', 'app/complexity.py'),
                            row('human_gates', 'partial', 'PROJECT_CHARTER.md'),
                            row('humane_limits', 'gap', 'PROJECT_CHARTER.md')],
                limitations=['Synthetic evidence only.'])


def first(definition=None, card=None):
    return build_adoption(build_definition() if definition is None else definition,
                          fixture_card() if card is None else card)['capabilities'][0]


def test_states_labels_references_and_independence():
    definition, card = build_definition(), fixture_card()
    before = copy.deepcopy((definition, card))
    model = build_adoption(definition, card)
    assert [r['status'] for r in model['capabilities']] == ['pass', 'partial', 'gap']
    for row in model['capabilities']:
        assert row['label'] == row['id'].replace('_', ' ').title()
        assert row['property_refs'] == [p['id'] for p in row['properties']]
        for prop in row['properties']:
            assert prop in definition['properties']
        assert all(row[key] for key in ('action', 'verification', 'next_step'))
    model['capabilities'][0]['evidence'][0]['sha256'] = 'changed'
    model['capabilities'][0]['properties'][0]['text'] = 'changed'
    model['workflow'][0]['action'] = 'changed'
    assert (definition, card) == before
    assert build_adoption(definition, card)['workflow'][0]['action'] != 'changed'


@pytest.mark.parametrize('status', ['gap', 'partial', 'pass'])
def test_changed_status_never_upgraded(status):
    card = fixture_card()
    card['properties'][0]['status'] = status
    assert first(card=card)['status'] == status


@pytest.mark.parametrize('case', ['missing', 'bad_hash', 'mismatch', 'conflict',
                                  'unknown_status', 'duplicate', 'missing_row',
                                  'wrong_version', 'invalid_conflicts', 'extra'])
def test_invalid_evidence_cannot_pass(case):
    card = fixture_card()
    row = card['properties'][0]
    if case == 'missing':
        row['evidence'] = []
    elif case == 'bad_hash':
        row['evidence'][0]['sha256'] = 'bad'
    elif case == 'mismatch':
        row['evidence'][1]['sha256'] = 'b' * 64
    elif case == 'conflict':
        row['conflicts'] = ['Named check disagrees']
    elif case == 'unknown_status':
        row['status'] = 'certified'
    elif case == 'duplicate':
        card['properties'].append(copy.deepcopy(row))
    elif case == 'missing_row':
        card['properties'].pop(0)
    elif case == 'wrong_version':
        card['schema_version'] = 'future'
    elif case == 'invalid_conflicts':
        row['conflicts'] = None
    elif case == 'extra':
        row['accepted'] = True
    result = first(card=card)
    assert result['status'] != 'pass'
    if case == 'conflict':
        assert result['status'] == 'partial'
        assert result['conflicts'] == ['Named check disagrees']


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'invalid_text', 'version'])
def test_invalid_property_references_fail_closed(case):
    definition = build_definition()
    if case == 'missing':
        definition['properties'] = [p for p in definition['properties'] if p['id'] != 'tested-learning']
    elif case == 'duplicate':
        definition['properties'].append(copy.deepcopy(definition['properties'][1]))
    elif case == 'invalid_text':
        definition['properties'][1]['text'] = None
    else:
        definition['schema_version'] = 'future'
    row = first(definition=definition)
    assert row['status'] == 'gap'
    assert any('property reference' in issue for issue in row['issues'])


def test_charter_cannot_be_promoted_and_conflicts_survive_gap():
    card = fixture_card()
    card['properties'][1]['status'] = 'pass'
    card['properties'][2]['conflicts'] = ['Unresolved limit']
    model = build_adoption(build_definition(), card)
    assert model['capabilities'][1]['status'] == 'partial'
    assert model['capabilities'][2]['status'] == 'gap'
    assert model['capabilities'][2]['conflicts'] == ['Unresolved limit']


def test_missing_models_and_real_empty_root(tmp_path):
    absent = build_adoption(None, None)
    assert [r['status'] for r in absent['capabilities']] == ['gap'] * 3
    empty = build_adoption(build_definition(), build_scorecard(tmp_path))
    assert [r['status'] for r in empty['capabilities']] == ['gap'] * 3


def test_human_gates_rest_and_no_io(monkeypatch):
    import builtins
    import socket

    definition, card = build_definition(), fixture_card()

    def forbidden(*args, **kwargs):
        raise AssertionError('I/O forbidden')

    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', forbidden)
        patch.setattr(socket, 'socket', forbidden)
        model = build_adoption(definition, card)
    text = repr(model)
    assert 'passing checks are not human acceptance' in text
    assert 'unresolved evidence is not human acceptance' in text
    assert 'REST preserves access and recognition' in text
    assert 'Appreciation does not buy authority' in text
    assert 'without personal health details' in text
    assert 'no automatic launch or commit' in text
    assert [s['id'] for s in model['workflow']] == ['inspect', 'propose', 'test', 'rest']
    for step in model['workflow']:
        assert set(step) == {'id', 'action', 'verification', 'next_step'}
