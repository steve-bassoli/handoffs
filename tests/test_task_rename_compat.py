"""Explicit compatibility literals and historical-schema fixtures are intentional."""
import asyncio
from pathlib import Path
import shutil
import subprocess

from alembic import command
from alembic.config import Config
from fastapi.routing import APIRoute
import pytest

from app.storage import Database

ROOT = Path(__file__).resolve().parents[1]
OLD_TO_NEW = {
    'bounty_paid': 'task_paid', 'bounty_funded': 'task_funded',
    'bounty_refunded': 'task_refunded', 'bounty_edited': 'task_edited',
    'opportunity_updated': 'task_updated',
}


def migrate(db, revision, downgrade=False):
    cfg = Config()
    cfg.set_main_option('script_location', str(ROOT / 'migrations'))
    with db.engine.begin() as c:
        cfg.attributes['connection'] = c
        (command.downgrade if downgrade else command.upgrade)(cfg, revision)


def snapshot(c):
    tables = [r[0] for r in c.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT IN ('alembic_version','_task_rename_003') ORDER BY name")]
    return {table: sorted([dict(row) for row in c.exec_driver_sql('SELECT * FROM "' + table + '"').mappings()], key=repr) for table in tables}


def expected_after(before):
    result = {}
    for table, rows in before.items():
        changed = []
        for source in rows:
            row = {('task_id' if key == 'bounty_id' else key): value for key, value in source.items()}
            if table in ('events', 'gold_transactions'):
                row['kind'] = OLD_TO_NEW.get(row['kind'], row['kind'])
            if table == 'accounts' and row['id'] == 'legacy:bounty':
                row['id'] = 'legacy:task'
            if table == 'gold_entries' and row['account_id'] == 'legacy:bounty':
                row['account_id'] = 'legacy:task'
            changed.append(row)
        result['tasks' if table == 'bounties' else table] = sorted(changed, key=repr)
    return result


def balances(c):
    return dict(c.exec_driver_sql('SELECT account_id,SUM(amount) FROM gold_entries GROUP BY account_id').all())


def test_002_upgrade_preserves_all_rows_balances_constraints_and_downgrade(tmp_path):
    db = Database(tmp_path / 'migration.sqlite')
    try:
        migrate(db, '002')
        with db.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO users VALUES ('steve','Steve','Steve')")
            for identity, parent in [('root', None), ('child', 'root')]:
                c.exec_driver_sql("INSERT INTO bounties(id,title,goal,criteria,repository,context_links,creator,gold,created_at,parent_id) VALUES (?,?,?,'[]','','[]','steve',100,'t',?)", (identity, identity, 'Keep evidence unchanged: bounty opportunity', parent))
            c.exec_driver_sql("INSERT INTO accounts VALUES ('issuance',NULL,'issuance'),('wallet:steve','steve','wallet'),('escrow:root','steve','escrow'),('legacy:bounty','steve','escrow')")
            for index, kind in enumerate(OLD_TO_NEW):
                c.exec_driver_sql("INSERT INTO events(bounty_id,kind,actor,state,data,created_at) VALUES ('root',?,'steve','open',?,'t')", (kind, '{"evidence":"bounty opportunity", "bounty_id":"opaque historical evidence"}'))
                c.exec_driver_sql("INSERT INTO gold_transactions VALUES (?,?,'root','t')", ('tx' + str(index), kind))
                c.exec_driver_sql("INSERT INTO gold_entries(transaction_id,account_id,amount) VALUES (?,'wallet:steve',-10),(?,'escrow:root',10)", ('tx' + str(index), 'tx' + str(index)))
            c.exec_driver_sql("INSERT INTO gold_entries(transaction_id,account_id,amount) VALUES ('tx0','issuance',-3),('tx0','legacy:bounty',3)")
            c.exec_driver_sql("INSERT INTO deliveries VALUES ('d','root','steve','https://example.invalid/pr','Unchanged bounty evidence',1,'t')")
            c.exec_driver_sql("INSERT INTO ai_runs VALUES ('run','root','steve','done','{}','t','t')")
            c.exec_driver_sql("INSERT INTO monthly_allocations VALUES ('steve','2026-01',1000)")
            c.exec_driver_sql("INSERT INTO operations VALUES ('steve','receipt','unchanged-fingerprint','{\"bounty_id\":\"root\"}')")
            c.exec_driver_sql("INSERT INTO import_records VALUES ('fixture','doc','hash','{\"text\":\"opportunity\"}')")
            c.exec_driver_sql('CREATE INDEX ix_events_bounty_id ON events(bounty_id)')
            before = snapshot(c)
            money = balances(c)
        migrate(db, '003')
        with db.engine.connect() as c:
            assert snapshot(c) == expected_after(before)
            assert balances(c) == {('legacy:task' if key == 'legacy:bounty' else key): value for key, value in money.items()}
            assert not c.exec_driver_sql('PRAGMA foreign_key_check').all()
            assert c.exec_driver_sql("SELECT parent_id FROM tasks WHERE id='child'").scalar() == 'root'
            assert c.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND name='ix_events_task_id'").scalar()
            for table in ('events', 'deliveries', 'gold_transactions', 'ai_runs'):
                foreign_keys = c.exec_driver_sql('PRAGMA foreign_key_list(' + table + ')').mappings().all()
                assert any(row['from'] == 'task_id' and row['table'] == 'tasks' for row in foreign_keys)
            assert any(row['from'] == 'parent_id' and row['table'] == 'tasks' for row in c.exec_driver_sql('PRAGMA foreign_key_list(tasks)').mappings())
        # A new insert exercises the retained AUTOINCREMENT state and FKs.
        with db.engine.begin() as c:
            maximum = c.exec_driver_sql('SELECT MAX(seq) FROM events').scalar()
            c.exec_driver_sql("INSERT INTO events(task_id,kind,actor,state,data,created_at) VALUES ('child','posted','steve','open','{}','t')")
            assert c.exec_driver_sql('SELECT MAX(seq) FROM events').scalar() > maximum
            c.exec_driver_sql('DELETE FROM events WHERE seq>?', (maximum,))
        migrate(db, '002', downgrade=True)
        with db.engine.connect() as c:
            assert snapshot(c) == before
            assert balances(c) == money
            assert not c.exec_driver_sql('PRAGMA foreign_key_check').all()
            assert c.exec_driver_sql("SELECT name FROM sqlite_master WHERE name='ix_events_bounty_id'").scalar()
    finally:
        db.engine.dispose()


def test_legacy_routes_are_hidden_and_share_endpoints(client):
    routes = [route for route in client.app.routes if isinstance(route, APIRoute)]
    canonical = [route for route in routes if route.path == '/api/v1/tasks' or route.path.startswith('/api/v1/tasks/')]
    assert canonical
    for route in canonical:
        old = '/api/v1/bounties' + route.path[len('/api/v1/tasks'):]
        matches = [candidate for candidate in routes if candidate.path == old and candidate.methods == route.methods]
        assert len(matches) == 1
        assert matches[0].endpoint is route.endpoint
        assert matches[0].include_in_schema is False
        assert matches[0].deprecated is True
    paths = client.get('/openapi.json').json()['paths']
    assert not any(path.startswith('/api/v1/bounties') for path in paths)
    payload = {'title': 'Compatibility', 'goal': 'Keep old links working', 'criteria': ['Same record'], 'gold': 10, 'complexity': 'LOW'}
    headers = {'X-Demo-User': 'steve', 'Idempotency-Key': 'compat-post'}
    response = client.post('/api/v1/bounties', json=payload, headers=headers)
    assert response.status_code == 200, response.text
    identity = response.json()['id']
    assert client.post('/api/v1/tasks', json=payload, headers=headers).json()['id'] == identity
    assert client.get('/api/v1/bounties/' + identity).json()['id'] == identity
    assert client.get('/api/v1/tasks/' + identity).json()['id'] == identity
    assert client.get('/api/v1/bounties?view=all').json()['items'] == client.get('/api/v1/tasks?view=all').json()['items']
    taken = client.post('/api/v1/bounties/' + identity + '/take', json={}, headers={'X-Demo-User': 'nate', 'Idempotency-Key': 'compat-take'})
    assert taken.status_code == 200, taken.text
    assert client.get('/api/v1/tasks/' + identity).json()['claimant'] == 'nate'


def test_old_mcp_tools_are_listed_and_keep_legacy_argument_schemas(monkeypatch):
    from app import mcp_server as module
    aliases = {'post_bounty': 'post_task', 'take_bounty': 'take_task', 'get_bounty': 'get_task', 'list_bounties': 'list_tasks', 'edit_bounty': 'edit_task', 'get_bounty_context': 'get_task_context'}
    tools = {tool.name: tool for tool in asyncio.run(module.server.list_tools())}
    for old, new in aliases.items():
        assert old in tools and new in tools
        assert tools[old].annotations == tools[new].annotations
        assert 'Deprecated' in tools[old].description
        properties = tools[old].inputSchema.get('properties', {})
        if old in ('take_bounty', 'get_bounty', 'edit_bounty', 'get_bounty_context'):
            assert 'bounty_id' in properties
            assert 'task_id' not in properties
        calls = []
        def target(*args, **kwargs):
            calls.append((args, kwargs))
            return {'ok': True}
        monkeypatch.setattr(module, new, target)
        assert getattr(module, old)(_compat_probe=True) == {'ok': True}
        assert calls == [((), {'_compat_probe': True})]


def test_legacy_hashes_resolve_to_canonical_routes():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for sliced startup JavaScript test')
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const start = source.indexOf('async function show(id) {');
const end = source.indexOf("  for (const section of ['board'");
assert.ok(start >= 0 && end > start, 'Review slice after frontend refactoring');
const show = source.slice(start, end) + '}';
const startupAt = source.lastIndexOf('run(async () => {');
assert.ok(startupAt >= 0);
const startup = source.slice(startupAt);
(async () => {
  for (const [hash, id] of [
    ['#task=current', 'current'],
    ['#task=current&opp=previous&bounty=old', 'current'],
    ['#opp=offer', 'offer'], ['#bounty=offer', 'offer'],
    ['#opp=new&bounty=old', 'new'],
    ['#opp=offer%2Fwith%20space', 'offer/with space'], ['', null],
  ]) {
    const requests = [];
    const context = {
      URLSearchParams, encodeURIComponent, user: 'nate', aiPoll: null, proofPoll: null,
      clearTimeout() {}, location: {hash},
      history: {replaceState(_s, _t, url) { context.location.hash = url; }},
      api: async path => { requests.push(path); return path === '/users' ? [{id:'nate',name:'Nate'}] : {}; },
      navigate: async () => { context.location.hash = ''; },
      $: () => ({append() {}}), element: () => ({cloneNode: () => ({})}),
      document: {querySelector: () => ({append() {}})},
      run: operation => { context.finished = operation(); },
    };
    vm.runInNewContext(show + '\n' + startup, context);
    await context.finished;
    assert.deepEqual(requests, id ? ['/users', '/tasks/' + encodeURIComponent(id)] : ['/users']);
    assert.equal(context.location.hash, id ? '#task=' + encodeURIComponent(id) : '');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run([node, '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
