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
                    'started': 'start', 'ended': 'end', 'resting': None,
                    'name': None, 'session': None, 'task': None, 'directive': None, 'task_id': None}
    assert 'private' not in response.text and 'pid' not in response.text
    assert path.read_bytes() == before
    assert client.get('/api/v1/agents', headers={'X-Demo-User': 'unknown'}).status_code == 401


@pytest.mark.parametrize('report', ['{"pressure_level": 3}', '{"energy": "low"}', 'not JSON'])
def test_retired_pressure_and_energy_reports_are_ignored(tmp_path, report):
    # Tasks 9e5678ac and bb4bcf2c: the only self-report left is a tree turn's rest flag.
    path, run = registry(tmp_path, 'active')
    (run / 'candidate.json').write_text(report, encoding='utf-8')
    item = roster(path)['items'][0]
    assert item['resting'] is None and 'pressure' not in item and item['state'] == 'active'


def test_missing_registry_is_not_created_and_empty_is_distinct(tmp_path):
    path = tmp_path / 'absent.sqlite'
    assert roster(path) == {'available': False, 'items': []}
    assert not path.exists()
    with sqlite3.connect(path) as db:
        assert roster(path) == {'available': False, 'items': []}
        db.execute(SCHEMA)
    assert roster(path) == {'available': True, 'items': []}


def test_tree_agent_shows_task_directive_rest_and_campaign_task(tmp_path):
    path = tmp_path / 'budget.sqlite'
    root = tmp_path / 'astra-tree'
    session = root / '20261017T090000Z-it2'
    for name in ('frontend', 'fe_study'):
        (session / name).mkdir(parents=True)
    (session / 'plan.json').write_text(json.dumps({'tree': {
        'frontend': {'role': 'MEDIUM: forms', 'parent': 'coordinator', 'level': 2},
        'fe_study': {'role': 'LOW crawler: study screens', 'parent': 'frontend', 'level': 3}}}), encoding='utf-8')
    (session / 'frontend' / 'round-01.json').write_text(json.dumps({'directives': {'fe_study': 'Crawl frmStudy first'}}), encoding='utf-8')
    (session / 'fe_study' / 'round-01.json').write_text(json.dumps({'summary': 'tired', 'rest': True}), encoding='utf-8')
    (root / 'campaign-task.json').write_text(json.dumps({'id': 'task-1', 'sessions_since': '20261017T082340Z'}), encoding='utf-8')
    with sqlite3.connect(path) as db:
        db.execute(SCHEMA)
        db.execute('INSERT INTO astra_agents VALUES (?,?,?,?,?,?,?,?,?,?)',
                   ('a3', 'frontend-id', 'tree', 3, 'worker', 1, str(session / 'fe_study'), 'start', None, 'active'))
    item = roster(path)['items'][0]
    assert (item['name'], item['session'], item['resting']) == ('fe_study', '20261017T090000Z-it2', True)
    assert item['task'] == 'LOW crawler: study screens' and item['directive'] == 'Crawl frmStudy first'
    assert item['task_id'] == 'task-1'
    (root / 'campaign-task.json').write_text(json.dumps({'id': 'task-1', 'sessions_since': '20261018'}), encoding='utf-8')
    assert roster(path)['items'][0]['task_id'] is None
