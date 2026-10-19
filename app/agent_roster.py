"""Read-only projection of registered Astra runs, not a process monitor or wallet."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from app.api_budget import budget_path

LEVELS = {1: 'HIGH', 2: 'MEDIUM', 3: 'LOW'}


def _json(path, limit=262144):
    try:
        with Path(path).open('rb') as source:
            raw = source.read(limit + 1)
        return None if len(raw) > limit else json.loads(raw)
    except (OSError, ValueError):
        return None


def _resting(run):
    """Pressure and energy are retired (tasks 9e5678ac, bb4bcf2c): the only self-report is a tree turn's rest: true.
    True when the latest turn asked to rest, False when it did not, None when there is no tree turn to read."""
    rounds = sorted(Path(run).glob('round-*.json'), reverse=True)
    if not rounds:
        return None
    report = _json(rounds[0])
    return None if not isinstance(report, dict) else report.get('rest') is True


def _work(run):
    """What a tree agent is working on: its plan role, latest parent directive and linked task."""
    run = Path(run)
    session = run.parent
    tree = (_json(session / 'plan.json', 4194304) or {}).get('tree')
    node = tree.get(run.name) if isinstance(tree, dict) else None
    if not isinstance(node, dict):
        return {'name': None, 'session': None, 'task': None, 'directive': None, 'task_id': None}
    directive = None
    if node.get('parent'):
        for path in sorted((session / node['parent']).glob('round-*.json'), reverse=True):
            directives = (_json(path) or {}).get('directives')
            if isinstance(directives, dict) and isinstance(directives.get(run.name), str):
                directive = directives[run.name][:300]
                break
    link = _json(session / 'task.json') or {}
    if not link:
        campaign = _json(session.parent / 'campaign-task.json') or {}
        if isinstance(campaign.get('sessions_since'), str) and session.name >= campaign['sessions_since']:
            link = campaign
    task_id = link.get('id') if isinstance(link.get('id'), str) else None
    level, role = LEVELS.get(node.get('level'), '?'), str(node.get('role', ''))
    task = role if role.startswith(level) else f'{level} · {role}'
    return {'name': run.name, 'session': session.name, 'task': task[:200],
            'directive': directive, 'task_id': task_id}


def roster(path=None):
    try:
        with closing(sqlite3.connect(Path(path or budget_path()).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT id, role, level, state, started, ended, run FROM astra_agents
                ORDER BY CASE state WHEN 'active' THEN 0 ELSE 1 END, started DESC, id""").fetchall()
        items = []
        for row in rows:
            item = {key: row[key] for key in ('id', 'role', 'level', 'state', 'started', 'ended')}
            item.update(resting=_resting(row['run']), credits=None, admiration=None, growth=None, **_work(row['run']))
            items.append(item)
        return {'available': True, 'items': items}
    except (sqlite3.Error, OSError, ValueError):
        return {'available': False, 'items': []}
