"""Construction mode (task eabd11e7): one switch takes the whole door off; the default keeps every lock."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.prototype as prototype
from app.main import create_app

CLOSE = {'baseline': 'a', 'candidate': 'b', 'environment': 'door fixture', 'evidence': 'Synthetic door fixture.'}


class VetoScreen:
    def screen(self, text):
        return {'verdict': 'veto', 'reason': 'Synthetic veto', 'model': 'fixture', 'policy_sha256': 'fixture'}


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    monkeypatch.delenv('ASE_PROTOTYPE_AUTO_SIGNOFF', raising=False)
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', 'enforce')

    def make(door):
        if door:
            monkeypatch.setenv('ASE_DOOR', door)
        else:
            monkeypatch.delenv('ASE_DOOR', raising=False)
        return TestClient(create_app(tmp_path / f'door-{door}.sqlite', intake_screen=VetoScreen()))
    return make


def write(client, path, body, headers):
    return client.post('/api/v1' + path, json=body, headers={**headers, 'Idempotency-Key': str(uuid4()), 'X-Action-Intent': 'user-directed'})


def test_door_on_by_default_keeps_every_lock(board):
    with board(None) as client:
        assert client.get('/health').json()['door'] == 'on'
        assert write(client, '/tasks', {'title': 't', 'goal': 'g', 'criteria': ['c'], 'gold': 1}, {'X-Demo-User': 'steve'}).status_code == 401
        relay = {'Authorization': 'Bearer ' + client.app.state.credentials.issue('steve', 'relay')['access_token']}
        task = write(client, '/tasks', {'title': 't', 'goal': 'g', 'criteria': ['c'], 'gold': 1, 'complexity': 'LOW'}, relay).json()
        assert task['status'] == 'blocked'  # Enforced intake veto.


def test_door_off_lets_the_furniture_in_and_labels_it(board):
    with board('off') as client:
        assert client.get('/health').json()['door'] == 'off'
        demo = {'X-Demo-User': 'steve'}
        task = write(client, '/tasks', {'title': 't', 'goal': 'g', 'criteria': ['c'], 'gold': 1, 'complexity': 'LOW'}, demo).json()
        assert task['status'] == 'open'  # Veto recorded, not blocking.
        assert write(client, f"/tasks/{task['id']}/take", {}, demo).status_code == 200
        relay = {'Authorization': 'Bearer ' + client.app.state.credentials.issue('steve', 'relay')['access_token']}
        closed = write(client, f"/tasks/{task['id']}/close-human", CLOSE, relay)
        assert closed.status_code == 200, closed.text
        accepted = [e for e in closed.json()['events'] if e['kind'] == 'proof_human_reviewed'][-1]['data']
        assert accepted['signoff'] == 'door-off' and accepted['principal'] == 'relay'


def test_door_cannot_outlive_the_cutoff_or_a_release(board, tmp_path, monkeypatch):
    monkeypatch.setenv('ASE_DOOR', 'off')
    assert prototype.door_off(datetime(2026, 10, 31, tzinfo=timezone.utc)) is True
    assert prototype.door_off(prototype.HARD_CUTOFF) is False
    (tmp_path / 'RELEASED').write_text('released')
    assert prototype.door_off(datetime(2026, 10, 20, tzinfo=timezone.utc)) is False


def test_banner_and_health_say_when_the_door_is_off():
    static = Path(__file__).resolve().parents[1] / 'app' / 'static'
    assert 'id="door-banner"' in (static / 'index.html').read_text(encoding='utf-8')
    assert "h.door !== 'off'" in (static / 'app.js').read_text(encoding='utf-8')
