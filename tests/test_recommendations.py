import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    with TestClient(create_app(tmp_path / 'recommendations.sqlite')) as client:
        credentials = client.app.state.credentials
        credentials.set_password('steve', 'test-only long password')
        login = client.post('/api/v1/auth/login', json={
            'username': 'steve', 'password': 'test-only long password'})
        assert login.status_code == 200
        human = {'Authorization': 'Bearer ' + login.json()['access_token']}
        relay = {'Authorization': 'Bearer ' + credentials.issue('steve', 'relay')['access_token'],
                 'X-Principal': 'human'}
        yield client, human, relay


def body(revision='a' * 64, **updates):
    value = dict(item_kind='signoff', item_id='synthetic-item',
                 item_revision=revision, disposition='change',
                 rationale='Review synthetic work evidence.',
                 provenance={'source_ref': 'synthetic-fixture'},
                 requester_context='private synthetic work-context marker')
    value.update(updates)
    return value


def test_revision_supersession_and_reconstruction(setup):
    client, human, relay = setup
    endpoint = '/api/v1/recommendations'
    def get(revision):
        return client.get(endpoint + '/signoff/synthetic-item',
                          params={'revision': revision}, headers=human)
    assert get('a' * 64).json() == {'status': 'unavailable'}
    first = client.post(endpoint, json=body(), headers=relay)
    assert first.status_code == 200
    first_id = first.json()['id']
    shown = get('a' * 64)
    assert shown.status_code == 200
    assert shown.json()['id'] == first_id
    assert shown.json()['created_principal'] == 'relay'
    assert shown.headers['cache-control'] == 'no-store'
    assert 'requester_context' not in shown.json()
    assert 'provenance_json' not in shown.json()
    assert 'private synthetic work-context marker' not in shown.text
    assert get('b' * 64).json() == {'status': 'unavailable'}
    second = client.post(endpoint, json=body(disposition='yes'), headers=human)
    assert second.status_code == 200
    second_id = second.json()['id']
    assert get('a' * 64).json()['id'] == second_id
    third = client.post(endpoint, json=body('b' * 64), headers=relay)
    assert third.status_code == 200
    assert get('a' * 64).json() == {'status': 'unavailable'}
    assert get('b' * 64).json()['id'] == third.json()['id']
    with client.app.state.service.db.engine.connect() as c:
        rows = {r['id']: dict(r) for r in c.exec_driver_sql(
            'SELECT * FROM recommendations').mappings()}
    assert rows[first_id]['superseded_by'] == second_id
    assert rows[second_id]['superseded_by'] == third.json()['id']
    assert rows[first_id]['item_revision'] == 'a' * 64
    assert rows[first_id]['disposition'] == 'change'
    assert json.loads(rows[first_id]['provenance_json'])['author']['principal'] == 'relay'
    assert rows[first_id]['requester_context'] == body()['requester_context']


def test_access_and_validation(setup):
    client, human, relay = setup
    endpoint = '/api/v1/recommendations'
    assert client.post(endpoint, json=body()).status_code == 401
    assert client.post(endpoint, json=body(), headers={'X-Demo-User': 'steve'}).status_code == 401
    assert client.get(endpoint + '/signoff/synthetic-item', params={'revision': 'a' * 64}).status_code == 401
    for changes in ({'item_revision': 'not-a-digest'}, {'disposition': 'approved'},
                    {'item_kind': 'unknown'}, {'created_principal': 'human'}):
        assert client.post(endpoint, json=body(**changes), headers=relay).status_code == 422
    assert client.get(endpoint + '/signoff/synthetic-item',
                      params={'revision': 'bad'}, headers=human).status_code == 422


@pytest.mark.parametrize('kind', ['signoff', 'intake_veto', 'human_close', 'policy_decision'])
def test_kinds_remain_distinct(setup, kind):
    client, human, relay = setup
    result = client.post('/api/v1/recommendations', json=body(item_kind=kind), headers=relay)
    assert result.status_code == 200
    for other in {'signoff', 'intake_veto', 'human_close', 'policy_decision'} - {kind}:
        result = client.get('/api/v1/recommendations/' + other + '/synthetic-item',
                            params={'revision': 'a' * 64}, headers=human)
        assert result.json() == {'status': 'unavailable'}
