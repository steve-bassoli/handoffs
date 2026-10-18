"""Pure dashboard_ops_v1/R2 normalization; no I/O or inferred proof."""
from copy import deepcopy
import math
import re

MAX = 9007199254740991
STATES = {'pending', 'reported_upper', 'unknown_conservative', 'unknown', 'overrun'}
SOURCES = ('ledger', 'session_usage', 'wallet', 'codex', 'leases', 'git')
ERRORS = {'source_unavailable', 'invalid_data', 'adapter_required',
          'invalid_read_bound', 'ledger_unavailable', 'git_unavailable'}


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def _cents(value):
    return type(value) is int and 0 <= value <= MAX


def _number(value):
    return (type(value) in (int, float) and 0 <= value <= MAX
            and math.isfinite(value))


def _ledger(data):
    ceiling, baseline = data.get('ceiling_cents'), data.get('baseline_cents')
    holds, total, seen = data.get('holds'), 0, set()
    valid = data.get('reservations_complete') is True
    valid = valid and _cents(ceiling) and _cents(baseline)
    clean = []
    if not isinstance(holds, list):
        valid = False
    else:
        for hold in holds:
            if not isinstance(hold, dict):
                valid = False
                continue
            ident, state, amount = (hold.get('id'), hold.get('state'),
                                    hold.get('held_cents'))
            if (not _text(ident) or ident in seen or not isinstance(state, str)
                    or state not in STATES or not _cents(amount)):
                valid = False
                continue
            seen.add(ident)
            total += amount
            clean.append({'id': ident, 'state': state, 'held_cents': amount})
    blocked = any(row['state'] in ('unknown', 'overrun') for row in clean)
    valid = valid and total <= MAX and not any(row['state'] == 'overrun' for row in clean)
    valid = valid and _cents(baseline) and baseline + total <= MAX
    return {'ceiling_cents': ceiling if _cents(ceiling) else None,
            'baseline_cents': baseline if _cents(baseline) else None,
            'reservations_complete': data.get('reservations_complete') is True,
            'holds': clean, 'provenance': _text(data.get('provenance')),
            'held_upper_bound_cents': total if valid else None,
            'source_headroom_cents': ceiling - baseline - total if valid else None,
            'guarded_headroom_cents':
                min(ceiling, 199800) - baseline - total if valid and not blocked else None}


def _data(name, data):
    if not isinstance(data, dict):
        raise ValueError('invalid data')
    if name == 'ledger':
        return _ledger(data)
    if name == 'session_usage':
        value = data.get('reported_upper_cents')
        return {'reported_upper_cents': value if _cents(value) else None}
    if name == 'wallet':
        value = data.get('gold')
        return {'gold': value if _number(value) else None}
    if name == 'codex':
        value = data.get('amount')
        return {'amount': value if _number(value) else None,
                'unit': _text(data.get('unit'))}
    if name == 'leases':
        records = data.get('records')
        if not isinstance(records, list):
            raise ValueError('invalid records')
        clean = []
        for row in records:
            if not isinstance(row, dict) or not _text(row.get('id')):
                raise ValueError('invalid record')
            if not _text(row.get('state')):
                raise ValueError('invalid state')
            clean.append({'id': row['id'], 'state': row['state'],
                          'evidence': _text(row.get('evidence'))})
        result = {'records': clean}
        for key in ('verified_live_count', 'interrupted_occupied_count'):
            value = data.get(key)
            result[key] = value if _cents(value) else None
        return result
    commit = data.get('commit')
    if commit is None:
        return {'commit': None}
    if (not isinstance(commit, dict)
            or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',
                                str(commit.get('hash', '')))
            or not _text(commit.get('committed_at'))):
        raise ValueError('invalid commit')
    return {'commit': {'hash': commit['hash'],
                       'committed_at': commit['committed_at']}}


def normalize_ops(raw, previous=None):
    """Caller supplies authorized, non-secret source identities and metadata."""
    sources = raw.get('sources', {}) if isinstance(raw, dict) else {}
    sources = sources if isinstance(sources, dict) else {}
    old = previous.get('sources', {}) if isinstance(previous, dict) else {}
    old = old if isinstance(old, dict) else {}
    result = {'version': 1, 'policy': {'protected_cents': 100,
              'sponsor_guard_cents': 199800, 'tests_gated_before_commit': True},
              'sources': {}, 'tests': {'status': 'not_recorded', 'provenance': None}}
    for name in SOURCES:
        item = sources.get(name)
        item = item if isinstance(item, dict) else {}
        ident = _text(item.get('source_id'))
        error = item.get('error_code')
        error = error if isinstance(error, str) and error in ERRORS else 'source_unavailable'
        envelope = {'status': 'unavailable', 'source_id': ident,
                    'observed_at': None,
                    'last_attempt_at': _text(item.get('last_attempt_at')),
                    'error_code': error, 'data': None}
        if item.get('status') == 'ok':
            try:
                envelope.update(status='ok', data=_data(name, item.get('data')),
                                observed_at=_text(item.get('observed_at')), error_code=None)
            except (ValueError, TypeError, OverflowError):
                envelope['error_code'] = 'invalid_data'
        prior = old.get(name)
        if (envelope['status'] != 'ok' and ident is not None
                and isinstance(prior, dict) and prior.get('source_id') == ident
                and prior.get('status') in ('ok', 'stale')
                and isinstance(prior.get('data'), dict)):
            try:
                envelope.update(status='stale', data=_data(name, prior['data']),
                                observed_at=_text(prior.get('observed_at')))
            except (ValueError, TypeError, OverflowError):
                pass
        result['sources'][name] = envelope
    return deepcopy(result)
