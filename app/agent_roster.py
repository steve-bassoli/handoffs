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


def _pressure(run):
    for filename in ('answer.json', 'candidate.json'):
        try:
            report = _json(Path(run) / filename)
            if report is None:
                continue
            if filename == 'answer.json':
                if report.get('state') != 'completed':
                    continue
                report = json.loads(report['text'])
            value = report.get('pressure_level')
            if type(value) is int and 1 <= value <= 3:
                return value
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    for path in sorted(Path(run).glob('round-*.json'), reverse=True):  # Tree turns report 'pressure'.
        value = (_json(path) or {}).get('pressure')
        if type(value) is int and 1 <= value <= 3:
            return value
    return None


def _work(run):
    """What a tree agent is working on: its plan role, latest parent directive and linked opportunity."""
    run = Path(run)
    session = run.parent
    tree = (_json(session / 'plan.json', 4194304) or {}).get('tree')
    node = tree.get(run.name) if isinstance(tree, dict) else None
    if not isinstance(node, dict):
        return {'name': None, 'session': None, 'task': None, 'directive': None, 'opportunity': None}
    directive = None
    if node.get('parent'):
        for path in sorted((session / node['parent']).glob('round-*.json'), reverse=True):
            directives = (_json(path) or {}).get('directives')
            if isinstance(directives, dict) and isinstance(directives.get(run.name), str):
                directive = directives[run.name][:300]
                break
    link = _json(session / 'opportunity.json') or {}
    if not link:
        campaign = _json(session.parent / 'campaign-opportunity.json') or {}
        if isinstance(campaign.get('sessions_since'), str) and session.name >= campaign['sessions_since']:
            link = campaign
    opportunity = link.get('id') if isinstance(link.get('id'), str) else None
    level, role = LEVELS.get(node.get('level'), '?'), str(node.get('role', ''))
    task = role if role.startswith(level) else f'{level} · {role}'
    return {'name': run.name, 'session': session.name, 'task': task[:200],
            'directive': directive, 'opportunity': opportunity}


def roster(path=None):
    try:
        with closing(sqlite3.connect(Path(path or budget_path()).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT id, role, level, state, started, ended, run FROM astra_agents
                ORDER BY CASE state WHEN 'active' THEN 0 ELSE 1 END, started DESC, id""").fetchall()
        items = []
        for row in rows:
            item = {key: row[key] for key in ('id', 'role', 'level', 'state', 'started', 'ended')}
            item.update(pressure=_pressure(row['run']), credits=None, admiration=None, growth=None, **_work(row['run']))
            items.append(item)
        return {'available': True, 'items': items}
    except (sqlite3.Error, OSError, ValueError):
        return {'available': False, 'items': []}
