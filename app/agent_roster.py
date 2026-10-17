"""Read-only projection of registered Astra runs, not a process monitor or wallet."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from app.api_budget import budget_path


def _pressure(run):
    for filename in ('answer.json', 'candidate.json'):
        try:
            with (Path(run) / filename).open('rb') as source:
                raw = source.read(262145)
            if len(raw) > 262144:
                continue
            report = json.loads(raw)
            if filename == 'answer.json':
                if report.get('state') != 'completed':
                    continue
                report = json.loads(report['text'])
            value = report.get('pressure_level')
            if type(value) is int and 1 <= value <= 3:
                return value
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return None


def roster(path=None):
    try:
        with closing(sqlite3.connect(Path(path or budget_path()).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT id, role, level, state, started, ended, run FROM astra_agents
                ORDER BY CASE state WHEN 'active' THEN 0 ELSE 1 END, started DESC, id""").fetchall()
        items = []
        for row in rows:
            item = {key: row[key] for key in ('id', 'role', 'level', 'state', 'started', 'ended')}
            item.update(pressure=_pressure(row['run']), credits=None, admiration=None, growth=None)
            items.append(item)
        return {'available': True, 'items': items}
    except (sqlite3.Error, OSError, ValueError):
        return {'available': False, 'items': []}
