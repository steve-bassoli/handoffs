"""CONTRACT_V1: authoritative fixture and reference drift checks; no runtime consumer."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.complexity import DECOMPOSITION, MIN_CHILDREN, validate_bounty_split
from app.decomposition_teaching import build_teaching, render_markdown

BEGIN = '<!-- BEGIN GENERATED DECOMPOSITION_TEACHING V1 -->'
END = '<!-- END GENERATED DECOMPOSITION_TEACHING V1 -->'
ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ('docs/decomposition_rule.md',
              'skills/handoffs/references/decomposition-rule.md')
FIXTURE = {
    'version': 1,
    'source': 'app.complexity:DECOMPOSITION,MIN_CHILDREN,validate_bounty_split',
    'min_children': 2,
    'rules': {'HIGH': ['HIGH', 'MEDIUM'], 'MEDIUM': ['LOW'], 'LOW': []},
    'explanation': (
        'A HIGH splits into two or more HIGHs or two or more MEDIUMs, never a mix. '
        'A MEDIUM splits into two or more LOWs. A LOW never splits. '
        'HIGH-to-HIGH decomposition may repeat. Counts follow grounded work, '
        'not a fixed three. Structural examples do not authorize agent launches.'),
    'examples': [
        {'id': 'high-two-medium', 'explanation': 'Two MEDIUM children are valid.',
         'splits': [{'parent': 'HIGH', 'children': ['MEDIUM', 'MEDIUM']}], 'valid': True},
        {'id': 'medium-four-low', 'explanation': 'Four LOW children are valid.',
         'splits': [{'parent': 'MEDIUM', 'children': ['LOW'] * 4}], 'valid': True},
        {'id': 'high-repeat',
         'explanation': 'A HIGH child may itself split into HIGH children.',
         'splits': [{'parent': 'HIGH', 'children': ['HIGH', 'HIGH']},
                    {'parent': 'HIGH', 'children': ['HIGH', 'HIGH']}], 'valid': True},
        {'id': 'high-mixed', 'explanation': 'Mixed HIGH and MEDIUM children are invalid.',
         'splits': [{'parent': 'HIGH', 'children': ['HIGH', 'MEDIUM']}], 'valid': False},
        {'id': 'low-split', 'explanation': 'LOW children cannot be created beneath a LOW.',
         'splits': [{'parent': 'LOW', 'children': ['LOW', 'LOW']}], 'valid': False},
        {'id': 'high-single', 'explanation': 'One child is not a split.',
         'splits': [{'parent': 'HIGH', 'children': ['HIGH']}], 'valid': False},
    ],
    'fingerprint': '0' * 64,  # Shape sentinel only, not the generated digest.
}


def semantic_digest(teaching):
    semantics = {key: teaching[key] for key in ('rules', 'min_children')}
    payload = json.dumps(semantics, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def split_valid(split):
    try:
        validate_bounty_split(split['parent'], split['children'])
    except ValueError:
        return False
    return True


def assert_teaching(teaching):
    expected = copy.deepcopy(FIXTURE)
    expected['fingerprint'] = semantic_digest(expected)
    assert type(teaching['version']) is int
    assert type(teaching['min_children']) is int
    assert teaching == expected
    assert teaching['fingerprint'] == semantic_digest(teaching)
    assert teaching['rules'] == {key: list(value) for key, value in DECOMPOSITION.items()}
    assert teaching['min_children'] == MIN_CHILDREN
    for example in teaching['examples']:
        assert type(example['valid']) is bool
        assert example['valid'] is all(split_valid(split) for split in example['splits'])


def extract_block(text):
    text = text.replace('\r\n', '\n')
    assert text.count(BEGIN) == text.count(END) == 1
    start, finish = text.index(BEGIN), text.index(END)
    assert start < finish
    return text[start:finish + len(END)]


def assert_reference(text):
    teaching = build_teaching()
    assert_teaching(teaching)
    generated = render_markdown(teaching)
    assert generated.endswith('\n') and not generated.endswith('\n\n')
    assert extract_block(generated) == generated[:-1]
    assert extract_block(text) == generated[:-1]


def test_contract_and_default_renderer():
    teaching = build_teaching()
    assert_teaching(teaching)
    assert render_markdown() == render_markdown(teaching)
    assert render_markdown(None) == render_markdown(teaching)


@pytest.mark.parametrize('relative', REFERENCES)
def test_real_references(relative):
    text = (ROOT / relative).read_text(encoding='utf-8')
    assert_reference(text)
    assert_reference(text.replace('\n', '\r\n'))


@pytest.mark.parametrize('mutation', [
    lambda text: text.replace('never a mix', 'mix freely'),
    lambda text: text.replace('two or more', 'exactly three'),
    lambda text: text.replace(BEGIN, ''),
    lambda text: text.replace(END, ''),
    lambda text: text + '\n' + BEGIN,
    lambda text: text + '\n' + END,
    lambda text: text.replace(BEGIN, '__SWAP__').replace(END, BEGIN).replace('__SWAP__', END),
])
def test_reference_mutations_fail(mutation):
    text = (ROOT / REFERENCES[0]).read_text(encoding='utf-8')
    with pytest.raises(AssertionError):
        assert_reference(mutation(text))


@pytest.mark.parametrize('field,value', [
    ('explanation', 'Every parent must have exactly three children.'),
    ('min_children', 3),
    ('rules', {'HIGH': ['LOW'], 'MEDIUM': ['LOW'], 'LOW': []}),
    ('fingerprint', '0' * 64),
    ('version', True),
])
def test_payload_mutations_fail(field, value):
    teaching = copy.deepcopy(build_teaching())
    teaching[field] = value
    with pytest.raises(AssertionError):
        assert_teaching(teaching)


def test_example_outcome_mutation_fails():
    teaching = copy.deepcopy(build_teaching())
    teaching['examples'][0]['valid'] = False
    with pytest.raises(AssertionError):
        assert_teaching(teaching)
