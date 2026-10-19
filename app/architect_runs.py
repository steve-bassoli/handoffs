"""Read-only Bob and Sue view: recent architect-team runs (task a6eb660f, designed by bob-the-architect and sue-the-architect).

Runs are found through the launcher's lease ledger, never by scanning folders. Metadata only, as sue asked:
no goals, conversations, directives, syntheses, personalities or paths. An active lease is not proof of live
activity, and unknown stays unknown.
"""
from contextlib import closing
from pathlib import Path
import re
import sqlite3

from app.agent_roster import _json
from app.api_budget import budget_path

NAME = re.compile(r'[a-z0-9][a-z0-9-]{0,40}')
TICKET = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
LEASE = {'active': 'active lease', 'released': 'released', 'failed': 'failed: needs explicit recovery'}


def _name(value):
    return value if isinstance(value, str) and NAME.fullmatch(value) else None


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _run(row):
    session = Path(row['run']).parent
    plan = _json(session / 'plan.json', 4194304) or {}
    summary = _json(session / 'summary.json') or {}
    tree = plan.get('tree') if isinstance(plan.get('tree'), dict) else {}
    cards = summary.get('cards') if isinstance(summary.get('cards'), dict) else {}
    team = [{'name': name, 'level': {1: 'HIGH', 2: 'MEDIUM', 3: 'LOW'}.get(node.get('level'), '?'), 'card': bool(cards.get(name))}
            for name, node in tree.items() if _name(name) and isinstance(node, dict)]
    turns = summary.get('turns') if isinstance(summary.get('turns'), list) else []
    rounds = [t['round'] for t in turns if isinstance(t, dict) and _count(t.get('round'))]
    stamp = summary.get('architect_stamp') if isinstance(summary.get('architect_stamp'), dict) else None
    unknown = summary.get('unknown_usage')
    stopped = summary.get('stopped_agents') if isinstance(summary.get('stopped_agents'), list) else None
    ticket = plan.get('ticket') if isinstance(plan.get('ticket'), str) and TICKET.fullmatch(plan['ticket']) else None
    return {'architect': _name(plan.get('root_name')) or _name(Path(row['run']).name) or 'unknown',
            'session': session.name if re.fullmatch(r'[0-9TZ]{16}-[a-z0-9-]{1,60}', session.name) else None,
            'ticket': ticket, 'started': row['started'], 'ended': row['ended'],
            'lease': LEASE.get(row['state'], 'unknown'), 'finished': bool(summary),
            'team': team, 'rounds': max(rounds) if rounds else None,
            'stamp': None if stamp is None else {'approved': stamp.get('approved') is True, 'round': _count(stamp.get('round'))},
            'rest_stops': len(stopped) if stopped is not None else None,
            'elapsed_minutes': summary.get('elapsed_minutes') if isinstance(summary.get('elapsed_minutes'), (int, float)) else None,
            'minutes_allowed': plan.get('minutes') if isinstance(plan.get('minutes'), (int, float)) else None,
            'upper_bound_cents': _count(summary.get('upper_bound_cents_for_reported_usage')),
            # Any unknown usage means the recorded bound may not cover the whole run.
            'cost_bound_complete': True if unknown == 0 or unknown is False else False if _count(unknown) or unknown is True else None}


def architect_runs(path=None, limit=40):
    try:
        with closing(sqlite3.connect(Path(path or budget_path()).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT run, state, started, ended FROM astra_agents WHERE level=1
                ORDER BY started DESC LIMIT ?""", (limit,)).fetchall()
        runs = [_run(row) for row in rows]
    except (sqlite3.Error, OSError, ValueError):
        return {'available': False, 'architects': []}
    # Architects lead; runs from before the architects (plain coordinators, experiments) fold into one group.
    groups, earlier = {}, []
    for run in runs:
        if run['architect'].endswith('-the-architect'):
            groups.setdefault(run['architect'], []).append(run)
        else:
            earlier.append(run)
    return {'available': True, 'architects': [{'name': name, 'runs': items} for name, items in groups.items()],
            'earlier': earlier}
