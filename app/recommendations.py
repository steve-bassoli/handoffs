"""Persist supplied advice only: no generation, approval or executor calls.

Callers must derive the effective item revision from authoritative item content.
Requester context is separate private metadata, never recommendation evidence.
Use work-only text: this ledger is not a store for personal health information.
"""
import json
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.services import RuleError
from app.signoffs import canonical_payload, identity, response

Kind = Literal['signoff', 'intake_veto', 'human_close', 'policy_decision']
Disposition = Literal['yes', 'no', 'change']
router = APIRouter(prefix='/api/v1/recommendations')


class RecommendationRequest(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    item_kind: Kind
    item_id: str = Field(min_length=1, max_length=200)
    item_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    disposition: Disposition
    rationale: str = Field(min_length=1, max_length=4000)
    provenance: dict
    requester_context: str = Field(default='', max_length=2000)


def writer(who):
    # Credentials, not body fields or X-Principal, establish authorship.
    if who.get('principal') not in {'human', 'relay', 'agent', 'codex'}:
        raise RuleError('Authenticated recommendation author required', 403)
    if not all(who.get(key) for key in ('user_id', 'principal_id')):
        raise RuleError('Complete authenticated identity required', 401)


def public_snapshot(row):
    # Context and raw provenance may contain private requester information.
    # Neither is exported by the digest read endpoint.
    return {key: row[key] for key in (
        'id', 'item_kind', 'item_id', 'item_revision', 'disposition',
        'rationale', 'created_by', 'created_principal', 'created_at',
        'superseded_by')}


class Recommendations:
    def __init__(self, db, who):
        writer(who)
        self.db = db
        self.who = dict(who)

    def record(self, item_kind, item_id, item_revision, disposition, rationale,
               provenance, *, requester_context=''):
        payload = RecommendationRequest(
            item_kind=item_kind, item_id=item_id, item_revision=item_revision,
            disposition=disposition, rationale=rationale,
            provenance=provenance, requester_context=requester_context)
        # Authoritative attribution lives outside caller-supplied evidence.
        encoded, _ = canonical_payload({
            'schema_version': 1,
            'author': {'principal': self.who['principal'],
                       'principal_id': self.who['principal_id'],
                       'user_id': self.who['user_id']},
            'evidence': payload.provenance})
        rid = str(uuid4())
        now = int(time.time())
        try:
            with self.db.write() as c:
                previous = c.exec_driver_sql(
                    'SELECT id FROM recommendations WHERE item_kind=? AND item_id=? AND superseded_by IS NULL',
                    (payload.item_kind, payload.item_id)).scalar()
                # Deferred FK permits retire-before-insert while the partial
                # unique index prevents concurrent duplicate current records.
                # Instead use a temporary self-contained successor insertion:
                # old -> new is installed only after old leaves the unique set.
                if previous:
                    c.exec_driver_sql('DELETE FROM recommendations WHERE 0')
                    # SQLite checks this FK at transaction commit below.
                    c.exec_driver_sql('PRAGMA defer_foreign_keys = ON')
                    c.exec_driver_sql(
                        'UPDATE recommendations SET superseded_by=? WHERE id=? AND superseded_by IS NULL',
                        (rid, previous))
                c.exec_driver_sql(
                    'INSERT INTO recommendations(id,item_kind,item_id,item_revision,disposition,rationale,provenance_json,requester_context,created_by,created_principal,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (rid, payload.item_kind, payload.item_id, payload.item_revision,
                     payload.disposition, payload.rationale, encoded,
                     payload.requester_context, self.who['user_id'],
                     self.who['principal'], now))
        except IntegrityError:
            raise RuleError('Concurrent recommendation change; refresh before recording again', 409) from None
        return {'status': 'available', 'id': rid, 'item_revision': payload.item_revision}

    def current(self, item_kind, item_id, item_revision):
        # Validate read inputs through the same contract without fabricating advice.
        RecommendationRequest(item_kind=item_kind, item_id=item_id,
            item_revision=item_revision, disposition='change', rationale='validation', provenance={})
        with self.db.engine.connect() as c:
            row = c.exec_driver_sql(
                'SELECT * FROM recommendations WHERE item_kind=? AND item_id=? AND item_revision=? AND superseded_by IS NULL',
                (item_kind, item_id, item_revision)).mappings().first()
        if row is None:
            return {'status': 'unavailable'}
        return {'status': 'available', **public_snapshot(row)}


@router.post('')
def record_recommendation(payload: RecommendationRequest, request: Request):
    who = identity(request)
    return response(Recommendations(request.app.state.service.db, who).record(**payload.model_dump()))


@router.get('/{item_kind}/{item_id}')
def current_recommendation(item_kind: Kind, item_id: str, request: Request,
                           revision: str = Query(pattern=r'^[0-9a-f]{64}$')):
    who = identity(request)
    if not item_id or len(item_id) > 200:
        raise RuleError('Invalid item ID', 422)
    return response(Recommendations(request.app.state.service.db, who).current(item_kind, item_id, revision))
