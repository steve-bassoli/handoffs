"""Task-independent requests and outcomes. Nothing here performs a step.

The row retains the request and human outcome audit. Service.execute commits
that mutation and its idempotent result together; no task event is fabricated.
"""
import hashlib
import json
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services import RuleError, now
from app.storage import all_rows, one

router = APIRouter(prefix='/api/v1/manual-steps')
Text = Annotated[str, Field(strict=True, min_length=1, max_length=2000)]


def clean_text(value):
    # Match the existing Service.do_ai_profile check; never echo rejected text.
    if ('sk-' + 'proj-') in value:
        raise ValueError('Keep secrets out of manual steps')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in value):
        raise ValueError('Use plain text without control characters')
    return value


class NewStep(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    title: Text
    what: Text
    where: Text
    why: Text
    success: Text

    @field_validator('title', 'what', 'where', 'why', 'success')
    @classmethod
    def plain_text(cls, value):
        return clean_text(value)


class Outcome(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    outcome: Literal['done', 'could_not']
    note: Text
    revision: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')

    @field_validator('note')
    @classmethod
    def plain_text(cls, value):
        return clean_text(value)


def validate(model, payload):
    # Default Pydantic HTTP errors may echo rejected input. Keep this router's
    # errors generic, including for direct Service callers, without global changes.
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError:
        raise RuleError('Invalid manual-step text: use nonblank plain text of at most 2000 characters, no secrets, and a current revision for outcomes', 422) from None


def authorize(identity, actor, outcome=False):
    identity = identity or {}
    allowed = {'human'} if outcome else {'human', 'relay'}
    if (identity.get('principal') not in allowed or not identity.get('principal_id')
            or not actor or identity.get('user_id') != actor):
        raise RuleError('Manual-step outcomes require a signed-in human' if outcome
                        else 'Manual steps require a signed-in human or relay', 403)
    return identity


def revision(row):
    body = {key: value for key, value in row.items() if key != 'revision'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def public(row):
    result = dict(row)
    result['where'] = result.pop('where_text')
    return result


def get(c, identifier):
    row = one(c, 'SELECT * FROM manual_steps WHERE id=?', (identifier,))
    if row is None:
        raise RuleError('Manual step not found', 404)
    return public(row)


def pending(c):
    return [public(row) for row in all_rows(c,
            "SELECT * FROM manual_steps WHERE state='open' ORDER BY created_utc,id")]


def create(c, actor, payload, identity):
    authorize(identity, actor)
    body = validate(NewStep, payload)
    row = {'id': str(uuid4()), **body, 'state': 'open', 'created_by': actor,
           'created_utc': now(), 'outcome': None, 'note': None,
           'decided_by': None, 'decided_utc': None}
    row['revision'] = revision(row)
    columns = ('id', 'title', 'what', 'where', 'why', 'success', 'state',
               'created_by', 'created_utc', 'outcome', 'note', 'decided_by',
               'decided_utc', 'revision')
    c.exec_driver_sql(
        'INSERT INTO manual_steps '
        '(id,title,what,where_text,why,success,state,created_by,created_utc,'
        'outcome,note,decided_by,decided_utc,revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        tuple(row[key] for key in columns))
    return row


def record_outcome(c, actor, payload, identity):
    authorize(identity, actor, True)
    body = validate(Outcome, {key: value for key, value in payload.items() if key != 'id'})
    row = get(c, payload['id'])
    if row['revision'] != body['revision']:
        raise RuleError({'message': 'The item changed; review the current version',
                         'revision': row['revision']}, 409)
    if row['state'] != 'open':
        raise RuleError('Manual step already has an outcome', 409)
    current = row['revision']
    row.update(state=body['outcome'], outcome=body['outcome'], note=body['note'],
               decided_by=identity['principal_id'], decided_utc=now())
    row['revision'] = revision(row)
    changed = c.exec_driver_sql(
        'UPDATE manual_steps SET state=?,outcome=?,note=?,decided_by=?,decided_utc=?,revision=? '
        "WHERE id=? AND state='open' AND revision=?",
        (row['state'], row['outcome'], row['note'], row['decided_by'],
         row['decided_utc'], row['revision'], row['id'], current))
    if changed.rowcount != 1:
        raise RuleError('Manual step changed; refresh before recording an outcome', 409)
    return row


async def read_body(request, model):
    # Read and validate locally so rejected secret text is not included in a
    # RequestValidationError response. Never log or persist the raw body here.
    try:
        payload = await request.json()
    except (ValueError, UnicodeError):
        raise RuleError('A JSON manual-step object is required', 422) from None
    return validate(model, payload)


def reply(value):
    return JSONResponse(value, headers={'Cache-Control': 'no-store'})


@router.post('')
async def create_endpoint(request: Request,
                          idempotency_key: str = Header(min_length=1, max_length=200)):
    identity = getattr(request.state, 'identity', None) or {}
    authorize(identity, identity.get('user_id'))
    body = await read_body(request, NewStep)
    return reply(request.app.state.service.execute(identity['user_id'], idempotency_key,
                 'ai_manual_step_create', body))


@router.get('/{identifier}')
def get_endpoint(identifier: str, request: Request):
    # The unchanged application middleware resolves authentication for all API reads.
    with request.app.state.service.db.engine.connect() as c:
        return reply(get(c, identifier))


@router.post('/{identifier}/outcome')
async def outcome_endpoint(identifier: str, request: Request,
                           idempotency_key: str = Header(min_length=1, max_length=200)):
    identity = getattr(request.state, 'identity', None) or {}
    authorize(identity, identity.get('user_id'), True)
    body = await read_body(request, Outcome)
    return reply(request.app.state.service.execute(identity['user_id'], idempotency_key,
                 'ai_manual_step_outcome', {'id': identifier, **body}))
