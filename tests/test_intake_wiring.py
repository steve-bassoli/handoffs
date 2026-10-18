from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.intake_screen import canonical_text, text_sha256
from conftest import post_task, write


class Screen:
    def __init__(self, verdict='pass'):
        self.verdict = verdict
        self.calls = []

    def screen(self, text):
        self.calls.append(text)
        return {'verdict': self.verdict, 'reason': 'Synthetic ' + self.verdict,
                'model': 'test-intake', 'policy_sha256': 'test-policy'}


@pytest.fixture
def setup_client(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'allow')
    def build(mode='enforce', verdict='pass'):
        monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', mode)
        screen = Screen(verdict)
        return TestClient(create_app(tmp_path / (str(uuid4()) + '.sqlite'), intake_screen=screen)), screen
    return build


def screened(task):
    return [e for e in task['events'] if e['kind'] == 'intake_screened']


def human(client):
    client.app.state.credentials.set_password('steve', 'synthetic password only')
    response = client.post('/api/v1/auth/login', json={
        'username': 'steve', 'password': 'synthetic password only'})
    assert response.status_code == 200
    return response.json()


def override(client, task_id, session, key=None):
    return client.post('/api/v1/tasks/' + task_id + '/intake-override',
                       json={'note': 'Explicit synthetic human decision'},
                       headers={'Authorization': 'Bearer ' + session['access_token'],
                                'Idempotency-Key': key or str(uuid4())})


@pytest.mark.parametrize('verdict', ['veto', 'unavailable'])
def test_enforce_post_blocks_and_records(setup_client, verdict):
    client, screen = setup_client(verdict=verdict)
    with client:
        response = post_task(client, gold=10)
        assert response.status_code == 200
        task = response.json()
        assert task['status'] == 'blocked'
        event = screened(task)[-1]['data']
        assert event['verdict'] == verdict
        assert event['reason'] == 'Synthetic ' + verdict
        assert event['mode'] == 'enforce'
        assert event['model'] == 'test-intake'
        assert event['policy_sha256'] == 'test-policy'
        assert event['text_sha256'] == text_sha256(canonical_text(task))
        assert len(screen.calls) == 1


@pytest.mark.parametrize('verdict', ['veto', 'unavailable'])
def test_enforce_take_refusal_is_durable(setup_client, verdict):
    client, screen = setup_client()
    with client:
        task = post_task(client, gold=10).json()
        screen.verdict = verdict
        response = write(client, '/tasks/' + task['id'] + '/take')
        assert response.status_code == 403
        assert response.json()['detail'] == 'Intake screen: Synthetic ' + verdict
        current = client.get('/api/v1/tasks/' + task['id']).json()
        assert current['status'] == 'open'
        assert current['claimant'] is None
        assert screened(current)[-1]['data']['verdict'] == verdict
        assert len(screen.calls) == 2


@pytest.mark.parametrize('verdict', ['pass', 'veto', 'unavailable'])
def test_observe_records_without_blocking(setup_client, verdict):
    client, screen = setup_client(mode='observe', verdict=verdict)
    with client:
        task = post_task(client, gold=10).json()
        assert task['status'] == 'open'
        response = write(client, '/tasks/' + task['id'] + '/take')
        assert response.status_code == 200
        assert response.json()['status'] == 'working'
        assert len(screened(response.json())) == 2
        assert all(e['data']['mode'] == 'observe' for e in screened(response.json()))


@pytest.mark.parametrize('mode', ['enforce', 'off'])
def test_pass_and_off(setup_client, mode):
    client, screen = setup_client(mode=mode)
    with client:
        task = post_task(client, gold=10).json()
        response = write(client, '/tasks/' + task['id'] + '/take')
        assert response.status_code == 200
        assert response.json()['status'] == 'working'
        assert len(screen.calls) == (0 if mode == 'off' else 2)
        assert len(screened(response.json())) == (0 if mode == 'off' else 2)


def test_human_override_and_nonhuman_cached_replay(setup_client, monkeypatch):
    monkeypatch.setenv('ASE_PROTOTYPE_AUTO_SIGNOFF', 'on')
    client, screen = setup_client(verdict='veto')
    with client:
        task = post_task(client, gold=10).json()
        session = human(client)
        key = str(uuid4())
        response = override(client, task['id'], session, key)
        assert response.status_code == 200
        current = response.json()
        assert current['status'] == 'open'
        event = current['events'][-1]
        assert event['kind'] == 'intake_overridden'
        assert event['data']['principal'] == 'human'
        assert event['data']['principal_id'] == session['principal_id']
        assert event['data']['overridden_by'] == 'steve'
        assert event['data']['note'] == 'Explicit synthetic human decision'
        assert event['data']['text_sha256'] == text_sha256(canonical_text(task))
        before = current['events']
        for kind in ('relay', 'codex', 'agent'):
            issued = client.app.state.credentials.issue('steve', kind)
            assert override(client, task['id'], issued, key).status_code == 403
        assert write(client, '/tasks/' + task['id'] + '/intake-override', {'note': 'demo'}).status_code == 403
        assert client.get('/api/v1/tasks/' + task['id']).json()['events'] == before
        assert write(client, '/tasks/' + task['id'] + '/take').status_code == 200
        assert screen.verdict == 'veto'


def test_changed_text_does_not_inherit_override(setup_client):
    client, screen = setup_client(verdict='veto')
    with client:
        task = post_task(client, gold=10).json()
        assert override(client, task['id'], human(client)).status_code == 200
        fields = {k: task[k] for k in ('title', 'goal', 'criteria', 'repository',
                  'context_links', 'gold', 'target', 'complexity', 'work_type')}
        fields['goal'] = 'Different synthetic goal'
        assert write(client, '/tasks/' + task['id'] + '/edit', fields).status_code == 200
        assert write(client, '/tasks/' + task['id'] + '/take').status_code == 403


def test_accept_cannot_bypass_veto(setup_client):
    client, screen = setup_client()
    with client:
        task = post_task(client, gold=10).json()
        screen.verdict = 'veto'
        response = write(client, '/tasks/' + task['id'] + '/accept', {})
        assert response.status_code == 403
        task = client.get('/api/v1/tasks/' + task['id']).json()
        assert task['claimant'] is None
        assert task['ai_run'] is None
        assert screened(task)[-1]['data']['verdict'] == 'veto'


def test_cached_post_does_not_rescreen(setup_client):
    client, screen = setup_client()
    with client:
        key = str(uuid4())
        first = post_task(client, gold=10, key=key)
        second = post_task(client, gold=10, key=key)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert len(screen.calls) == 1
