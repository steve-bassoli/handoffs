import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import RuleError
from app.signoffs import require_signoff


def test_signoff_authority_binding_and_single_use(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    with TestClient(create_app(tmp_path / 'signoffs.sqlite')) as client:
        credentials = client.app.state.credentials
        credentials.set_password('steve', 'a long test-only password')
        login = client.post('/api/v1/auth/login', json={'username': 'steve', 'password': 'a long test-only password'})
        assert login.status_code == 200
        human = {'Authorization': 'Bearer ' + login.json()['access_token']}
        relay = {'Authorization': 'Bearer ' + credentials.issue('steve', 'relay')['access_token'], 'X-Principal': 'human'}
        body = {'action': 'automation_mode', 'payload': {'mode': 'AUTO', 'target': 'test-only'}, 'summary': 'Test-only change'}
        assert client.post('/api/v1/signoffs', json=body).status_code == 401
        created = client.post('/api/v1/signoffs', json=body, headers=relay)
        assert created.status_code == 200
        sid = created.json()['id']
        decision = {'approved': True, 'note': 'Reviewed exact test payload'}
        endpoint = '/api/v1/signoffs/' + sid + '/decision'
        assert client.post(endpoint, json=decision, headers=relay).status_code == 403
        db = client.app.state.service.db
        def consume(action='automation_mode', payload=None, record=sid):
            with db.write() as c:
                return require_signoff(c, action, body['payload'] if payload is None else payload, signoff_id=record)
        with pytest.raises(RuleError):
            consume()
        assert client.get('/api/v1/signoffs', headers=human).json()[0]['payload_json']
        assert client.post(endpoint, json=decision, headers=human).status_code == 200
        assert client.post(endpoint, json=decision, headers=human).status_code == 409
        with pytest.raises(RuleError):
            consume(payload={'mode': 'MANUAL', 'target': 'test-only'})
        with pytest.raises(RuleError):
            consume(action='publish')
        with pytest.raises(RuleError):
            consume(record='missing')
        with pytest.raises(RuntimeError):
            with db.write() as c:
                require_signoff(c, body['action'], body['payload'], signoff_id=sid)
                raise RuntimeError('Simulated protected mutation failure')
        assert consume() == sid
        with pytest.raises(RuleError):
            consume()
        rejected = client.post('/api/v1/signoffs', json=body, headers=relay).json()['id']
        assert client.post('/api/v1/signoffs/' + rejected + '/decision', json={'approved': False, 'note': 'Declined'}, headers=human).status_code == 200
        with pytest.raises(RuleError):
            consume(record=rejected)


def test_prototype_flag_lets_relay_decide_but_marks_it_and_dies_with_the_flag(tmp_path, monkeypatch):
    import app.prototype as prototype
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    with TestClient(create_app(tmp_path / 'proto-signoffs.sqlite')) as client:
        credentials = client.app.state.credentials
        with pytest.raises(RuleError):
            credentials.issue('steve', 'human')  # Human sessions come only from password login.
        relay = {'Authorization': 'Bearer ' + credentials.issue('steve', 'relay')['access_token']}
        body = {'action': 'publish', 'payload': {'commit': 'abc'}, 'summary': 'Prototype publish'}
        sid = client.post('/api/v1/signoffs', json=body, headers=relay).json()['id']
        monkeypatch.setenv('ASE_PROTOTYPE_AUTO_SIGNOFF', 'on')
        decided = client.post('/api/v1/signoffs/' + sid + '/decision', json={'approved': True, 'note': 'auto'}, headers=relay)
        assert decided.status_code == 200 and decided.json()['decision_mode'] == 'prototype-auto'
        monkeypatch.delenv('ASE_PROTOTYPE_AUTO_SIGNOFF')
        with pytest.raises(RuleError):  # Once the flag is gone, prototype approvals stop counting.
            with client.app.state.service.db.write() as c:
                require_signoff(c, 'publish', body['payload'], signoff_id=sid)
        monkeypatch.setenv('ASE_PROTOTYPE_AUTO_SIGNOFF', 'on')
        with client.app.state.service.db.write() as c:
            assert require_signoff(c, 'publish', body['payload'], signoff_id=sid) == sid
