"""Read-only dashboard integration over explicit service-owned sources."""
import re
from datetime import datetime, timezone

from app.dashboard_live import build_snapshot
from app.dashboard_session_source import read_session_metadata
from app.services import RuleError


def session_name(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}', value))


def live_snapshot(service, user, roster, mode, sessions_root, *, task_id=None, session_id=None):
    observed = datetime.now(timezone.utc).isoformat()
    rows = roster.get('items', []) if isinstance(roster, dict) else []
    sessions = sorted({row['session'] for row in rows
                       if isinstance(row, dict) and session_name(row.get('session'))}, reverse=True)
    session = None
    if session_id is not None:
        if not session_name(session_id):
            raise RuleError('Invalid session selection', 422)
        if roster.get('available'):
            if session_id not in sessions:
                raise RuleError('Select a registered session', 404)
            session = read_session_metadata(session_id, base_dir=sessions_root)
        else:
            session = {'id': session_id, 'sources': {key: {'status': 'unavailable', 'event_at': None}
                       for key in ('plan', 'board', 'summary')}}
    selected = service.get(task_id) if task_id else None
    snapshot = build_snapshot(roster=roster, mode=mode, session=session, observed_at=observed)
    evidence = {row.get('id'): row for row in rows if isinstance(row, dict)}
    for agent in snapshot['agents']:
        row = evidence.get(agent['id'], {})
        # Never export source paths, directives or role/prompt prose.
        agent.update(name=row.get('name') if isinstance(row.get('name'), str) else None,
                     level=row.get('level') if type(row.get('level')) is int else None,
                     session=row.get('session') if session_name(row.get('session')) else None)
    listed = service.listing(user, 'all', 100, 0)['items']
    tasks = {row['id']: {'id': row['id'], 'title': row['title']} for row in listed}
    if selected:
        tasks[selected['id']] = {'id': selected['id'], 'title': selected['title']}
    snapshot['context'] = {'user': user, 'selected_task': task_id, 'selected_session': session_id,
                           'sessions': sessions, 'tasks': list(tasks.values())}
    return snapshot
