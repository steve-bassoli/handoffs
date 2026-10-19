"""Read-only decision discovery; neither advice nor discovery grants authority.

LOW-5 proposed decision contract (NOT implemented by this module):

source       yes                         no                         change
signoff      existing approve            existing reject            change request; pending
intake_veto  existing human override      uphold veto; task blocked  task change request
human_close  accept current proof, close  reject proof; open rework  task change request

Every outcome requires a verified signed-in human, a nonblank note, current
source revision, an idempotency key, and binding to the displayed advice.
Protected rule-text proposals appear as rule_texts items (task 2c56ad7a): each
person decides once, and two distinct acceptances apply them (app.rule_proposals). Domain mutation, digest_decided
and operation caching must commit together. Approval never invokes publication,
spending, settlement or automation-mode changes. Change requests preserve source
state and expose their notes; No must never merely hide an unresolved card.
See docs/digest-low5-contract.md for implementation gates and proposed checks.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.effects import classify
from app import rule_proposals
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


CONSTRUCTION_CLOSE = 'construction mode: the relay closes proven work itself (labelled door-off)'


def _mark_ready(service, ordered, construction=False):
    """Steve, 2026-10-18: show only what a click can complete now; everything else says what it waits on.

    Task 33a5d860 (veto overridden 2026-10-19 02:13 in Nate's session, clicked by Steve with Nate in the room): while construction mode is on, task closes are the relay's to make
    under the first door, so they fold away; rule texts, vetoes and sign-offs stay with people. Deciding is unchanged."""
    detail = getattr(service, 'detail', None)
    for item in ordered:
        item['ready'], item['waiting_on'] = True, None
        if construction and item['kind'] == 'human_close':
            item['ready'], item['waiting_on'] = False, CONSTRUCTION_CLOSE
    if detail is None:
        return
    with service.db.engine.connect() as c:
        for item in ordered:
            if item['kind'] == 'human_close' and item['ready']:
                if not ((detail(c, item['id']).get('proof') or {}).get('fresh')):
                    item['ready'], item['waiting_on'] = False, 'needs proof first'
            elif item['kind'] == 'intake_veto':
                task = detail(c, item['id'])
                if task['status'] not in ('open', 'blocked') or task['claimant'] is not None:
                    item['ready'], item['waiting_on'] = False, 'already being worked on, so the veto cannot be decided here'


def build_digest(service, user):
    _identity(service, user)
    construction = door_off()
    advice = _AdviceReader(service.db)
    items = {}

    def add(kind, record_id, title, why, action, revision, actor, principal, details=None):
        item = {
            'kind': kind, 'id': record_id, 'title': title,
            'why_waiting': why, 'action': action, 'effect': classify(action),
            'revision': revision,
            # Rule texts carry no advisory snapshot: the people deciding read the texts themselves.
            'recommendation': {'status': 'unavailable'} if kind == 'rule_texts' else advice.current(kind, record_id, revision),
            'provenance': {'construction': construction,
                           'requested_by': actor,
                           'requested_principal': principal}}
        if details is not None:
            item['details'] = details
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
        proposals = rule_proposals.pending(c)
    for proposal in proposals:
        # A person who already decided is no longer waited on; the card stays for the others.
        if any(d['decided_by'] == user['user_id'] for d in proposal['decisions']):
            continue
        add('rule_texts', proposal['id'], proposal['title'], rule_proposals.why(proposal), 'rule_texts',
            proposal['sha256'], proposal['author'], 'proposal',
            {'changed': proposal['changed'], 'decisions': proposal['decisions'], 'needed': rule_proposals.NEEDED})
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
    _mark_ready(service, ordered, construction)
    coverage = {'signoff': 'complete', 'intake_veto': 'complete',
                'human_close': 'complete', 'rule_texts': 'complete', 'policy_decision': 'unsupported'}
    counts = {kind: sum(item['kind'] == kind for item in ordered)
              for kind in ('signoff', 'intake_veto', 'human_close', 'rule_texts')}
    # Unknown source cardinality is null, never an asserted zero.
    counts['policy_decision'] = None
    return {'items': ordered, 'coverage': coverage,
            'counts': {'total': len(ordered), 'ready': sum(item['ready'] for item in ordered), 'by_kind': counts},
            'complete': all(value == 'complete' for value in coverage.values()),
            'checked_at': datetime.now(timezone.utc).isoformat()}


@router.get('')
def digest(request: Request):
    return response(build_digest(request.app.state.service,
                                 getattr(request.state, 'identity', None)))
