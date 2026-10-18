"""Decision digest LOW-5: one audited human decision per waiting item (contract: docs/digest-low5-contract.md).

source       yes                              no                               change
signoff      approve (decision_mode human)    reject                           change request; stays pending
intake_veto  existing human override          veto upheld; task blocked        change request on the task
human_close  accept current proof, complete   reject proof; task stays open    change request on the task

Only a signed-in person decides (never demo headers, relay, codex or agent tokens, even with the door off).
A stale revision is refused with the current one. Mutation and audit commit together through Service.execute.
Approving a sign-off never consumes it; no decision publishes, changes the automation mode or spends beyond
the escrow that accepting a funded task already settles (Steve, 2026-10-18).
"""
import json
import time
from typing import Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from app.services import RuleError
from app.storage import one

router = APIRouter(prefix='/api/v1/digest')


class Decision(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    kind: Literal['signoff', 'intake_veto', 'human_close']
    id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=64, max_length=64)
    decision: Literal['yes', 'no', 'change']
    note: str = Field(min_length=1, max_length=2000)
    recommendation_id: str | None = Field(default=None, max_length=200)


def signed_in_person(request):
    identity = getattr(request.state, 'identity', None) or {}
    if identity.get('principal') != 'human' or not identity.get('principal_id'):
        raise RuleError('Digest decisions need a signed-in person', 403)
    return identity


def _snapshot(c, payload):
    if not payload.get('recommendation_id'):
        return None
    row = one(c, 'SELECT * FROM recommendations WHERE id=? AND item_kind=? AND item_id=? AND item_revision=?',
              (payload['recommendation_id'], payload['kind'], payload['id'], payload['revision']))
    if not row:
        raise RuleError('Recommendation does not match this item version', 409)
    return {k: row[k] for k in ('id', 'disposition', 'rationale', 'created_by', 'created_principal', 'created_at')}


def decide(service, c, actor, payload, identity):
    """Runs inside Service.execute's write transaction (action ai_digest_decide)."""
    from app.digest import build_digest
    current = next((i for i in build_digest(service, identity)['items']
                    if i['kind'] == payload['kind'] and i['id'] == payload['id']), None)
    if current is None:
        raise RuleError('This item is no longer waiting on a person', 409)
    if current['revision'] != payload['revision']:
        raise RuleError({'message': 'The item changed; review the current version', 'revision': current['revision']}, 409)
    advice = _snapshot(c, payload)
    audit = {'kind': payload['kind'], 'decision': payload['decision'], 'revision': payload['revision'],
             'note': payload['note'], 'recommendation_id': payload.get('recommendation_id'),
             'recommendation_snapshot': advice, 'decided_by': actor, 'principal_id': identity['principal_id']}
    kind, choice, note = payload['kind'], payload['decision'], payload['note']
    if kind == 'signoff':
        now = int(time.time())
        if choice == 'change':
            changed = c.exec_driver_sql('UPDATE signoffs SET change_note=?, change_requested_by=?, change_requested_at=?, digest_audit_json=? '
                                        'WHERE id=? AND decision IS NULL', (note, actor, now, json.dumps(audit), payload['id']))
        else:
            changed = c.exec_driver_sql("UPDATE signoffs SET decided_by=?, decided_principal='human', decided_principal_id=?, decision=?, "
                                        "decision_note=?, decision_mode='human', decided_at=?, digest_audit_json=? WHERE id=? AND decision IS NULL",
                                        (actor, identity['principal_id'], 'approved' if choice == 'yes' else 'rejected', note, now,
                                         json.dumps(audit), payload['id']))
        if changed.rowcount != 1:
            raise RuleError('Sign-off already decided', 409)
        return {'kind': kind, 'id': payload['id'], 'decision': choice, 'consumed': False}
    if kind == 'intake_veto':
        if choice == 'yes':
            service.do_intake_override(c, actor, {'id': payload['id'], 'note': note})
        else:
            task = service.detail(c, payload['id'])
            if choice == 'no':
                if task['status'] not in ('open', 'blocked') or task['claimant'] is not None:
                    raise RuleError('Only an unclaimed open or blocked task can have its veto upheld', 409)
                service.event(c, task['id'], 'intake_veto_upheld', actor, 'blocked', {'note': note, 'text_sha256': payload['revision']})
            else:
                service.event(c, task['id'], 'change_requested', actor, task['status'], {'note': note, 'source': 'intake_veto'})
    else:  # human_close
        task = service.detail(c, payload['id'])
        if choice in ('yes', 'no'):
            if not task.get('proof') or not task['proof'].get('fresh'):
                raise RuleError('no current proof', 409)
            service.do_ai_proof_human(c, actor, {'id': task['id'], 'accepted': choice == 'yes', 'note': note,
                                                 'review_basis': 'human-only'})
            if choice == 'yes':
                service.do_ai_proof_complete(c, actor, {'id': task['id'], 'note': note})
        else:
            service.event(c, task['id'], 'change_requested', actor, task['status'], {'note': note, 'source': 'human_close'})
    task = service.detail(c, payload['id'])
    service.event(c, task['id'], 'digest_decided', actor, task['status'], audit)
    return {'kind': kind, 'id': payload['id'], 'decision': choice, 'status': service.detail(c, payload['id'])['status']}


@router.post('/decide')
def decide_endpoint(payload: Decision, request: Request, idempotency_key: str = Header(min_length=1, max_length=200)):
    identity = signed_in_person(request)  # Before the operation cache, so a cached result never leaks to non-humans.
    return request.app.state.service.execute(identity['user_id'], idempotency_key, 'ai_digest_decide', payload.model_dump())


class BatchItem(BaseModel):
    model_config = {'extra': 'forbid'}
    kind: Literal['signoff', 'intake_veto', 'human_close']
    id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=64, max_length=64)
    recommendation_id: str | None = Field(default=None, max_length=200)


class Batch(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    items: list[BatchItem] = Field(min_length=1, max_length=50)
    note: str = Field(min_length=1, max_length=2000)


@router.post('/decide-batch')
def decide_batch(payload: Batch, request: Request, idempotency_key: str = Header(min_length=1, max_length=150)):
    """Decision digest LOW-6: Yes to selected items. Each item is decided through the single-item path with its own
    derived idempotency key and reports its own outcome; there is no cross-item atomicity, and a retry with the same
    batch key returns each item's original result instead of deciding twice."""
    identity = signed_in_person(request)
    service, results = request.app.state.service, []
    for entry in payload.items:
        body = {'kind': entry.kind, 'id': entry.id, 'revision': entry.revision, 'decision': 'yes', 'note': payload.note,
                'recommendation_id': entry.recommendation_id}
        try:
            outcome = service.execute(identity['user_id'], f'{idempotency_key}:{entry.kind}:{entry.id}', 'ai_digest_decide', body)
            results.append({'kind': entry.kind, 'id': entry.id, 'ok': True, 'result': outcome})
        except RuleError as error:
            results.append({'kind': entry.kind, 'id': entry.id, 'ok': False, 'status': error.status, 'detail': error.message})
    return {'decided': sum(r['ok'] for r in results), 'failed': sum(not r['ok'] for r in results), 'results': results}
