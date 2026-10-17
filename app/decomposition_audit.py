"""Project an explicitly authorized audit reader; no endpoint or DB setup.

The zero-argument reader returns existing Service parent/reason dictionaries.
Authorization must precede invocation. Service.hierarchy_violations scans all
parents; scope is a display label, not a filter. Review reader/plugin behavior
separately: injection is not a sandbox. No retries or decomposition rules here.
"""

SOURCE = 'Service.hierarchy_violations'
DEFAULT_HIGH_CAVEAT = 'Service.detail defaults missing complexity to HIGH.'
LIMITATIONS = (
    DEFAULT_HIGH_CAVEAT,
    'Scope is a caller-supplied display label, not authorization or filtering.',
    'Source and checked_at are provenance labels, not proof of correctness.',
)


def build_decomposition_audit(authorized_reader, *, checked_at, scope):
    """Return audit-v1-r1; reader text must already be authorized for display.

    Invalid caller metadata raises before invocation. Reader failures and bad
    records yield unavailable, never a misleading empty result. Extra raw
    fields are omitted; exception details are never disclosed.
    """
    if not isinstance(checked_at, str) or not isinstance(scope, str):
        raise TypeError('checked_at and scope must be strings')
    payload = {
        'version': 1,
        'source': SOURCE,
        'checked_at': checked_at,
        'scope': scope,
        'status': 'unavailable',
        'violations': None,
        'error': 'Audit unavailable',
        'limitations': list(LIMITATIONS),
    }
    try:
        if not callable(authorized_reader):
            return payload
        rows = authorized_reader()
        if not isinstance(rows, list):
            return payload
        pairs = set()
        for row in rows:
            if not isinstance(row, dict):
                return payload
            ticket_id, message = row.get('parent'), row.get('reason')
            if not isinstance(ticket_id, str) or not ticket_id.strip():
                return payload
            if not isinstance(message, str) or not message.strip():
                return payload
            pairs.add((ticket_id, message))
        violations = [
            {'ticket_id': ticket_id, 'message': message}
            for ticket_id, message in sorted(pairs)
        ]
    except Exception:
        return payload
    payload.update(
        status='findings' if violations else 'checked_empty',
        violations=violations,
        error=None,
    )
    return payload
