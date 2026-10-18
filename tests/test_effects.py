from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.effects import EFFECTS, classify, effect_table, gate_for
from app.main import create_app


REVERSIBLE = {'internal_work', 'post', 'edit', 'take', 'release', 'intake_screened', 'signoff.request'}
EXPECTED_KEYS = set('internal_work post edit take release administrative_close intake_screened intake_override intake_overridden close_human proof_human ai_proof_human signoff.request signoff.decision signoff.consume publish automation_mode spend_ceiling real_spending price_checkpoint rule_texts watson_real_data policy_adoption attach_package ai_reopen checkpoint status deliver settle cancel review accept ai_start ai_answer ai_retry ai_confirm ai_complete ai_proof_attach ai_proof_queue ai_proof_complete ai_profile ai_dependencies'.split())


def test_inventory():
    assert set(EFFECTS) == EXPECTED_KEYS


@pytest.mark.parametrize('action', sorted(EXPECTED_KEYS))
def test_every_catalog_row(action):
    row = classify(action)
    assert set(row) == {'reversibility', 'gate', 'reason'}
    assert row['reversibility'] == ('reversible' if action in REVERSIBLE else 'irreversible')
    assert row['gate'] and row['reason']
    assert gate_for(action) == row['gate']
    assert row == effect_table()[action]


@pytest.mark.parametrize('action', ['missing', '', 'POST', 'post,publish', 'post+rule_texts', None, 1, ['post', 'publish'], {'action': 'post', 'reversibility': 'reversible'}])
def test_unknown_or_mixed_fails_closed(action):
    assert classify(action)['reversibility'] == 'irreversible'
    assert gate_for(action) == 'human required'


@pytest.mark.parametrize('action', ['publish', 'rule_texts', 'close_human', 'ai_proof_human', 'unknown'])
def test_forged_request_tags_are_not_classifier_inputs(action):
    body = {'action': action, 'reversibility': 'reversible', 'gate': 'none', 'effects': ['post']}
    # Future callers must obtain this key from server dispatch, not body.action.
    server_action = action
    expected = classify(server_action)
    assert classify(server_action) == expected
    assert expected['reversibility'] == 'irreversible'
    assert classify(body)['gate'] == 'human required'
    body.update(action='post', reversibility='irreversible', gate='approved')
    assert classify(server_action) == expected


def test_returned_values_and_backing_table_are_immutable():
    before = classify('post')
    classify('post')['gate'] = 'forged'
    snapshot = effect_table()
    snapshot['post']['gate'] = 'forged'
    snapshot.clear()
    assert classify('post') == before
    with pytest.raises(TypeError):
        EFFECTS['post'] = {}
    with pytest.raises(TypeError):
        EFFECTS['post']['gate'] = 'forged'


@pytest.fixture
def client():
    # No lifespan: no database migration, seed or background recovery.
    app = create_app()
    app.state.credentials = SimpleNamespace(resolve=lambda token: {
        'user_id': 'test-reader', 'principal': 'human', 'principal_id': 'test-session'})
    return TestClient(app, headers={'Authorization': 'Bearer synthetic-test-token'})


def test_read_only_api(client):
    response = client.get('/api/v1/effects')
    assert response.status_code == 200
    expected = response.json()
    assert expected == effect_table()
    expected['rule_texts']['gate'] = 'forged'
    for method in ('post', 'put', 'patch', 'delete'):
        result = client.request(method, '/api/v1/effects', json=expected)
        assert result.status_code == 405
    assert client.get('/api/v1/effects').json() == effect_table()
    assert classify('rule_texts')['reversibility'] == 'irreversible'


def test_get_body_cannot_override_table(client):
    response = client.request('GET', '/api/v1/effects', json={
        'action': 'rule_texts', 'reversibility': 'reversible', 'gate': 'none'})
    assert response.status_code == 200
    assert response.json() == effect_table()


def test_existing_authentication_boundary_is_retained(client):
    client.app.state.demo_identity = 'refuse'
    response = client.get('/api/v1/effects', headers={'Authorization': ''})
    assert response.status_code == 401
