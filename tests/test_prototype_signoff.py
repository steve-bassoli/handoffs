"""Prototype auto sign-off (task e3c65ba2): off by default, labelled when used, dead after the cutoff or release."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.prototype as prototype
from app.main import create_app

CLOSE = {'baseline': 'fixture-base', 'candidate': 'fixture-patch', 'environment': 'isolated synthetic fixture',
         'evidence': 'Synthetic fixture; no live execution.'}


@pytest.fixture
def relay(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    with TestClient(create_app(tmp_path / 'proto.sqlite')) as client:
        token = client.app.state.credentials.issue('steve', 'relay')['access_token']
        client.headers.update({'Authorization': 'Bearer ' + token})
        yield client


def write(client, path, body=None):
    return client.post('/api/v1' + path, json=body or {}, headers={'Idempotency-Key': str(uuid4()), 'X-Action-Intent': 'user-directed'})


def close(client):
    task = write(client, '/tasks', {'title': 'Proto', 'goal': 'g', 'criteria': ['c'], 'gold': 5, 'complexity': 'LOW'}).json()['id']
    assert write(client, f'/tasks/{task}/take').status_code == 200
    return write(client, f'/tasks/{task}/close-human', CLOSE)


def test_off_by_default_refuses_relay(relay, monkeypatch):
    monkeypatch.delenv('ASE_PROTOTYPE_AUTO_SIGNOFF', raising=False)
    assert close(relay).status_code == 403
    assert relay.get('/health').json()['prototype_auto_signoff'] is False


def test_on_lets_relay_accept_and_labels_every_event(relay, monkeypatch):
    monkeypatch.setenv('ASE_PROTOTYPE_AUTO_SIGNOFF', 'on')
    response = close(relay)
    assert response.status_code == 200, response.text
    events = response.json()['events']
    assert response.json()['status'] in ('completed', 'settled')
    accepted = [e for e in events if e['kind'] == 'proof_human_reviewed']
    assert accepted and accepted[-1]['data']['signoff'] == 'prototype-auto' and accepted[-1]['data']['principal'] == 'relay'
    assert all('signoff' not in e['data'] for e in events if e['kind'] in ('posted', 'taken'))
    assert relay.get('/health').json()['prototype_auto_signoff'] is True


def test_hard_cutoff_and_release_marker_cannot_be_overridden(relay, monkeypatch, tmp_path):
    monkeypatch.setenv('ASE_PROTOTYPE_AUTO_SIGNOFF', 'on')
    assert prototype.auto_signoff_active(datetime(2026, 10, 31, 23, tzinfo=timezone.utc)) is True
    assert prototype.auto_signoff_active(prototype.HARD_CUTOFF) is False
    assert prototype.auto_signoff_active(datetime(2027, 1, 1, tzinfo=timezone.utc)) is False
    (tmp_path / 'RELEASED').write_text('released')
    assert prototype.auto_signoff_active(datetime(2026, 10, 20, tzinfo=timezone.utc)) is False
    assert close(relay).status_code == 403
