"""Prototype ledger. Existing executors are NOT protected merely by importing this."""
import hashlib
import json
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.prototype import auto_signoff_active
from app.services import RuleError

Action = Literal['automation_mode', 'spend_ceiling', 'price_checkpoint', 'rule_texts', 'publish']
ACTIONS = {'automation_mode', 'spend_ceiling', 'price_checkpoint', 'rule_texts', 'publish'}
router = APIRouter(prefix='/api/v1/signoffs')


class SignoffRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    action: Action
    payload: dict
    summary: str = Field(min_length=1, max_length=2000)


class SignoffDecision(BaseModel):
    model_config = {'extra': 'forbid'}
    approved: bool = Field(strict=True)
    note: str = Field(min_length=1, max_length=2000)


def canonical_payload(payload):
    # Version-1 binding is Python canonical JSON, not a claim of RFC 8785.
    # Executors must reconstruct their complete effective payload themselves.
    if not isinstance(payload, dict):
        raise RuleError('Payload must be an object', 422)
    def validate(value):
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError('Non-string key')
            for item in value.values():
                validate(item)
        elif isinstance(value, list):
            for item in value:
                validate(item)
        elif value is not None and type(value) not in (str, bool, int, float):
            raise ValueError('Non-JSON value')
    try:
        validate(payload)
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
        if len(encoded.encode('utf-8')) > 65536:
            raise ValueError('Payload too large')
    except (TypeError, ValueError, RecursionError):
        raise RuleError('Use a finite JSON payload of at most 65536 encoded bytes', 422) from None
    return encoded, hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def identity(request):
    value = getattr(request.state, 'identity', None)
    if not value or value.get('principal') not in {'human', 'relay', 'codex', 'agent'}:
        raise RuleError('Authenticated principal required; demo headers are insufficient', 401)
    return value


def response(value):
    return JSONResponse(value, headers={'Cache-Control': 'no-store'})


@router.post('')
def request_signoff(payload: SignoffRequest, request: Request):
    who = identity(request)
    encoded, digest = canonical_payload(payload.payload)
    record_id = str(uuid4())
    with request.app.state.service.db.write() as c:
        c.exec_driver_sql('INSERT INTO signoffs(id,action,payload_sha256,payload_json,summary,requested_by,requested_principal,requested_principal_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (record_id, payload.action, digest, encoded, payload.summary, who['user_id'], who['principal'], who['principal_id'], int(time.time())))
    return response({'id': record_id, 'action': payload.action, 'payload_sha256': digest})


@router.get('')
def pending_signoffs(request: Request):
    identity(request)
    with request.app.state.service.db.engine.connect() as c:
        records = [dict(row) for row in c.exec_driver_sql('SELECT * FROM signoffs WHERE decision IS NULL ORDER BY created_at,id LIMIT 100').mappings()]
    return response(records)


@router.post('/{signoff_id}/decision')
def decide_signoff(signoff_id: str, payload: SignoffDecision, request: Request):
    who = identity(request)
    # Prototype-only: app/prototype.py hard-cuts this bypass; the decision records which path was used.
    mode = 'human' if who['principal'] == 'human' else 'prototype-auto' if auto_signoff_active() else None
    if mode is None:
        raise RuleError('Human password-login session required', 403)
    decision = 'approved' if payload.approved else 'rejected'
    with request.app.state.service.db.write() as c:
        result = c.exec_driver_sql('UPDATE signoffs SET decided_by=?,decided_principal=?,decided_principal_id=?,decision=?,decision_note=?,decision_mode=?,decided_at=? WHERE id=? AND decision IS NULL AND used_at IS NULL',
            (who['user_id'], who['principal'], who['principal_id'], decision, payload.note, mode, int(time.time()), signoff_id))
        if result.rowcount != 1:
            raise RuleError('Sign-off missing or already decided', 409)
    return response({'id': signoff_id, 'decision': decision, 'decision_mode': mode})


def require_signoff(c, action, payload, *, signoff_id):
    """Consume using an existing write transaction, never a separate commit.

    The caller must mutate protected state in this SAME transaction. Files,
    external publication and separate database stores need another protocol.
    No fallback search: CLI executors must name the exact reviewed record.
    """
    if action not in ACTIONS:
        raise RuleError('Unknown protected action', 422)
    _, digest = canonical_payload(payload)
    modes = ('human', 'prototype-auto') if auto_signoff_active() else ('human', 'human')
    result = c.exec_driver_sql("UPDATE signoffs SET used_at=? WHERE id=? AND action=? AND payload_sha256=? AND decision='approved' AND decision_mode IN (?,?) AND used_at IS NULL",
        (int(time.time()), signoff_id, action, digest, *modes))
    if result.rowcount != 1:
        raise RuleError('Approved unused human sign-off required for this exact action and payload', 403)
    return signoff_id
