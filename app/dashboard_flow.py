"""Pure v1-r2 adapter projection; upstream completeness is always unknown.

Inputs are normalized authorized adapter data, not a claimed live API shape.
Assignment is supplied confirmation evidence, not resolved human acceptance.
"""

KINDS = frozenset(('posted', 'followup_confirmed', 'package_attached',
                   'dependencies_set', 'taken', 'reopened', 'ai_started', 'ai_failed'))


def _valid(value):
    return isinstance(value, str) and bool(value.strip())


def _limit(value):
    if type(value) is not int:
        raise TypeError('caps must be integers, excluding bool')
    return max(0, min(100, value))


def build_dashboard_flow(lineage, details, *, current_id=None, observed_at=None,
                         max_tickets=100, max_activity=100):
    """Project without mutations, fetching, inferred tickets, or payload export."""
    ticket_cap, activity_cap = _limit(max_tickets), _limit(max_activity)
    if not isinstance(lineage, dict) or not isinstance(lineage.get('items'), list):
        raise TypeError('lineage must contain an items list')
    if not isinstance(details, dict):
        raise TypeError('details must be a dictionary keyed by ticket ID')
    if any(v is not None and not isinstance(v, str) for v in (current_id, observed_at)):
        raise TypeError('current_id and observed_at must be strings or None')
    issues, rows, signatures = [], {}, {}

    def issue(code):
        if code not in issues:
            issues.append(code)

    for row in lineage['items']:
        if not isinstance(row, dict) or not _valid(row.get('id')):
            issue('invalid_id')
            continue
        key = row['id']
        signature = tuple((field in row, row.get(field))
                          for field in ('parent_id', 'title', 'status'))
        if key in rows:
            issue('duplicate_id')
            if signature != signatures[key]:
                issue('conflicting_evidence')
            continue
        signatures[key] = signature
        parent = row.get('parent_id')
        known = 'parent_id' in row and (parent is None or _valid(parent))
        if parent is not None and not _valid(parent):
            issue('invalid_parent')
        rows[key] = {'id': key, 'parent_id': parent if known else None,
                     'parent_known': known,
                     'title': row['title'][:240] if _valid(row.get('title')) else 'Unknown',
                     'status': row['status'] if _valid(row.get('status')) else 'Unknown',
                     'assigned_agent': None, 'assignment_source': None,
                     'detail_available': False}
    # Validate full supplied topology before any display cap; never repair it.
    for row in rows.values():
        if row['parent_id'] is not None and row['parent_id'] not in rows:
            issue('orphan_parent')
    finished = set()
    for key in rows:
        path, cursor = set(), key
        while cursor in rows and cursor not in finished:
            if cursor in path:
                issue('cycle')
                break
            path.add(cursor)
            cursor = rows[cursor]['parent_id']
        finished.update(path)
    tickets = list(rows.values())[:ticket_cap]
    activity, eligible, missing = [], 0, 0
    for ticket in tickets:
        detail = details.get(ticket['id'])
        if not isinstance(detail, dict):
            missing += 1
            issue('missing_detail')
            continue
        ticket['detail_available'] = True
        events = detail.get('events', [])
        if not isinstance(events, list):
            issue('invalid_events')
            continue
        agents = set()
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                issue('invalid_events')
                continue
            kind = event.get('kind')
            if not isinstance(kind, str) or kind not in KINDS:
                continue
            # Scan confirmation evidence even after activity output is full.
            data = event.get('data')
            if kind == 'followup_confirmed' and isinstance(data, dict):
                agent = data.get('assigned_agent')
                if _valid(agent):
                    agents.add(agent)
                    ticket['assigned_agent'] = agent
                    ticket['assignment_source'] = 'followup_confirmed'
                    if len(agents) > 1:
                        issue('conflicting_assignment')
            eligible += 1
            if len(activity) < activity_cap:
                timestamp = event.get('created_at')
                activity.append({'ticket_id': ticket['id'], 'kind': kind,
                                 'event_time': timestamp if _valid(timestamp) else None,
                                 'source_index': index})
    tickets_truncated = len(rows) > len(tickets)
    activity_truncated = eligible > len(activity)
    if tickets_truncated:
        issue('tickets_truncated')
    if activity_truncated:
        issue('activity_truncated')
    return {'version': 1, 'observed_at': observed_at, 'current_id': current_id,
            'tickets': tickets, 'activity': activity, 'issues': issues,
            'coverage': {'tickets_supplied': len(rows), 'tickets_shown': len(tickets),
                         'activity_eligible': eligible, 'activity_shown': len(activity),
                         'tickets_truncated': tickets_truncated,
                         'activity_truncated': activity_truncated,
                         'details_missing': missing}}
