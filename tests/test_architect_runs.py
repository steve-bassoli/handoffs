"""Bob and Sue tab (task a6eb660f): read-only architect-run metadata found through the lease ledger."""
import json
import re
import sqlite3
from pathlib import Path

from app.architect_runs import architect_runs

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'
SCHEMA = """CREATE TABLE astra_agents (id TEXT PRIMARY KEY, parent_id TEXT, tree_id TEXT NOT NULL, level INTEGER NOT NULL,
    role TEXT NOT NULL, pid INTEGER NOT NULL, run TEXT NOT NULL, started TEXT NOT NULL, ended TEXT, state TEXT NOT NULL)"""


def _session(base, name, root, summary, ticket='2bfa6685-9271-4127-a62b-67addcdcbec7'):
    session = base / name
    (session / root).mkdir(parents=True)
    plan = {'root_name': root, 'ticket': ticket, 'minutes': 60, 'goal': 'SECRET GOAL TEXT', 'culture': 'SECRET CULTURE',
            'tree': {root: {'level': 1, 'role': 'Coordinates.'}, 'bob-3': {'level': 3, 'role': 'Worker.'}}}
    (session / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    if summary is not None:
        (session / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
    return session / root


def _ledger(path, rows):
    db = sqlite3.connect(path)
    db.execute(SCHEMA)
    for i, (run, state, started) in enumerate(rows):
        db.execute('INSERT INTO astra_agents VALUES (?,?,?,?,?,?,?,?,?,?)', (f'a{i}', None, f'a{i}', 1, 'coordinator', 1, str(run), started, None, state))
    db.commit(); db.close()


def test_runs_are_grouped_by_architect_with_metadata_only(tmp_path):
    summary = {'turns': [{'round': 1}, {'round': 2}], 'architect_stamp': {'approved': True, 'round': 2, 'notes': 'SECRET NOTES'},
               'stopped_agents': ['bob-3'], 'elapsed_minutes': 3.1, 'upper_bound_cents_for_reported_usage': 98, 'unknown_usage': 0,
               'cards': {'bob-3': {'specialty': 'x', 'personality': 'SECRET PERSONALITY'}}, 'final_synthesis': 'SECRET SYNTHESIS'}
    bob = _session(tmp_path, '20261019T043737Z-bob-bb3', 'bob-the-architect', summary)
    sue = _session(tmp_path, '20261019T051000Z-bob-sue', 'sue-the-architect', None)
    old = _session(tmp_path, '20261017T120000Z-bob-01-calm', 'bob', {'unknown_usage': 2})
    _ledger(tmp_path / 'ledger.sqlite', [(bob, 'released', '2026-10-19T04:37'), (sue, 'active', '2026-10-19T05:10'), (old, 'failed', '2026-10-17T12:00')])
    data = architect_runs(tmp_path / 'ledger.sqlite')
    assert data['available'] and [g['name'] for g in data['architects']] == ['sue-the-architect', 'bob-the-architect']
    run = data['architects'][1]['runs'][0]
    assert run['ticket'] == '2bfa6685-9271-4127-a62b-67addcdcbec7' and run['rounds'] == 2 and run['rest_stops'] == 1
    assert run['stamp'] == {'approved': True, 'round': 2} and run['upper_bound_cents'] == 98 and run['cost_bound_complete'] is True
    assert run['team'] == [{'name': 'bob-the-architect', 'level': 'HIGH', 'card': False}, {'name': 'bob-3', 'level': 'LOW', 'card': True}]
    live = data['architects'][0]['runs'][0]
    assert live['lease'] == 'active lease' and live['finished'] is False and live['rounds'] is None
    # Runs from before the architects fold into one group; unknown usage means the bound is incomplete.
    assert [r['architect'] for r in data['earlier']] == ['bob'] and data['earlier'][0]['cost_bound_complete'] is False
    assert data['earlier'][0]['lease'] == 'failed: needs explicit recovery'
    # Metadata only: no goals, culture, notes, personalities, syntheses or paths leave the server.
    text = json.dumps(data)
    assert 'SECRET' not in text and str(tmp_path) not in text


def test_unavailable_ledger_says_so(tmp_path):
    assert architect_runs(tmp_path / 'missing' / 'ledger.sqlite') == {'available': False, 'architects': []}


def test_bob_and_sue_tab_is_second_and_read_only():
    for page in ('index.html', 'dashboard.html'):
        nav = re.search(r'<nav aria-label="Workspace"[^>]*>(.*?)</nav>', (STATIC / page).read_text(encoding='utf-8'), re.S).group(1)
        assert re.findall(r'data-view="(\w+)"', nav)[:3] == ['signoffs', 'bobsue', 'gallery'], page
        assert 'Bob and Sue</button>' in nav, page
    section = re.search(r'<section id="bobsue" hidden>(.*?)</section>', (STATIC / 'index.html').read_text(encoding='utf-8'), re.S).group(1)
    assert re.findall(r'<button[^>]*>([^<]*)</button>', section) == ['Refresh']  # no launch, stop, approve or spend controls
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    assert "await api('/architect-runs')" in script and "'signoffs', 'bobsue', 'gallery']" in script
