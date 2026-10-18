"""Automation modes: tree shape and models per level, humans-only writes in manual mode."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.astra_tree import Tree
from app.automation_mode import AUTOMATION_HEADER, MODES, apply_agent_names, current, set_mode
from app.main import create_app
from conftest import post_task
from test_agent_conduit import candidate, stream_result, usage
from test_astra_tree import thirteen


def shelf(tmp_path):
    path = tmp_path / 'source.txt'
    path.write_text('source', encoding='utf-8')
    return {'source': str(path)}


def recorder(seen, done=True):
    def respond(request):
        payload = json.loads(request.content)
        content = json.loads(payload['input'][0]['content'])
        seen.append((content['your_name'], payload['model'], payload['reasoning']['effort'], payload.get('max_output_tokens')))
        reply = {'summary': 'ok', 'done': done, 'directives': {}}
        return stream_result(candidate(json.dumps(reply)), usage())
    return httpx.MockTransport(respond)


def test_missing_or_invalid_setting_means_manual_and_set_keeps_history(tmp_path):
    path = tmp_path / 'automation-mode.json'
    assert current(path)['mode'] == 'manual' and current(path)['automated_writes'] is False
    path.write_text('{"mode": "turbo"}', encoding='utf-8')
    assert current(path)['mode'] == 'manual'
    with pytest.raises(ValueError):
        set_mode('max', 'steve', '', path)
    set_mode('max', 'steve', 'campaign', path)
    record = set_mode('manual', 'steve', 'humans only', path)
    assert record['mode'] == 'manual' and [h['mode'] for h in record['history']] == ['max', 'manual']


def test_max_mode_runs_astra_root_and_sol_below(tmp_path):
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    summary = Tree(thirteen(tmp_path), session, 30, transport=recorder(seen, done=True), mode='max').run()
    models = {name: (model, effort, ceiling) for name, model, effort, ceiling in seen}
    assert models['coordinator'] == ('gpt-6-astra', 'max', None)
    assert models['catalog'] == models['catalog1'] == ('gpt-6.1-sol', 'low', 12000)
    assert summary['mode'] == 'max' and summary['models'] == {'HIGH': 'gpt-6-astra', 'MEDIUM': 'gpt-6.1-sol', 'LOW': 'gpt-6.1-sol'}


def test_light_and_heavy_modes_are_four_agents_and_reject_more(tmp_path):
    source = shelf(tmp_path)
    plan = {'goal': 'g', 'authority': 'a', 'coordinator': {'shelf': source},
            'children': [{'name': f'w{n}', 'role': 'low', 'shelf': source, 'max_requests': 1} for n in range(3)]}
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    Tree(plan, session, 30, transport=recorder(seen), mode='light').run()
    assert {(name, model) for name, model, _, _ in seen} == {
        ('coordinator', 'gpt-6.1-sol'), ('w0', 'gpt-5.6-terra'), ('w1', 'gpt-5.6-terra'), ('w2', 'gpt-5.6-terra')}
    with pytest.raises(ValueError):
        Tree(thirteen(tmp_path), tmp_path, 30, mode='light')


def test_manual_mode_is_one_sol_agent_that_answers_once(tmp_path):
    plan = {'goal': 'g', 'authority': 'a', 'coordinator': {'shelf': shelf(tmp_path)}}
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    summary = Tree(plan, session, 30, transport=recorder(seen, done=False), mode='manual').run()
    assert seen == [('coordinator', 'gpt-6.1-sol', 'low', 12000)] and summary['requests'] == 1
    with pytest.raises(ValueError):
        Tree({**plan, 'children': [{'name': 'w', 'role': 'x', 'shelf': shelf(tmp_path)}]}, tmp_path, 30, mode='manual')
    assert MODES['manual']['agents'] == 1 and MODES['light']['agents'] == 4 and MODES['max']['agents'] == 13


def test_manual_mode_refuses_automated_writes_but_not_humans(tmp_path, monkeypatch):
    mode_file = tmp_path / 'automation-mode.json'
    monkeypatch.setenv('HANDOFFS_AUTOMATION_MODE', str(mode_file))
    with TestClient(create_app(tmp_path / 'test.sqlite')) as client:
        assert client.get('/api/v1/automation-mode', headers={'X-Demo-User': 'steve'}).json()['mode'] == 'manual'
        assert post_task(client).status_code == 200, 'Humans still create tickets in manual mode'
        automated = client.post('/api/v1/tasks', json={'title': 't', 'goal': 'g', 'criteria': ['c'], 'gold': 5},
                                headers={'X-Demo-User': 'steve', 'Idempotency-Key': 'auto-1', AUTOMATION_HEADER: 'astra'})
        assert automated.status_code == 403 and 'Manual mode' in automated.json()['detail']
        set_mode('light', 'steve', 'test', mode_file)
        allowed = client.post('/api/v1/tasks', json={'title': 't', 'goal': 'g', 'criteria': ['c'], 'gold': 5},
                              headers={'X-Demo-User': 'steve', 'Idempotency-Key': 'auto-2', AUTOMATION_HEADER: 'astra'})
        assert allowed.status_code == 403
        assert 'Automation scope' in allowed.json()['detail']


def test_manual_mode_accepts_attributed_user_direction_without_enabling_autonomy(client):
    headers = {'X-Demo-User': 'steve', 'Idempotency-Key': 'directed',
               AUTOMATION_HEADER: 'codex', 'X-Action-Intent': 'user-directed'}
    payload = {'title': 'Requested task', 'goal': 'Finish', 'criteria': ['Works'], 'gold': 5}
    response = client.post('/api/v1/tasks', json=payload, headers=headers)
    assert response.status_code == 200
    event = response.json()['events'][-1]
    assert event['actor'] == 'steve'
    assert event['data']['via'] == 'codex'
    assert event['data']['action_intent'] == 'user-directed'
    assert client.get('/api/v1/automation-mode').json()['mode'] == 'manual'
    for intent in ('autonomous', None):
        changed = {**headers, 'Idempotency-Key': 'blocked-' + str(intent)}
        if intent is None:
            changed.pop('X-Action-Intent')
        else:
            changed['X-Action-Intent'] = intent
        assert client.post('/api/v1/tasks', json=payload, headers=changed).status_code == 403
    invalid = {**headers, 'X-Action-Intent': 'guess', 'Idempotency-Key': 'invalid'}
    assert client.post('/api/v1/tasks', json=payload, headers=invalid).status_code == 422
    task_id = response.json()['id']
    # User direction does not grant another participant's permissions.
    wrong = {**headers, 'X-Demo-User': 'will', 'Idempotency-Key': 'wrong-user'}
    assert client.post(f'/api/v1/tasks/{task_id}/cancel', json={}, headers=wrong).status_code == 403


def test_relay_user_direction_is_recorded_in_task_history(client):
    headers = {'X-Demo-User': 'steve', 'Idempotency-Key': 'relay-directed',
               AUTOMATION_HEADER: 'relay', 'X-Action-Intent': 'user-directed'}
    response = client.post('/api/v1/tasks', json={
        'title': 'Relay request', 'goal': 'Finish', 'criteria': ['Works'], 'gold': 5,
    }, headers=headers)
    assert response.status_code == 200
    history = client.get('/api/v1/tasks/' + response.json()['id']).json()['events']
    event = history[-1]
    assert event['actor'] == 'steve'
    assert event['data']['via'] == 'relay'
    assert event['data']['action_intent'] == 'user-directed'


@pytest.mark.parametrize('mode', ['light', 'heavy', 'max'])
@pytest.mark.parametrize('attribution', ['implicit', 'explicit', 'intent-only'])
def test_autonomous_writes_are_ticket_scoped(tmp_path, monkeypatch, mode, attribution):
    mode_file = tmp_path / 'automation-mode.json'
    monkeypatch.setenv('HANDOFFS_AUTOMATION_MODE', str(mode_file))
    set_mode(mode, 'steve', 'scope regression', mode_file)
    with TestClient(create_app(tmp_path / 'scope.sqlite')) as client:
        first = post_task(client).json()['id']
        second_response = client.post('/api/v1/tasks', json={
            'title': 'Other task', 'goal': 'Finish', 'criteria': ['Works'], 'gold': 5,
        }, headers={'X-Demo-User': 'steve', 'Idempotency-Key': 'second-task'})
        assert second_response.status_code == 200
        second = second_response.json()['id']
        headers = {'X-Demo-User': 'steve', 'Idempotency-Key': 'scoped-write'}
        if attribution != 'intent-only':
            headers[AUTOMATION_HEADER] = 'astra'
        if attribution != 'implicit':
            headers['X-Action-Intent'] = 'autonomous'
        path = f'/api/v1/tasks/{first}/cancel'
        for scope in (None, '', second, first + '-suffix', first + '/cancel', '..'):
            changed = dict(headers)
            if scope is not None:
                changed['X-Automation-Scope'] = scope
            response = client.post(path, json={}, headers=changed)
            assert response.status_code == 403
            assert 'Automation scope' in response.json()['detail']
        scoped = {**headers, 'X-Automation-Scope': first}
        for forbidden in ('/api/v1/tasks', '/api/v1/tasks/',
                          f'/api/v1/tasks/{second}/cancel',
                          f'/api/v1/bounties/{first}/cancel', '/api/v1/gremlins/mimic'):
            response = client.post(forbidden, json={}, headers=scoped)
            assert response.status_code == 403
            assert 'Automation scope' in response.json()['detail']
        assert client.post(path, json={}, headers=scoped).status_code == 200
        directed = {**scoped, 'X-Action-Intent': 'user-directed',
                    'Idempotency-Key': 'directed-other-task'}
        assert client.post(f'/api/v1/tasks/{second}/cancel', json={}, headers=directed).status_code == 200


def test_bob_naming_for_light_and_heavy_trees(tmp_path):
    heavy = apply_agent_names(thirteen(tmp_path))
    assert heavy['root_name'] == 'bob'
    assert [lead['name'] for lead in heavy['children']] == ['bob-2', 'bob-3', 'bob-4']
    assert [[w['name'] for w in lead['children']] for lead in heavy['children']] == [
        ['bob-5', 'bob-6', 'bob-7'], ['bob-8', 'bob-9', 'bob-10'], ['bob-11', 'bob-12', 'bob-13']]
    source = shelf(tmp_path)
    light = apply_agent_names({'goal': 'g', 'authority': 'a', 'coordinator': {'shelf': source},
                               'children': [{'name': f'w{n}', 'role': 'low', 'shelf': source, 'max_requests': 1} for n in range(3)]})
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    summary = Tree(light, session, 30, transport=recorder(seen), mode='light').run()
    assert {name for name, *_ in seen} == {'bob', 'bob-2', 'bob-3', 'bob-4'}
    assert dict((name, model) for name, model, _, _ in seen)['bob'] == 'gpt-6.1-sol'
    assert summary['turns'][0]['agent'] == 'bob'
    heavy_seen = []
    heavy_session = tmp_path / 'heavy'
    heavy_session.mkdir()
    Tree(heavy, heavy_session, 30, transport=recorder(heavy_seen, done=True), mode='max').run()
    assert {name for name, *_ in heavy_seen} == {'bob'} | {f'bob-{n}' for n in range(2, 14)}


def test_heavy_mode_is_astra_over_three_sol(tmp_path):
    source = shelf(tmp_path)
    plan = {'goal': 'g', 'authority': 'a', 'coordinator': {'shelf': source},
            'children': [{'name': f'w{n}', 'role': 'low', 'shelf': source, 'max_requests': 1} for n in range(3)]}
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    Tree(plan, session, 30, transport=recorder(seen), mode='heavy').run()
    assert {(name, model) for name, model, _, _ in seen} == {
        ('coordinator', 'gpt-6-astra'), ('w0', 'gpt-6.1-sol'), ('w1', 'gpt-6.1-sol'), ('w2', 'gpt-6.1-sol')}
    with pytest.raises(ValueError):
        Tree(thirteen(tmp_path), tmp_path, 30, mode='heavy')
