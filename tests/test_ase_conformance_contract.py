"""Independent contract assertions; proposed checks, not execution evidence."""
import hashlib
import json
import os
from pathlib import Path
import re

import pytest

from app import ase_conformance as producer

DOC = Path(__file__).resolve().parents[1] / 'docs/ase_conformance_contract.md'
IDS = ['decomposition', 'human_gates', 'humane_limits']
ROW_KEYS = {'id', 'status', 'scope', 'reason', 'evidence', 'conflicts'}


def block(label):
    text = DOC.read_text(encoding='utf-8')
    matches = re.findall(r'^```' + re.escape(label) + r'\n(.*?)^```',
                         text, flags=re.M | re.S)
    assert len(matches) == 1, label
    return matches[0]


def model(label):
    return json.loads(block(label))


def coverage(card):
    assert set(card) == {'schema_version', 'scope', 'properties', 'limitations'}
    assert card['schema_version'] == 'ase-narrow-v1'
    assert [row['id'] for row in card['properties']] == IDS
    for row in card['properties']:
        assert set(row) == ROW_KEYS
        assert row['status'] in {'pass', 'partial', 'gap'}
        assert row['scope'] and row['reason']
        assert isinstance(row['evidence'], list)
        assert isinstance(row['conflicts'], list)
        if row['conflicts']:
            assert row['status'] != 'pass'
        if row['status'] == 'pass':
            assert row['evidence']
    for row in card['properties'][1:]:
        assert row['status'] != 'pass'


def decomposition(card):
    coverage(card)
    return card['properties'][0]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprints_match(row, root):
    assert row['evidence'], 'No source fingerprint evidence'
    for evidence in row['evidence']:
        assert evidence['path'] == 'app/complexity.py'
        assert evidence['sha256'] == digest((root / evidence['path']).read_bytes())


def seed(root):
    path = root / 'app/complexity.py'
    path.parent.mkdir(parents=True)
    path.write_bytes(block('ase-source').encode('utf-8'))
    return path


def baseline(root):
    path = seed(root)
    row = decomposition(producer.build_scorecard(root))
    assert row['status'] == 'pass', row
    fingerprints_match(row, root)
    return path, row


def normalize_empty_root(card, root):
    # Normalize decoded values, not serialized JSON with escaped backslashes.
    normalized = json.loads(json.dumps(card))
    expected_scope = 'Selected checkout: ' + os.path.abspath(os.fspath(root))
    for row in normalized['properties']:
        assert row['scope'] == expected_scope
        row['scope'] = 'Selected checkout: <fixture-root>'
    return normalized


@pytest.mark.parametrize('fallback', [False, True])
def test_canonical_and_generated_empty_root(tmp_path, monkeypatch, fallback):
    if fallback:
        monkeypatch.setattr(producer, '_descriptor_reads_available', lambda: False)
    fixture = model('ase-fixture')
    coverage(fixture)
    assert all(r['status'] == 'gap' and not r['evidence']
               for r in fixture['properties'])
    expected = model('ase-expected')
    assert model('ase-generated') == expected
    actual = producer.build_scorecard(tmp_path)
    coverage(actual)
    assert normalize_empty_root(actual, tmp_path) == expected


def test_behavior_and_exact_source_fingerprints(tmp_path):
    path, row = baseline(tmp_path)
    raw = path.read_bytes()
    validate = producer._extract_validator(raw, digest(raw))
    assert validate('HIGH', ['MEDIUM', 'MEDIUM']) == 'MEDIUM'
    assert validate('HIGH', ['HIGH', 'HIGH']) == 'HIGH'
    assert validate('MEDIUM', ['LOW', 'LOW']) == 'LOW'
    for parent, levels in [('LOW', ['LOW', 'LOW']),
                           ('HIGH', ['HIGH', 'MEDIUM']), ('HIGH', ['HIGH'])]:
        with pytest.raises(ValueError):
            validate(parent, levels)
    with pytest.raises(ValueError):
        producer._extract_validator(raw, '0' * 64)


def test_stale_saved_evidence_fails(tmp_path):
    path, saved = baseline(tmp_path)
    path.write_bytes(path.read_bytes() + b'\n# changed temporary evidence\n')
    with pytest.raises(AssertionError):
        fingerprints_match(saved, tmp_path)


def test_unsupported_source_cannot_pass(tmp_path):
    path = seed(tmp_path)
    path.write_text('def unrelated():\n    return True\n', encoding='utf-8')
    row = decomposition(producer.build_scorecard(tmp_path))
    assert row['status'] != 'pass'


@pytest.mark.parametrize('accept_all', [True, False])
def test_broken_validator_cannot_pass(tmp_path, monkeypatch, accept_all):
    baseline(tmp_path)

    def broken(parent, levels):
        if accept_all:
            return levels[0] if levels else 'LOW'
        raise ValueError('intentionally broken temporary validator')

    monkeypatch.setattr(producer, '_extract_validator', lambda *args: broken)
    assert decomposition(producer.build_scorecard(tmp_path))['status'] != 'pass'
