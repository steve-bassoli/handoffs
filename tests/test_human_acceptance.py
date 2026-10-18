import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import RuleError, event_identity
from conftest import post_task, write


CLOSE = {'baseline': 'fixture-base', 'candidate': 'fixture-patch',
         'environment': 'isolated synthetic fixture',
         'evidence': 'Synthetic acceptance fixture; no live execution.'}
HUMAN = {'accepted': True, 'note': 'Explicit synthetic review',
         'review_basis': 'human-only'}
ERROR = 'Human acceptance requires a signed-in person'


@pytest.fixture
def strict_client(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    with TestClient(create_app(tmp_path / 'acceptance.sqlite')) as client:
        yield client


def login(client):
    client.app.state.credentials.set_password('steve', 'synthetic test password only')
    response = client.post('/api/v1/auth/login', json={
        'username': 'steve', 'password': 'synthetic test password only'})
    assert response.status_code == 200
    return response.json()


def headers(session):
    return {'Authorization': 'Bearer ' + session['access_token']}


def request(client, session, path, payload, key=None):
    return client.post('/api/v1' + path, json=payload,
                       headers={**headers(session), 'Idempotency-Key': key or str(uuid4())})


def claimed(client, session, proof=False):
    # Reuse the established post_task/write sequence with authenticated defaults.
    client.headers.update(headers(session))
    response = post_task(client, gold=10)
    assert response.status_code == 200, response.text
    task_id = response.json()['id']
    assert write(client, f'/tasks/{task_id}/take').status_code == 200
    if proof:
        profile = {'validation_scope': 'SIM', 'migration_stage': 'WRAP',
                   'baseline_revision': CLOSE['baseline'],
                   'candidate_revision': CLOSE['candidate'],
                   'environment': CLOSE['environment']}
        assert write(client, f'/tasks/{task_id}/profile', profile).status_code == 200
        upload = {'filename': 'evidence.txt', 'media_type': 'text/plain',
                  'content_base64': base64.b64encode(CLOSE['evidence'].encode()).decode(),
                  'description': 'Synthetic fixture evidence'}
        response = write(client, f'/tasks/{task_id}/proofs', upload)
        assert response.status_code == 200, response.text
    return task_id


def snapshot(client):
    # Compare all persisted application tables, not only projected task events.
    with client.app.state.service.db.engine.connect() as c:
        names = c.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").scalars().all()
        return {name: c.exec_driver_sql('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
                for name in names}


@pytest.mark.parametrize('route,payload', [('proof-human', HUMAN), ('close-human', CLOSE)])
@pytest.mark.parametrize('kind', ['relay', 'codex', 'agent'])
def test_nonhuman_refused_without_writes(strict_client, route, payload, kind):
    session = login(strict_client)
    task_id = claimed(strict_client, session, proof=route == 'proof-human')
    issued = strict_client.app.state.credentials.issue('steve', kind)
    before = snapshot(strict_client)
    response = request(strict_client, issued, f'/tasks/{task_id}/{route}', payload)
    assert response.status_code == 403, response.text
    assert response.json()['detail'] == ERROR
    assert snapshot(strict_client) == before


@pytest.mark.parametrize('route,payload', [('proof-human', HUMAN), ('close-human', CLOSE)])
def test_human_session_and_relay_cached_replay(strict_client, route, payload):
    session = login(strict_client)
    task_id = claimed(strict_client, session, proof=route == 'proof-human')
    relay = strict_client.app.state.credentials.issue('steve', 'relay')
    path = f'/tasks/{task_id}/{route}'
    key = str(uuid4())
    response = request(strict_client, session, path, payload, key)
    assert response.status_code == 200, response.text
    event = next(e for e in reversed(response.json()['events'])
                 if e['kind'] == 'proof_human_reviewed')
    assert event['actor'] == session['user_id']
    assert event['data']['principal'] == 'human'
    assert event['data']['principal_id'] == session['principal_id']
    assert event['data']['review_basis'] == 'human-only'
    before = snapshot(strict_client)
    response = request(strict_client, relay, path, payload, key)
    assert response.status_code == 403, response.text
    assert response.json()['detail'] == ERROR
    assert snapshot(strict_client) == before


@pytest.mark.parametrize('route,payload', [('proof-human', HUMAN), ('close-human', CLOSE)])
def test_demo_transition(client, route, payload):
    response = post_task(client, gold=10)
    assert response.status_code == 200
    task_id = response.json()['id']
    assert write(client, f'/tasks/{task_id}/take').status_code == 200
    # close-human supplies its own proof; use it to exercise allow-mode attribution.
    if route == 'proof-human':
        session = login(client)
        task_id = claimed(client, session, proof=True)
        client.headers.pop('Authorization')
    response = write(client, f'/tasks/{task_id}/{route}', payload)
    assert response.status_code == 200, response.text
    event = next(e for e in reversed(response.json()['events'])
                 if e['kind'] == 'proof_human_reviewed')
    assert event['actor'] == 'steve'
    assert event['data']['principal'] == 'demo-header'
    assert event['data']['principal_id'] == 'demo-header:steve'


@pytest.mark.parametrize('route,payload', [('proof-human', HUMAN), ('close-human', CLOSE)])
def test_strict_missing_or_demo_identity_refused(strict_client, route, payload):
    session = login(strict_client)
    task_id = claimed(strict_client, session, proof=route == 'proof-human')
    strict_client.headers.pop('Authorization')
    before = snapshot(strict_client)
    for identity_headers in ({}, {'X-Demo-User': 'steve'}):
        response = strict_client.post(f'/api/v1/tasks/{task_id}/{route}', json=payload,
                                     headers={'Idempotency-Key': str(uuid4()), **identity_headers})
        assert response.status_code == 401
        assert snapshot(strict_client) == before


@pytest.mark.parametrize('identity', [None, {
    'user_id': 'steve', 'principal': 'demo-header', 'principal_id': 'demo-header:steve'}])
def test_service_guard_fails_closed(strict_client, identity):
    token = event_identity.set(identity)
    try:
        with pytest.raises(RuleError) as error:
            strict_client.app.state.service.do_ai_proof_human(None, 'steve', {})
        assert error.value.status == 403
        assert error.value.message == ERROR
    finally:
        event_identity.reset(token)
