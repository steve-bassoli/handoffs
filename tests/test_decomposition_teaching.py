"""Producer checks; execution and integration are relay responsibilities."""
import hashlib
import json

import pytest

from app.complexity import DECOMPOSITION, MIN_CHILDREN, validate_task_split
from app import decomposition_teaching as producer


EXPECTED_EXPLANATION = (
    'A HIGH splits into two or more HIGHs or two or more MEDIUMs, never a mix. '
    'A MEDIUM splits into two or more LOWs. A LOW never splits. '
    'HIGH-to-HIGH decomposition may repeat. '
    'Counts follow grounded work, not a fixed three. '
    'Structural examples do not authorize agent launches.'
)


def test_schema_prose_and_semantic_fingerprint():
    teaching = producer.build_teaching()
    assert set(teaching) == {
        'version', 'source', 'min_children', 'rules', 'explanation',
        'examples', 'fingerprint',
    }
    assert type(teaching['version']) is int and teaching['version'] == 1
    assert type(teaching['min_children']) is int
    assert teaching['min_children'] == MIN_CHILDREN
    assert teaching['rules'] == {k: list(v) for k, v in DECOMPOSITION.items()}
    assert teaching['explanation'] == EXPECTED_EXPLANATION
    semantics = {key: teaching[key] for key in ('rules', 'min_children')}
    encoded = json.dumps(semantics, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True).encode('utf-8')
    assert teaching['fingerprint'] == hashlib.sha256(encoded).hexdigest()
    assert teaching['fingerprint'] != '0' * 64


def test_six_examples_match_validator_and_contract():
    examples = producer.build_teaching()['examples']
    assert [(e['id'], e['valid']) for e in examples] == [
        ('high-two-medium', True), ('medium-four-low', True),
        ('high-repeat', True), ('high-mixed', False),
        ('low-split', False), ('high-single', False),
    ]
    assert len(examples[0]['splits'][0]['children']) == 2
    assert len(examples[1]['splits'][0]['children']) == 4
    assert examples[2]['splits'] == [
        {'parent': 'HIGH', 'children': ['HIGH', 'HIGH']},
        {'parent': 'HIGH', 'children': ['HIGH', 'HIGH']},
    ]
    for example in examples:
        assert type(example['valid']) is bool
        outcomes = []
        for split in example['splits']:
            try:
                validate_task_split(split['parent'], split['children'])
            except ValueError:
                outcomes.append(False)
            else:
                outcomes.append(True)
        assert example['valid'] is all(outcomes)


def test_low_leafhood_is_not_an_empty_split():
    assert producer.build_teaching()['rules']['LOW'] == []
    for children in ([], ['LOW', 'LOW']):
        with pytest.raises(ValueError):
            validate_task_split('LOW', children)


def test_deterministic_fresh_data_and_markdown():
    first, second = producer.build_teaching(), producer.build_teaching()
    assert first == second
    assert producer.render_markdown() == producer.render_markdown(second)
    first['rules']['LOW'].append('HIGH')
    first['examples'][0]['splits'][0]['children'].clear()
    assert producer.build_teaching() == second
    markdown = producer.render_markdown(second)
    assert markdown.startswith(producer.BEGIN + '\n')
    assert markdown.endswith(producer.END + '\n')
    assert second['explanation'] in markdown
    assert second['fingerprint'] not in markdown
    for example in second['examples']:
        trace = '; '.join(
            f"{s['parent']} -> {', '.join(s['children'])}" for s in example['splits'])
        status = 'valid' if example['valid'] else 'invalid'
        assert f"- {example['id']}: {trace} [{status}]" in markdown


def test_markdown_preserves_supplied_data(monkeypatch):
    teaching = producer.build_teaching()
    teaching.update(source='supplied.source', explanation='Supplied explanation.')
    teaching['examples'] = [{
        'id': 'supplied', 'explanation': 'Custom example',
        'splits': [{'parent': 'CUSTOM', 'children': ['OTHER']}], 'valid': False,
    }]
    def forbidden():
        raise AssertionError('Supplied teaching must not be regenerated')
    monkeypatch.setattr(producer, 'build_teaching', forbidden)
    markdown = producer.render_markdown(teaching)
    assert 'Source: `supplied.source`' in markdown
    assert 'Supplied explanation.' in markdown
    assert '- supplied: CUSTOM -> OTHER [invalid]' in markdown
    with pytest.raises(KeyError):
        producer.render_markdown({})


def test_prose_uses_imported_policy_values(monkeypatch):
    monkeypatch.setattr(producer, 'MIN_CHILDREN', 4)
    monkeypatch.setattr(producer, 'DECOMPOSITION', {'ROOT': ('LEAF',), 'LEAF': ()})
    teaching = producer.build_teaching()
    assert teaching['rules'] == {'ROOT': ['LEAF'], 'LEAF': []}
    assert teaching['explanation'].startswith(
        'A ROOT splits into 4 or more LEAFs. A LEAF never splits.')
