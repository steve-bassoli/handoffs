"""Pure v1 snapshot builder. Explicit evidence requires an authorized adapter."""
from datetime import datetime
from .dashboard_session_source import integer, metadata, text

STATUSES = {'available', 'missing', 'invalid', 'unavailable'}


def _boolean(value):
    return value if type(value) is bool else None


def build_snapshot(*, roster=None, mode=None, session=None, observed_at):
    if not isinstance(observed_at, str):
        raise ValueError('UTC observation time required')
    try:
        stamp = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError('UTC required')
    except (ValueError, OverflowError) as exc:
        raise ValueError('UTC observation time required') from exc
    sources = {}
    def source(name, status, event_at=None):
        sources[name] = {'status': status, 'observed_at': observed_at, 'event_at': text(event_at)}
    agents = []
    source('roster', 'unavailable')
    if roster is not None:
        source('roster', 'invalid')
        if isinstance(roster, dict) and roster.get('available') is False:
            source('roster', 'unavailable')
        elif isinstance(roster, dict) and roster.get('available') is True:
            rows, seen = roster.get('items'), set()
            try:
                if not isinstance(rows, list) or len(rows) > 1000:
                    raise ValueError('invalid roster')
                for row in rows:
                    if not isinstance(row, dict):
                        raise ValueError('invalid agent')
                    identity = text(row.get('id'))
                    if identity is None or identity in seen:
                        raise ValueError('invalid or duplicate identifier')
                    seen.add(identity)
                    pressure = row.get('pressure')
                    agents.append({'id': identity, 'reported_activity': text(row.get('state'), 80),
                                   'live_confirmed': _boolean(row.get('live_confirmed')),
                                   'interrupted_occupied_lease': _boolean(row.get('interrupted_occupied_lease')),
                                   'pressure': pressure if type(pressure) is int and pressure in (1, 2, 3) else None,
                                   'source': 'roster', 'event_at': text(row.get('event_at'))})
                agents.sort(key=lambda row: row['id'])
                source('roster', 'available', roster.get('event_at'))
            except ValueError:
                agents = []
    normalized_mode = {'value': None, 'agents': None, 'automated_writes': None, 'source': 'mode'}
    source('mode', 'unavailable' if mode is None else 'invalid')
    if isinstance(mode, dict):
        value = mode.get('mode')
        if value in ('manual', 'light', 'heavy', 'max'):
            normalized_mode.update(value=value, agents=integer(mode.get('agents')),
                                   automated_writes=_boolean(mode.get('automated_writes')))
            source('mode', 'available')
    normalized_session = {'id': None, 'plan': None, 'board': None, 'summary': None}
    if isinstance(session, dict):
        normalized_session['id'] = text(session.get('id'))
    for kind in ('plan', 'board', 'summary'):
        source(kind, 'unavailable' if session is None else 'invalid')
        if not isinstance(session, dict) or not isinstance(session.get('sources'), dict):
            continue
        record = session['sources'].get(kind)
        if not isinstance(record, dict):
            continue
        status = record.get('status')
        if not isinstance(status, str) or status not in STATUSES:
            continue
        if status == 'available':
            try:
                normalized_session[kind] = metadata(kind, session.get(kind))
            except (ValueError, TypeError, OverflowError):
                status = 'invalid'
        source(kind, status, record.get('event_at') if status == 'available' else None)
    return {'schema_version': 1, 'observed_at': observed_at, 'sources': sources,
            'agents': agents, 'mode': normalized_mode, 'session': normalized_session}
