"""Digest-approved rule texts. Production loads once at import; no database or network."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

# Mirrors the authoritative users table; changes require human review.
HUMANS = {'steve', 'nate', 'will'}
# Relay: compute from the exact final rules/agent-rules.json bytes; never rotate
# this pin to authorize a later rules change.
BOOTSTRAP_SHA256 = 'a216db419232e9f435cf6ef9f5257462836beba370193a3ba175bb5dbf836d5a'
ROOT = Path(__file__).resolve().parents[1]
TEXT_KEYS = frozenset({
    'COMMONS_RULES', 'PRESSURE_RULES', 'RULES', 'TREE_RULES',
    'CONDUIT_PREFIX', 'CHAT_PREFIX', 'SHARED', 'COORDINATOR_PREFIX',
    'LEAD_PREFIX', 'WORKER_PREFIX', 'SPACE',
})
COMPOSITION_KEYS = frozenset({'CONDUIT_MISSION', 'CHAT_MISSION', 'coordinator', 'lead', 'worker'})


class RulesError(RuntimeError):
    """Startup must stop rather than use unapproved or fallback instructions."""


def _fail(message):
    raise RulesError('Protected agent rules: ' + message)


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail('duplicate JSON key: ' + key)
        value[key] = item
    return value


def _json(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_object)


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError:
        return False


def load_rules(rules_path=ROOT / 'rules/agent-rules.json', approvals_path=ROOT / 'rules/APPROVALS.json'):
    """Validate one snapshot; explicit paths support offline negative tests."""
    try:
        raw = Path(rules_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        data = _json(raw)
        approvals = _json(Path(approvals_path).read_bytes())
        if not isinstance(data, dict) or set(data) != {'texts', 'compositions'}:
            _fail('expected texts and compositions objects')
        texts, compositions = data['texts'], data['compositions']
        if not isinstance(texts, dict) or set(texts) != TEXT_KEYS:
            _fail('missing or unexpected text names')
        if any(not isinstance(value, str) or not value for value in texts.values()):
            _fail('texts must be nonempty strings')
        if not isinstance(compositions, dict) or set(compositions) != COMPOSITION_KEYS:
            _fail('missing or unexpected composition names')
        for parts in compositions.values():
            if (not isinstance(parts, list) or not parts or
                    any(not isinstance(part, str) or part not in texts for part in parts)):
                _fail('compositions must reference named texts')
        if not isinstance(approvals, list) or not approvals:
            _fail('approval ledger must be a nonempty list')
        approved = False
        required = {'sha256', 'approved_by', 'approved_at', 'note'}
        allowed = required | {'bootstrap', 'pending_second_approver'}
        for entry in approvals:
            if not isinstance(entry, dict) or not required <= set(entry) or set(entry) - allowed:
                _fail('malformed approval entry')
            names = entry['approved_by']
            if (not _digest(entry['sha256']) or not isinstance(names, list) or not names or
                    any(not isinstance(name, str) or name not in HUMANS for name in names) or
                    len(set(names)) != len(names)):
                _fail('approval requires distinct known human IDs and a SHA-256 digest')
            if not isinstance(entry['note'], str) or not entry['note'].strip():
                _fail('approval note is required')
            if not _timestamp(entry['approved_at']):
                _fail('approval requires an actual timezone-aware timestamp')
            bootstrap = entry.get('bootstrap', False)
            if type(bootstrap) is not bool:
                _fail('bootstrap must be boolean')
            if 'pending_second_approver' in entry and entry['pending_second_approver'] not in HUMANS:
                _fail('pending approver must be a known human ID')
            if entry['sha256'] != digest:
                continue
            if len(names) >= 2:
                approved = True
            elif (bootstrap is True and names == ['steve'] and
                    _digest(BOOTSTRAP_SHA256) and digest == BOOTSTRAP_SHA256):
                approved = True
        if not approved:
            _fail('current SHA-256 has no two-human approval or exact pinned bootstrap approval')
        result = dict(texts)
        result.update({name: ''.join(texts[part] for part in parts)
                       for name, parts in compositions.items()})
        return MappingProxyType(result)
    except RulesError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise RulesError('Protected agent rules: missing, unreadable or malformed rules/approval files') from error


_LOADED = load_rules()
COMMONS_RULES = _LOADED['COMMONS_RULES']
PRESSURE_RULES = _LOADED['PRESSURE_RULES']
RULES = _LOADED['RULES']
TREE_RULES = _LOADED['TREE_RULES']
SHARED = _LOADED['SHARED']
CONDUIT_MISSION = _LOADED['CONDUIT_MISSION']
CHAT_MISSION = _LOADED['CHAT_MISSION']
ROLE_RULES = MappingProxyType({name: _LOADED[name] for name in ('coordinator', 'lead', 'worker')})
