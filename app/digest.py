"""Read-only decision discovery; neither advice nor discovery grants authority.

LOW-5 proposed decision contract (NOT implemented by this module):

source       yes                         no                         change
signoff      existing approve            existing reject            change request; pending
intake_veto  existing human override      uphold veto; task blocked  task change request
human_close  accept current proof, close  reject proof; open rework  task change request

Every outcome requires a verified signed-in human, a nonblank note, current
source revision, an idempotency key, and binding to the displayed advice.
Protected rule-text decisions are excluded. Domain mutation, digest_decided
and operation caching must commit together. Approval never invokes publication,
spending, settlement or automation-mode changes. Change requests preserve source
state and expose their notes; No must never merely hide an unresolved card.
See docs/digest-low5-contract.md for implementation gates and proposed checks.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.effects import classify
from app.proofs import human_closable
from app.prototype import door_off
from app.recommendations import Recommendations
from app.services import RuleError
from app.signoffs import canonical_payload, response

router = APIRouter(prefix='/api/v1/digest')


class _AdviceReader:
    # Reuse the authoritative read implementation without exposing record().
    # Recommendations.__init__ authorizes writers, not demo digest readers.
    current = Recommendations.current

    def __init__(self, db):
        self.db = db


def _identity(service, user):
    if not isinstance(user, dict):
        raise RuleError('Resolved principal required', 401)
    principal = user.get('principal')
    allowed = principal in {'human', 'relay', 'codex', 'agent'}
    allowed = allowed or (principal == 'demo-header' and service.demo_identity == 'allow')
    if not allowed or not user.get('user_id') or not user.get('principal_id'):
        raise RuleError('Resolved principal required', 401)
    return user


def _closable(task, children, requirements=()):
    return bool(task.get('claimant')) and task['status'] in {'working', 'blocked'} and (
        human_closable(task['complexity'], children, requirements))


def _receipts(history, histories):
    # Same receipt shape as Proofs.requirements, read from the already-loaded event histories.
    depends_on = next((e['data']['depends_on'] for e in reversed(history) if e['kind'] == 'dependencies_set'), [])
    receipts = []
    for identifier in sorted(set(depends_on)):
        events = histories.get(identifier, [])
        acceptance = next((e['data'] for e in reversed(events)
                           if e['kind'] in ('proof_completed', 'locally_verified', 'paid')), {})
        receipts.append({'id': identifier, 'status': events[-1]['state'] if events else None,
                         'proof_id': acceptance.get('proof_id'), 'binding': acceptance.get('proof_binding')})
    return receipts


def build_digest(service, user):
    _identity(service, user)
    construction = door_off()
    advice = _AdviceReader(service.db)
    items = {}

    def add(kind, record_id, title, why, action, revision, actor, principal):
        item = {
            'kind': kind, 'id': record_id, 'title': title,
            'why_waiting': why, 'action': action, 'effect': classify(action),
            'revision': revision,
            'recommendation': advice.current(kind, record_id, revision),
            'provenance': {'construction': construction,
                           'requested_by': actor,
                           'requested_principal': principal}}
        key = (kind, record_id)
        if key in items and items[key] != item:
            raise RuleError('Conflicting digest source identity; refresh required', 409)
        items[key] = item

    # No pagination: the pending endpoint's LIMIT 100 is not a discovery bound.
    with service.db.engine.connect() as c:
        signoffs = [dict(r) for r in c.exec_driver_sql(
            'SELECT * FROM signoffs WHERE decision IS NULL ORDER BY created_at,id').mappings()]
        events = [dict(r) for r in c.exec_driver_sql(
            'SELECT * FROM events ORDER BY seq').mappings()]
        tasks = [dict(r) for r in c.exec_driver_sql(
            'SELECT id,title,creator,parent_id FROM tasks ORDER BY id').mappings()]
    histories = {}
    children = {}
    for task in tasks:
        if task['parent_id'] is not None:
            children.setdefault(task['parent_id'], []).append(task['id'])
    for event in events:
        event['data'] = json.loads(event['data'])
        histories.setdefault(event['task_id'], []).append(event)
    for row in signoffs:
        add('signoff', row['id'], row['summary'],
            'Awaiting an explicit sign-off decision: ' + row['action'],
            row['action'], row['payload_sha256'], row['requested_by'],
            row['requested_principal'])
    for row in tasks:
        history = histories.get(row['id'], [])
        if not history:
            raise RuleError('Task has no authoritative event state', 409)
        latest = history[-1]
        complexity = next((e['data']['complexity'] for e in reversed(history)
                           if e['data'].get('complexity') in {'HIGH', 'MEDIUM', 'LOW'}), 'HIGH')
        claimant = next((e['actor'] for e in reversed(history) if e['kind'] == 'taken'), None)
        task = {**row, 'status': latest['state'], 'complexity': complexity, 'claimant': claimant}
        screened = next((e for e in reversed(history) if e['kind'] == 'intake_screened'), None)
        # A finished task has nothing left for a veto decision to allow or stop.
        finished = task['status'] in ('completed', 'settled', 'cancelled', 'superseded')
        if screened and screened['data'].get('verdict') in {'veto', 'unavailable'} and not finished:
            data = screened['data']
            digest = data['text_sha256']
            overridden = any(e['kind'] in ('intake_overridden', 'intake_veto_upheld')
                             and e['data'].get('principal') == 'human'
                             and e['data'].get('text_sha256') == digest for e in history)
            if not overridden:
                add('intake_veto', row['id'], row['title'], data['reason'],
                    'intake_override', digest, screened['actor'], data.get('principal'))
        kids = children.get(row['id'], [])
        if _closable(task, kids, _receipts(history, histories) if complexity == 'HIGH' and not kids else ()):
            # Versioned binding includes all event mutations and child identities.
            _, revision = canonical_payload({'schema_version': 1,
                'kind': 'human_close', 'id': row['id'], 'title': row['title'],
                'status': task['status'], 'complexity': complexity,
                'claimant': claimant, 'latest_event_seq': latest['seq'],
                'children': sorted(kids)})
            taken = next(e for e in reversed(history) if e['kind'] == 'taken')
            add('human_close', row['id'], row['title'],
                'Claimed work eligible for human closure; proof and claimant gates still apply.',
                'close_human', revision, taken['actor'], taken['data'].get('principal'))
    ordered = [items[key] for key in sorted(items)]
    coverage = {'signoff': 'complete', 'intake_veto': 'complete',
                'human_close': 'complete', 'policy_decision': 'unsupported'}
    counts = {kind: sum(item['kind'] == kind for item in ordered)
              for kind in ('signoff', 'intake_veto', 'human_close')}
    # Unknown source cardinality is null, never an asserted zero.
    counts['policy_decision'] = None
    return {'items': ordered, 'coverage': coverage,
            'counts': {'total': len(ordered), 'by_kind': counts},
            'complete': all(value == 'complete' for value in coverage.values()),
            'checked_at': datetime.now(timezone.utc).isoformat()}


@router.get('')
def digest(request: Request):
    return response(build_digest(request.app.state.service,
                                 getattr(request.state, 'identity', None)))
