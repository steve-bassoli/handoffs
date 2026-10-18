import json
import sqlite3

import pytest

from conftest import post_bounty


@pytest.fixture
def registered(monkeypatch):
    data = {'available': True, 'items': [{'id': 'agent-1', 'name': 'bob', 'level': 1,
        'state': 'active', 'pressure': 1, 'session': 'session-1', 'run': 'PRIVATE PATH',
        'directive': 'PRIVATE PROMPT'}]}
    monkeypatch.setattr('app.main.roster', lambda: data)
    return data


def test_live_dashboard_requires_selected_identity_and_does_not_mutate(client, registered):
    assert client.get('/api/dashboard/live').status_code == 401
    assert client.get('/api/dashboard/live', headers={'X-Demo-User': 'unknown'}).status_code in (401, 403, 404)
    task = post_bounty(client).json()['id']
    with client.app.state.service.db.engine.connect() as connection:
        before = {table: connection.exec_driver_sql('SELECT COUNT(*) FROM ' + table).scalar()
                  for table in ('events', 'gold_entries', 'monthly_allocations', 'operations')}
    response = client.get('/api/dashboard/live', params={'task': task}, headers={'X-Demo-User': 'steve'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    snapshot = response.json()
    assert snapshot['mode']['value'] == 'manual'
    assert snapshot['agents'][0]['name'] == 'bob'
    assert snapshot['agents'][0]['live_confirmed'] is None
    assert snapshot['agents'][0]['interrupted_occupied_lease'] is None
    assert snapshot['context']['selected_task'] == task
    assert snapshot['context']['sessions'] == ['session-1']
    assert snapshot['session']['id'] is None
    assert 'PRIVATE' not in response.text
    with client.app.state.service.db.engine.connect() as connection:
        after = {table: connection.exec_driver_sql('SELECT COUNT(*) FROM ' + table).scalar() for table in before}
    assert after == before


def test_selected_registered_tree_is_allowlisted_and_confined(client, registered):
    root = client.app.state.dashboard_sessions
    directory = root / 'session-1'
    directory.mkdir(parents=True)
    (directory / 'plan.json').write_text(json.dumps({'tree': {'bob': {'level': 1, 'parent': None,
        'role': 'PRIVATE PROMPT', 'shelf': 'PRIVATE PATH'}}}), encoding='utf-8')
    (directory / 'board.jsonl').write_text('{"event":"pressure_stop","at_utc":"2026-10-17T20:00:00Z","directive":"PRIVATE"}\n', encoding='utf-8')
    (directory / 'summary.json').write_text('{"requests":3,"unknown_usage":false,"final_synthesis":"PRIVATE"}', encoding='utf-8')
    headers = {'X-Demo-User': 'steve'}
    result = client.get('/api/dashboard/live', params={'session': 'session-1'}, headers=headers)
    assert result.status_code == 200
    data = result.json()
    assert data['session']['plan'] == {'agents': [{'name': 'bob', 'level': 1, 'parent': None}]}
    assert data['session']['board']['pressure_stop_count'] == 1
    assert data['sources']['board']['event_at'] == '2026-10-17T20:00:00Z'
    assert data['session']['summary']['requests'] == 3
    assert 'PRIVATE' not in result.text
    assert client.get('/api/dashboard/live', params={'session': '../outside'}, headers=headers).status_code == 422
    assert client.get('/api/dashboard/live', params={'session': 'not-registered'}, headers=headers).status_code == 404
    registered['available'] = False
    assert client.get('/api/dashboard/live', params={'session': 'session-1'}, headers=headers).json()['sources']['plan']['status'] == 'unavailable'


def test_dashboard_page_and_main_navigation_are_connected(client):
    assert 'id="dashboard-link" href="/dashboard"' in client.get('/').text
    page = client.get('/dashboard')
    assert page.status_code == 200
    assert page.headers['cache-control'] == 'no-store'
    assert 'dashboard-integration.js' in page.text
    assert 'id="dashboard-user"' in page.text
    assert 'id="dashboard-task"' in page.text
    assert 'id="dashboard-session"' in page.text
    assert 'Back to Tasks' in page.text


def test_ops_flow_use_read_only_sources_and_unknown_usage_blocks_allocation(client, registered):
    ledger = client.app.state.dashboard_ledger
    with sqlite3.connect(ledger) as connection:
        connection.executescript('CREATE TABLE budget(id INTEGER,ceiling INTEGER,baseline INTEGER,provenance TEXT);'
            'CREATE TABLE calls(id TEXT,state TEXT,held INTEGER);')
        connection.execute('INSERT INTO budget VALUES (1,199800,100,?)', ('PRIVATE PROVENANCE',))
        connection.execute('INSERT INTO calls VALUES (?,?,?)', ('call-1', 'unknown', 200))
    original = ledger.read_bytes()
    task = post_bounty(client, gold=10).json()['id']
    result = client.get('/api/dashboard/live', params={'task': task}, headers={'X-Demo-User': 'steve'})
    assert result.status_code == 200
    data = result.json()
    assert data['flow']['tickets'][0]['id'] == task
    assert any(event['kind'] == 'posted' for event in data['flow']['activity'])
    source = data['ops']['sources']['ledger']
    assert source['status'] == 'ok'
    assert source['data']['held_upper_bound_cents'] == 200
    assert source['data']['guarded_headroom_cents'] is None
    assert data['ops']['sources']['wallet']['data']['gold'] == 990
    assert data['ops']['sources']['codex']['status'] == 'unavailable'
    assert data['ops']['sources']['leases']['data']['verified_live_count'] is None
    assert 'PRIVATE' not in result.text
    assert str(ledger) not in result.text
    assert ledger.read_bytes() == original
