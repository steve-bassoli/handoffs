"""Explicit, bounded service adapters for read-only task flow and Ops evidence."""
import json
import hashlib
from pathlib import Path

from app.dashboard_flow import KINDS, build_dashboard_flow
from app.dashboard_ops import normalize_ops
from app.dashboard_ops_source import SourceUnavailable, read_git, read_ledger
from app.storage import all_rows, one


def task_flow(service, task_id, observed):
    with service.db.engine.connect() as connection:
        if task_id:
            root, visited = task_id, set()
            for _ in range(100):
                if root in visited:
                    raise ValueError('cyclic task ancestry')
                visited.add(root)
                parent = one(connection, 'SELECT parent_id FROM tasks WHERE id=?', (root,))
                if not parent or parent['parent_id'] is None:
                    break
                root = parent['parent_id']
            else:
                raise ValueError('task ancestry exceeds bound')
            rows = all_rows(connection, '''WITH RECURSIVE tree(id) AS (
                SELECT ? UNION SELECT b.id FROM tasks b JOIN tree ON b.parent_id=tree.id LIMIT 101)
                SELECT b.id,b.parent_id,b.title,COALESCE((SELECT json_extract(data,'$.complexity') FROM events WHERE task_id=b.id AND json_extract(data,'$.complexity') IN ('HIGH','MEDIUM','LOW') ORDER BY seq DESC LIMIT 1),'HIGH') AS complexity,e.state AS status,
                (SELECT actor FROM events WHERE task_id=b.id AND kind='taken' ORDER BY seq DESC LIMIT 1) AS claimant FROM tasks b
                JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE task_id=b.id)
                WHERE b.id IN (SELECT id FROM tree) ORDER BY b.created_at,b.id''', (root,))
        else:
            rows = all_rows(connection, '''SELECT b.id,b.parent_id,b.title,COALESCE((SELECT json_extract(data,'$.complexity') FROM events WHERE task_id=b.id AND json_extract(data,'$.complexity') IN ('HIGH','MEDIUM','LOW') ORDER BY seq DESC LIMIT 1),'HIGH') AS complexity,e.state AS status,
                (SELECT actor FROM events WHERE task_id=b.id AND kind='taken' ORDER BY seq DESC LIMIT 1) AS claimant FROM tasks b
                JOIN events e ON e.seq=(SELECT MAX(seq) FROM events WHERE task_id=b.id)
                ORDER BY b.created_at DESC,b.id LIMIT 101''')
        details = {}
        kinds = sorted(KINDS)
        placeholders = ','.join('?' for _ in kinds)
        for row in rows[:100]:
            events = all_rows(connection, f'''SELECT kind,data,created_at FROM events
                WHERE task_id=? AND kind IN ({placeholders}) ORDER BY seq DESC LIMIT 50''', (row['id'], *kinds))
            clean = []
            for event in reversed(events):
                data = json.loads(event['data'])
                assignment = data.get('assigned_agent') if isinstance(data, dict) else None
                clean.append({'kind': event['kind'], 'created_at': event['created_at'],
                    'data': {'assigned_agent': assignment[:200]} if isinstance(assignment, str) else {}})
            details[row['id']] = {'events': clean}
    result = build_dashboard_flow({'items': rows}, details, current_id=task_id,
                                 observed_at=observed, max_tickets=100 if task_id else 25, max_activity=100)
    by_id = {row['id']: row for row in rows}
    for task in result['tickets']:
        task.update(complexity=by_id[task['id']]['complexity'], claimant=by_id[task['id']]['claimant'])
    return result


def sponsor_adapter(query):
    budget = query('SELECT ceiling,baseline FROM budget WHERE id=1')
    if len(budget) != 1:
        raise SourceUnavailable()
    holds = query('SELECT state,SUM(held) AS held FROM calls GROUP BY state ORDER BY state')
    return {'ceiling_cents': budget[0]['ceiling'], 'baseline_cents': budget[0]['baseline'],
            'provenance': 'Owner-maintained API budget ledger; complete reservation totals grouped by recorded state', 'reservations_complete': True,
            'holds': [{'id': 'state:' + row['state'], 'state': row['state'], 'held_cents': row['held']} for row in holds]}


def ops_snapshot(service, user, snapshot, roster, ledger_path, repo_root):
    observed = snapshot['observed_at']
    sources = {}
    def identity(prefix, path):
        return prefix + ':' + hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:16]

    def source(key, identity, value):
        sources[key] = {**value, 'source_id': identity, 'last_attempt_at': observed,
                        'observed_at': observed if value.get('status') == 'ok' else None}

    source('ledger', identity('sponsor-ledger', ledger_path), read_ledger(ledger_path, sponsor_adapter))
    source('git', identity('commons-git-head', repo_root), read_git(repo_root))
    try:
        with service.db.engine.connect() as connection:
            gold = service.balance(connection, 'wallet:' + user)
        wallet = {'status': 'ok', 'data': {'gold': gold}}
    except Exception:
        wallet = {'status': 'unavailable', 'error_code': 'source_unavailable'}
    source('wallet', identity('participant:' + user, service.db.path), wallet)
    summary = snapshot['session']['summary']
    value = summary.get('upper_bound_cents_for_reported_usage') if summary else None
    usage = {'status': 'ok', 'data': {'reported_upper_cents': value}} if summary else {
        'status': 'unavailable', 'error_code': 'source_unavailable'}
    source('session_usage', identity('session:' + (snapshot['session']['id'] or 'none'), service.db.path.parent), usage)
    source('codex', 'codex-allowance', {'status': 'unavailable', 'error_code': 'adapter_required'})
    leases = {'status': 'ok', 'data': {'records': [{'id': row['id'], 'state': row['state'],
        'evidence': 'Registered state only; liveness unknown'} for row in roster.get('items', [])[:1000]],
        'verified_live_count': None, 'interrupted_occupied_count': None}} if roster.get('available') else {
        'status': 'unavailable', 'error_code': 'source_unavailable'}
    source('leases', identity('registered-agent-leases', ledger_path), leases)
    return normalize_ops({'sources': sources})


def add_panels(service, user, snapshot, roster, ledger_path, repo_root, task_id):
    try:
        snapshot['flow'] = task_flow(service, task_id, snapshot['observed_at'])
    except Exception:
        snapshot['flow'] = build_dashboard_flow({'items': []}, {}, current_id=task_id, observed_at=snapshot['observed_at'])
        snapshot['flow']['issues'].append('source_unavailable')
    snapshot['ops'] = ops_snapshot(service, user, snapshot, roster, ledger_path, repo_root)
    return snapshot
