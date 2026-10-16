import base64
import copy

import pytest

from app.proofs import binding, decode_upload, validate_review


def upload(text='Observed actual result; supplied fixture only.'):
    return {'filename': 'proof.txt', 'media_type': 'text/plain',
            'content_base64': base64.b64encode(text.encode()).decode(), 'description': 'Observed evidence'}


def test_one_proof_is_focused_and_cannot_be_an_executable_path_or_secret():
    proof, raw = decode_upload(upload())
    assert raw and proof.filename == 'proof.txt'
    for changed in [{'filename': '../proof.txt'}, {'media_type': 'image/png'}, {'content_base64': 'not base64'},
                    {'content_base64': base64.b64encode(b'sk-proj-secret').decode()}]:
        with pytest.raises(ValueError):
            decode_upload({**upload(), **changed})


def test_binding_changes_on_candidate_criteria_or_dependency_evidence_change():
    task = {'id': 'one', 'goal': 'Read', 'criteria': ['Matches'], 'repository': 'repo', 'events': [],
            'profile': {'candidate_revision': 'one'}}
    original = binding(task)
    changed = copy.deepcopy(task)
    changed['profile']['candidate_revision'] = 'two'
    assert binding(changed) != original
    assert binding({**task, 'criteria': ['Different']}) != original
    assert binding(task, [{'id': 'setup', 'proof': 'first'}]) != binding(task, [{'id': 'setup', 'proof': 'second'}])


def test_review_must_cover_each_criterion_and_cannot_hide_inconclusive_result():
    result = {'verdict': 'pass', 'reason': 'Evidence supports the criterion',
              'criteria': [{'index': 0, 'verdict': 'pass', 'reason': 'Observed'}]}
    assert validate_review(result, 1)['verdict'] == 'pass'
    with pytest.raises(ValueError):
        validate_review(result, 2)
    result['criteria'][0]['verdict'] = 'inconclusive'
    with pytest.raises(ValueError):
        validate_review(result, 1)
