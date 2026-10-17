"""Build an offline inventory from caller-supplied transport evidence."""
import json

_OPERATIONS = (
    ('projects', 'GET /api/v1/projects'),
    ('project_studies', 'GET /api/v1/projects/{projectId}/studies'),
    ('study_detail', 'GET /api/v1/studies/{studyId}'),
)
_TRANSPORTS = ('REST', 'SOAP', 'MCP')
_REQUIRED = ('operation', 'transport', 'reference', 'outcome', 'verification',
             'provenance', 'synthetic')


def _require(record):
    if not isinstance(record, dict) or any(key not in record for key in _REQUIRED):
        raise ValueError('each record must contain required evidence fields')
    operation, transport = record['operation'], record['transport']
    if (not isinstance(operation, str) or operation not in dict(_OPERATIONS)
            or not isinstance(transport, str) or transport not in _TRANSPORTS):
        raise ValueError('unknown operation or transport')
    if not isinstance(record['reference'], str) or not record['reference']:
        raise ValueError('reference must be nonempty text')
    if record['outcome'] not in ('pass', 'fail'):
        raise ValueError('outcome must be pass or fail')
    if record['verification'] not in ('reported', 'verified'):
        raise ValueError('verification must be reported or verified')
    if not isinstance(record['provenance'], str) or not record['provenance']:
        raise ValueError('provenance must be nonempty text')
    if record['synthetic'] is not True:
        raise ValueError('synthetic must be true')
    binding = record.get('binding')
    verification_reference = record.get('verification_reference')
    if binding is not None and (not isinstance(binding, str) or not binding):
        raise ValueError('binding must be nonempty text or null')
    if verification_reference is not None and (
            not isinstance(verification_reference, str)
            or not verification_reference):
        raise ValueError('verification_reference must be nonempty text or null')
    if record['verification'] == 'reported' and verification_reference is not None:
        raise ValueError('reported evidence has no verification_reference')
    if record['verification'] == 'verified' and not verification_reference:
        raise ValueError('verified evidence needs verification_reference')


def _evidence(record):
    keys = ('binding', 'reference', 'outcome', 'verification',
            'verification_reference', 'provenance', 'synthetic')
    return {key: record.get(key) for key in keys}


def _cell(operation, route, transport, records):
    evidence, seen = [], set()
    for record in records:
        item = _evidence(record)
        marker = json.dumps(item, sort_keys=True, separators=(',', ':'))
        if marker not in seen:
            seen.add(marker)
            evidence.append(item)
    bindings = {item['binding'] for item in evidence if item['binding']}
    outcomes = {item['outcome'] for item in evidence}
    binding = route if transport == 'REST' else (
        next(iter(bindings)) if len(bindings) == 1 else None)
    conflict = len(outcomes) > 1 or len(bindings) > 1
    if transport == 'REST' and any(
            item['binding'] and item['binding'] != route for item in evidence):
        conflict = True
    state = 'gap' if not evidence else ('conflict' if conflict else 'evidence')
    return {'operation': operation, 'transport': transport, 'binding': binding,
            'state': state, 'evidence': evidence}


def build_inventory(records):
    """Return all nine cells without I/O, fetching, or verification."""
    if not isinstance(records, list):
        raise ValueError('records must be a list')
    grouped = {}
    for record in records:
        _require(record)
        grouped.setdefault((record['operation'], record['transport']), []).append(record)
    cells = []
    for operation, route in _OPERATIONS:
        for transport in _TRANSPORTS:
            cells.append(_cell(operation, route, transport,
                               grouped.get((operation, transport), [])))
    return {'schema_version': 1, 'mode': 'offline_inventory', 'cells': cells}
