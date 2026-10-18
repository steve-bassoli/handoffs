import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import one

PAYLOAD = {'title': 'Authenticated write', 'goal': 'Verify attribution',
           'criteria': ['Identity is authenticated'], 'gold': 1, 'complexity': 'LOW'}


@pytest.fixture
def secure_client(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    with TestClient(create_app(tmp_path / 'auth.sqlite')) as client:
        yield client


def post(client, headers=None, path='/api/v1/tasks'):
    return client.post(path, json=PAYLOAD,
                       headers={'Idempotency-Key': str(uuid4()), **(headers or {})})


def test_refuse_missing_and_demo_only(secure_client):
    for headers in ({}, {'X-Demo-User': 'steve'}):
        assert post(secure_client, headers).status_code == 401
        assert post(secure_client, headers, '/api/v1/bounties').status_code == 401
    with secure_client.app.state.service.db.engine.connect() as c:
        assert one(c, 'SELECT COUNT(*) AS n FROM tasks')['n'] == 0


def test_login_existing_user_and_logout(secure_client):
    credentials = secure_client.app.state.credentials
    credentials.set_password('steve', 'a long test-only password')
    assert secure_client.post('/api/v1/auth/login', json={'username': 'steve', 'password': 'wrong'}).status_code == 401
    response = secure_client.post('/api/v1/auth/login', json={'username': 'STEVE', 'password': 'a long test-only password'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    session = response.json()
    headers = {'Authorization': 'Bearer ' + session['access_token'], 'X-Demo-User': 'nate'}
    result = post(secure_client, headers)
    assert result.status_code == 200
    assert result.json()['creator'] == 'steve'
    assert result.json()['events'][-1]['data']['principal'] == 'human'
    assert secure_client.post('/api/v1/auth/logout', headers=headers).status_code == 200
    assert post(secure_client, headers).status_code == 401


@pytest.mark.parametrize('kind', ['relay', 'codex', 'agent'])
def test_distinct_principal_and_hashed_storage(secure_client, kind):
    credentials = secure_client.app.state.credentials
    issued = credentials.issue('steve', kind)
    headers = {'Authorization': 'Bearer ' + issued['access_token'],
               'X-Demo-User': 'nate', 'X-Principal': 'human'}
    result = post(secure_client, headers)
    assert result.status_code == 200
    event = result.json()['events'][-1]
    assert event['actor'] == 'steve'
    assert event['data']['principal'] == kind
    assert event['data']['principal_id'] == issued['principal_id']
    with credentials.db.engine.connect() as c:
        row = one(c, 'SELECT * FROM principal_tokens WHERE id=?', (issued['principal_id'],))
    assert row['token_hash'] == hashlib.sha256(issued['access_token'].encode()).hexdigest()
    assert issued['access_token'] not in str(row)
    credentials.revoke(issued['principal_id'])
    assert post(secure_client, headers).status_code == 401


def test_expired_token(secure_client):
    credentials = secure_client.app.state.credentials
    issued = credentials.issue('steve', 'agent')
    with credentials.db.write() as c:
        c.exec_driver_sql('UPDATE principal_tokens SET expires_at=0 WHERE id=?', (issued['principal_id'],))
    assert post(secure_client, {'Authorization': 'Bearer ' + issued['access_token']}).status_code == 401


def test_demo_transition_and_no_bad_bearer_fallback(client):
    result = post(client, {'X-Demo-User': 'nate'})
    assert result.status_code == 200
    assert result.json()['creator'] == 'nate'
    assert result.json()['events'][-1]['data']['principal'] == 'demo-header'
    assert post(client, {'Authorization': 'Bearer invalid', 'X-Demo-User': 'steve'}).status_code == 401


def test_password_reset_revokes_sessions(secure_client):
    credentials = secure_client.app.state.credentials
    credentials.set_password('steve', 'first test-only password')
    issued = credentials.login('steve', 'first test-only password')
    credentials.set_password('steve', 'second test-only password')
    assert post(secure_client, {'Authorization': 'Bearer ' + issued['access_token']}).status_code == 401
    with credentials.db.engine.connect() as c:
        row = one(c, 'SELECT * FROM human_passwords WHERE user_id=?', ('steve',))
    assert row['password_hash'] != 'second test-only password'
    assert row['iterations'] >= 600000
