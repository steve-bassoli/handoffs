"""Pure visibility projection; coverage is evidence, never inferred from nesting."""
from app.complexity import validate_bounty_split

MAX_TICKETS = 10000


def project_decomposition_visibility(lineage, detailsById, coverage):
    """Return contract v1 without mutating inputs or performing I/O.

    Invalid input envelopes raise ValueError. Orphans, cycles and duplicate IDs
    taint the snapshot. Missing parent fields leave topology incomplete globally.
    Work is O(n log n), memory O(n); graph traversal is iterative.
    """
    if not isinstance(lineage, list) or len(lineage) > MAX_TICKETS:
        raise ValueError('lineage must be a bounded list')
    if not isinstance(detailsById, dict) or not isinstance(coverage, dict):
        raise ValueError('detailsById and coverage must be objects')
    complete = coverage.get('complete_parent_ids', [])
    if (not isinstance(complete, list) or len(complete) > MAX_TICKETS
            or any(not isinstance(key, str) for key in complete)):
        raise ValueError('complete_parent_ids must be a bounded string list')
    complete = set(complete)
    nodes = {}
    invalid = False
    incomplete = False
    for row in lineage:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or not row['id']):
            raise ValueError('each lineage row needs a nonempty string ID')
        key = row['id']
        parent = row.get('parent_id')
        if parent is not None and not isinstance(parent, str):
            raise ValueError('parent_id must be a string or null')
        incomplete |= 'parent_id' not in row
        invalid |= key in nodes
        nodes[key] = parent
    children = {key: [] for key in nodes}
    for key, parent in nodes.items():
        if parent is not None:
            if parent not in nodes:
                invalid = True
            else:
                children[parent].append(key)
    # Each parent pointer is visited at most once, even for deep chains.
    done = set()
    for start in nodes:
        path = set()
        current = start
        while current in nodes and current not in done:
            if current in path:
                invalid = True
                break
            path.add(current)
            current = nodes[current]
        done.update(path)

    def detail(key):
        value = detailsById.get(key, {})
        return value if isinstance(value, dict) else {}

    def classified(key):
        value = detail(key)
        return (value.get('classification_explicit') is True
                and value.get('complexity') in ('HIGH', 'MEDIUM', 'LOW'))

    tickets = []
    for key in sorted(nodes):
        child_ids = sorted(children[key])
        status = 'unknown'
        if invalid:
            reason = 'topology_invalid'
        elif incomplete:
            reason = 'topology_incomplete'
        elif key not in complete:
            reason = 'coverage_incomplete'
        elif not classified(key) or any(not classified(c) for c in child_ids):
            reason = 'classification_missing'
        elif not child_ids:
            status, reason = 'not_yet_split', 'no_children'
        else:
            try:
                validate_bounty_split(detail(key)['complexity'],
                                      [detail(c)['complexity'] for c in child_ids])
            except ValueError:
                status, reason = 'violation', 'split_invalid'
            else:
                status, reason = 'valid', 'split_valid'
        title = detail(key).get('title', key)
        if not isinstance(title, str):
            title = key
        tickets.append({'id': key, 'parent_id': nodes[key],
                        'child_ids': child_ids, 'title': title,
                        'status': status, 'reasons': [reason]})
    return {'schema_version': 1, 'tickets': tickets}
