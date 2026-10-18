"""Generated-block drift and source-change checks, not deployment proof."""
import hashlib
import json
from pathlib import Path
import re

import pytest

from app.ase_adoption import build_adoption
from app.ase_definition import build_definition
from app.ase_conformance import build_scorecard

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs/ase_adoption.md'
CONFORMANCE_DOC = ROOT / 'docs/ase_conformance_contract.md'


def block(document, label):
    matches = re.findall(r'^```' + re.escape(label) + r'\n(.*?)^```',
                         document.read_text(encoding='utf-8'), re.M | re.S)
    assert len(matches) == 1, label
    return matches[0]


def claims(model):
    return {'definition': model['definition'],
            'capabilities': [{key: row[key] for key in
                              ('id', 'label', 'property_refs', 'status', 'evidence', 'conflicts')}
                             for row in model['capabilities']]}


def assert_claims_current(saved, current):
    assert saved == claims(current), 'Stale claims or fingerprints: regenerate and review'


def model(root):
    return build_adoption(build_definition(), build_scorecard(root))


def seed(root):
    # Independently documented source, not the producer's exported template.
    path = root / 'app/complexity.py'
    path.parent.mkdir(parents=True)
    path.write_bytes(block(CONFORMANCE_DOC, 'ase-source').encode('utf-8'))
    return path


def test_generated_claims_and_checklist_match_models(tmp_path):
    adoption = model(tmp_path)
    generated = json.loads(block(DOC, 'ase-adoption-claims'))
    assert_claims_current(generated, adoption)
    assert [r['status'] for r in generated['capabilities']] == ['gap'] * 3
    assert all(not r['evidence'] for r in generated['capabilities'])
    assert json.loads(block(DOC, 'ase-adoption-checklist')) == adoption['workflow']
    properties = {p['id']: p for p in build_definition()['properties']}
    for row in adoption['capabilities']:
        assert row['properties'] == [properties[ref] for ref in row['property_refs']]
        assert row['label'] == row['id'].replace('_', ' ').title()


def test_changed_source_invalidates_saved_fingerprints_even_if_probe_still_passes(tmp_path):
    path = seed(tmp_path)
    original = model(tmp_path)
    assert original['capabilities'][0]['status'] == 'pass'
    saved = claims(original)
    path.write_bytes(path.read_bytes() + b'\n# changed synthetic source evidence\n')
    refreshed = model(tmp_path)
    assert refreshed['capabilities'][0]['status'] == 'pass'
    assert saved['capabilities'][0]['evidence'] != refreshed['capabilities'][0]['evidence']
    expected_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert all(e['sha256'] == expected_digest for e in refreshed['capabilities'][0]['evidence'])
    with pytest.raises(AssertionError, match='Stale claims'):
        assert_claims_current(saved, refreshed)


def test_changed_code_cannot_leave_stronger_stale_claims(tmp_path):
    path = seed(tmp_path)
    saved = claims(model(tmp_path))
    assert saved['capabilities'][0]['status'] == 'pass'
    path.write_bytes(b'def unrelated():\n    return True\n')
    refreshed = model(tmp_path)
    assert refreshed['capabilities'][0]['status'] == 'partial'
    with pytest.raises(AssertionError, match='Stale claims'):
        assert_claims_current(saved, refreshed)
    # Even the guide's conservative empty-root block is fixture-specific,
    # not reusable as a current source-bound result.
    documented = json.loads(block(DOC, 'ase-adoption-claims'))
    with pytest.raises(AssertionError, match='Stale claims'):
        assert_claims_current(documented, refreshed)


def test_definition_changes_cannot_leave_stale_doc_claims(tmp_path):
    definition = build_definition()
    definition['definition'] += ' Changed proposal.'
    changed = build_adoption(definition, build_scorecard(tmp_path))
    documented = json.loads(block(DOC, 'ase-adoption-claims'))
    with pytest.raises(AssertionError, match='Stale claims'):
        assert_claims_current(documented, changed)


def test_guide_preserves_human_boundaries_and_reading_policy():
    text = DOC.read_text(encoding='utf-8')
    for phrase in ('REST preserves access and recognition',
                   'Appreciation does not buy authority',
                   'Unresolved evidence is not human acceptance',
                   'No-personal-quota reading policy',
                   'without buying AI access', 'work-only REST checkpoint',
                   'No launch,', 'UNEXECUTED', 'not a pass',
                   'no Windows/POSIX platform skips'):
        assert phrase in text
    assert 'python -m pytest -q tests/test_ase_adoption.py' in text
    assert 'python -m app.ase_conformance --repo-root .' in text
