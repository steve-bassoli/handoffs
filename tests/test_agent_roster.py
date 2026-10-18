import json
import sqlite3

import pytest

from app.agent_roster import roster
from app.astra_agents import SCHEMA


def registry(tmp_path, state='released'):
    path = tmp_path / 'budget.sqlite'
    run = tmp_path / 'private-run'
    run.mkdir()
    with sqlite3.connect(path) as db:
        db.execute(SCHEMA)
        db.execute('INSERT INTO astra_agents VALUES (?,?,?,?,?,?,?,?,?,?)',
                   ('agent-one', None, 'tree', 1, 'worker', 999, str(run), 'start', 'end', state))
    return path, run


def test_registry_read_is_private_read_only_and_does_not_mint_stats(tmp_path, monkeypatch, client):
    path, run = registry(tmp_path)
    (run / 'answer.json').write_text(json.dumps({'state': 'completed', 'text': json.dumps({
        'pressure_level': 1, 'secret': 'private source'})}), encoding='utf-8')
    before = path.read_bytes()
    monkeypatch.setenv('HANDOFFS_API_BUDGET_DB', str(path))
    response = client.get('/api/v1/agents')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    item = response.json()['items'][0]
    assert item == {'id': 'agent-one', 'role': 'worker', 'level': 1, 'state': 'released',
                    'started': 'start', 'ended': 'end', 'pressure': 1,
                    'credits': None, 'admiration': None, 'growth': None,
                    'name': None, 'session': None, 'task': None, 'directive': None, 'task_id': None}
    assert 'private' not in response.text and 'pid' not in response.text
    assert path.read_bytes() == before
    assert client.get('/api/v1/agents', headers={'X-Demo-User': 'unknown'}).status_code == 401


@pytest.mark.parametrize('value', [None, True, '2', 0, 4, 2.0])
def test_invalid_or_missing_reports_are_unknown_not_requested_pressure(tmp_path, value):
    path, run = registry(tmp_path, 'active')
    (run / 'prompt.json').write_text('{"pressure_level": 2}', encoding='utf-8')
    (run / 'answer.json').write_text(json.dumps({'state': 'completed', 'text': json.dumps({'pressure_level': value})}), encoding='utf-8')
    assert roster(path)['items'][0]['pressure'] is None
    assert roster(path)['items'][0]['state'] == 'active'


def test_candidate_report_and_malformed_answer(tmp_path):
    path, run = registry(tmp_path, 'failed')
    (run / 'answer.json').write_text('not JSON', encoding='utf-8')
    (run / 'candidate.json').write_text('{"pressure_level": 3}', encoding='utf-8')
    assert roster(path)['items'][0]['pressure'] == 3


def test_missing_registry_is_not_created_and_empty_is_distinct(tmp_path):
    path = tmp_path / 'absent.sqlite'
    assert roster(path) == {'available': False, 'items': []}
    assert not path.exists()
    with sqlite3.connect(path) as db:
        assert roster(path) == {'available': False, 'items': []}
        db.execute(SCHEMA)
    assert roster(path) == {'available': True, 'items': []}


def test_tree_agent_shows_task_directive_pressure_and_campaign_task(tmp_path):
    path = tmp_path / 'budget.sqlite'
    root = tmp_path / 'astra-tree'
    session = root / '20261017T090000Z-it2'
    for name in ('frontend', 'fe_study'):
        (session / name).mkdir(parents=True)
    (session / 'plan.json').write_text(json.dumps({'tree': {
        'frontend': {'role': 'MEDIUM: forms', 'parent': 'coordinator', 'level': 2},
        'fe_study': {'role': 'LOW crawler: study screens', 'parent': 'frontend', 'level': 3}}}), encoding='utf-8')
    (session / 'frontend' / 'round-01.json').write_text(json.dumps({'directives': {'fe_study': 'Crawl frmStudy first'}}), encoding='utf-8')
    (session / 'fe_study' / 'round-01.json').write_text(json.dumps({'pressure': 2}), encoding='utf-8')
    (root / 'campaign-task.json').write_text(json.dumps({'id': 'task-1', 'sessions_since': '20261017T082340Z'}), encoding='utf-8')
    with sqlite3.connect(path) as db:
        db.execute(SCHEMA)
        db.execute('INSERT INTO astra_agents VALUES (?,?,?,?,?,?,?,?,?,?)',
                   ('a3', 'frontend-id', 'tree', 3, 'worker', 1, str(session / 'fe_study'), 'start', None, 'active'))
    item = roster(path)['items'][0]
    assert (item['name'], item['session'], item['pressure']) == ('fe_study', '20261017T090000Z-it2', 2)
    assert item['task'] == 'LOW crawler: study screens' and item['directive'] == 'Crawl frmStudy first'
    assert item['task_id'] == 'task-1'
    (root / 'campaign-task.json').write_text(json.dumps({'id': 'task-1', 'sessions_since': '20261018'}), encoding='utf-8')
    assert roster(path)['items'][0]['task_id'] is None
