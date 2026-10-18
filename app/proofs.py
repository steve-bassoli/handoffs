"""One primary immutable proof, bound to intent, change and observation context."""
import base64
import hashlib
import json
import re
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.workflow import digest


class ProofUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=1, max_length=160)
    media_type: Literal['text/plain', 'application/json', 'image/png', 'image/jpeg', 'video/mp4']
    content_base64: str = Field(min_length=1, max_length=12000000)
    description: str = Field(min_length=1, max_length=2000)


class CriterionVerdict(BaseModel):
    model_config = ConfigDict(extra='forbid')
    index: int
    verdict: Literal['pass', 'fail', 'inconclusive']
    reason: str = Field(min_length=1, max_length=2000)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verdict: Literal['pass', 'fail', 'inconclusive']
    reason: str = Field(min_length=1, max_length=4000)
    criteria: list[CriterionVerdict]


def decode_upload(value):
    proof = ProofUpload.model_validate(value)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_. -]*', proof.filename) or '..' in proof.filename:
        raise ValueError('Use a plain artifact filename, not a path')
    raw = base64.b64decode(proof.content_base64, validate=True)
    if not raw or len(raw) > 8000000:
        raise ValueError('Use one proof artifact between 1 byte and 8 MB')
    if proof.media_type in ('text/plain', 'application/json'):
        text = raw.decode('utf-8-sig')
        if len(raw) > 200000 or 'sk-proj-' in text or '-----BEGIN PRIVATE KEY-----' in text:
            raise ValueError('Use focused proof text under 200 KB without credentials')
        if proof.media_type == 'application/json':
            json.loads(text)
    elif proof.media_type == 'image/png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Expected PNG bytes')
    elif proof.media_type == 'image/jpeg' and not (raw.startswith(b'\xff\xd8') and raw.endswith(b'\xff\xd9')):
        raise ValueError('Expected JPEG bytes')
    elif proof.media_type == 'video/mp4' and raw[4:8] != b'ftyp':
        raise ValueError('Expected MP4 bytes')
    return proof, raw


def binding(task, requirements=()):
    return digest({'intent': {key: task[key] for key in ('id', 'goal', 'criteria')},
        'change': {'repository': task['repository'], 'profile': task.get('profile'),
                   'source': next((event['data'].get('sha256', event['data'].get('source_sha256'))
                       for event in reversed(task['events']) if event['kind'] in ('ai_source', 'ai_answers')), None)},
        'observation': {'requirements': list(requirements)}})


def validate_review(result, criteria_count):
    review = ReviewResult.model_validate(result)
    indices = [item.index for item in review.criteria]
    if len(indices) != criteria_count or set(indices) != set(range(criteria_count)):
        raise ValueError('Review must address every acceptance criterion once')
    if review.verdict == 'pass' and any(item.verdict != 'pass' for item in review.criteria):
        raise ValueError('A failed or inconclusive criterion cannot produce a passing proof')
    return review.model_dump()


class Proofs:
    def __init__(self, service, reviewer):
        self.service, self.reviewer = service, reviewer

    def requirements(self, c, task):
        from app.storage import all_rows
        children = all_rows(c, 'SELECT id FROM tasks WHERE parent_id=? ORDER BY id', (task['id'],))
        ids = sorted(set(task['depends_on'] + [child['id'] for child in children]))
        receipts = []
        for identifier in ids:
            events = all_rows(c, 'SELECT kind,state,data FROM events WHERE task_id=? ORDER BY seq', (identifier,))
            acceptance = next((json.loads(event['data']) for event in reversed(events)
                               if event['kind'] in ('proof_completed', 'locally_verified', 'paid')), {})
            receipts.append({'id': identifier, 'status': events[-1]['state'],
                'proof_id': acceptance.get('proof_id'), 'binding': acceptance.get('proof_binding')})
        return children, receipts

    @staticmethod
    def review_usage(task, review):
        observations = {event['data']['stage']: event['data'] for event in task['events']
                        if event['kind'] == 'proof_review_usage' and event['data']['review_id'] == review['review_id']}
        attempt = observations.get('request_started')
        received = observations.get('response_received', {})
        no_request = observations.get('no_request')
        state = received.get('usage_state', 'unknown') if attempt else 'no_request' if no_request else 'unobserved'
        usage = {'api_calls': 1 if attempt else 0 if no_request else None,
                 'input_tokens': received.get('input_tokens') if state == 'reported' else 0 if no_request else None,
                 'output_tokens': received.get('output_tokens') if state == 'reported' else 0 if no_request else None,
                 'usage_state': state, 'unreported_calls': int(state == 'unknown') if attempt else 0 if no_request else None,
                 'elapsed_ms': review.get('elapsed_ms')}
        observation = received or attempt or no_request or {}
        usage.update({key: observation[key] for key in ('model', 'response_id', 'response_status', 'reason') if key in observation})
        return usage

    def project(self, c, task):
        children, requirements = self.requirements(c, task)
        records = [event['data'] for event in task['events'] if event['kind'] == 'proof_attached']
        proof = records[-1] if records else None
        public = None
        if proof:
            review = next((event['data'] for event in reversed(task['events'])
                           if event['kind'] in ('proof_review_queued', 'proof_review_started', 'proof_reviewed')
                           and event['data']['proof_id'] == proof['proof_id']), None)
            if review:
                review = {**review, 'usage': self.review_usage(task, review)}
            human = next((event['data'] for event in reversed(task['events']) if event['kind'] == 'proof_human_reviewed'
                          and event['data']['proof_id'] == proof['proof_id']), None)
            fresh = proof['binding'] == binding(task, requirements)
            ready = fresh and review and review.get('verdict') == 'pass' and review['binding'] == proof['binding']
            human_current = bool(fresh and human and human['accepted'] and human['binding'] == proof['binding']
                and human['review_id'] == (review['review_id'] if review else None))
            human_only = bool(task['complexity'] == 'LOW' and human_current and human.get('review_basis') == 'human-only')
            accepted = bool(human_only or (ready and (task['complexity'] != 'LOW' or human_current)))
            public = {key: value for key, value in proof.items() if key != 'content_base64'} | {
                'fresh': fresh, 'review': review, 'human': human, 'accepted': accepted,
                'verification_method': ('human-only' if human_only else 'ai-reviewed') if accepted else None,
                'download_url': f"/api/v1/tasks/{task['id']}/proofs/{proof['proof_id']}"}
        task['proof'] = public
        task['proof_history'] = [{key: record[key] for key in ('proof_id', 'filename', 'sha256', 'binding')} for record in records]
        task['requirements'] = requirements
        task['required_children'] = [child['id'] for child in children]

    def owner(self, c, actor, identifier):
        from app.services import RuleError
        task = self.service.detail(c, identifier)
        if actor not in (task['creator'], task['claimant']):
            raise RuleError('Only requester or current worker can submit proof or request review', 403)
        if task['phase'] != 'Claimed' or not task['claimant']:
            raise RuleError('Proof actions require a claimed, unresolved task')
        return task

    @staticmethod
    def require_dependencies(task):
        from app.services import RuleError
        if task['complexity'] != 'LOW' and len(task['required_children']) < 2:
            raise RuleError('A composite needs its approved decomposition before integrated acceptance')
        if any(record['status'] not in ('completed', 'settled') or not record['proof_id'] or not record['binding']
               for record in task['requirements']):
            raise RuleError('Required child work and shared prerequisites need verified completion, not cancellation or reported progress')

    def attach(self, c, actor, payload):
        from app.services import RuleError
        task = self.owner(c, actor, payload['id'])
        self.require_dependencies(task)
        profile = task['profile']
        if not task['criteria'] or not profile or any(not profile.get(key, '').strip()
                for key in ('baseline_revision', 'candidate_revision', 'environment')):
            raise RuleError('Record criteria, baseline/candidate revisions and verification environment before proof', 422)
        try:
            value, raw = decode_upload({key: value for key, value in payload.items() if key != 'id'})
        except (ValueError, UnicodeError):
            raise RuleError('Invalid proof: use one supported, focused artifact without paths or secrets', 422) from None
        data = value.model_dump() | {'proof_id': str(uuid4()), 'binding': binding(task, task['requirements']),
                                    'sha256': hashlib.sha256(raw).hexdigest(), 'role': 'Witness'}
        self.service.event(c, task['id'], 'proof_attached', actor, task['status'], data)
        return self.service.detail(c, task['id'])

    def queue(self, c, actor, identifier):
        from app.services import RuleError
        task = self.owner(c, actor, identifier)
        proof = task['proof']
        if not proof or not proof['fresh']:
            raise RuleError('Attach proof for the current intent, revision, environment and prerequisites')
        if proof['review'] and proof['review'].get('verdict') in ('queued', 'running'):
            raise RuleError('This proof already has an active review')
        self.service.event(c, identifier, 'proof_review_queued', actor, task['status'], {
            'review_id': str(uuid4()), 'proof_id': proof['proof_id'], 'binding': proof['binding'],
            'verdict': 'queued', 'role': 'Breaker'})
        return self.service.detail(c, identifier)

    def run(self, identifier, review_id):
        from app.proof_reviewer import ProofReviewer
        with self.service.db.write() as c:
            task = self.service.detail(c, identifier)
            queued = next((event for event in task['events'] if event['kind'] == 'proof_review_queued'
                           and event['data']['review_id'] == review_id), None)
            if not queued or any(event['kind'] in ('proof_review_started', 'proof_reviewed') and event['data'].get('review_id') == review_id for event in task['events']):
                return
            meta = queued['data']
            proof = next(event['data'] for event in task['events'] if event['kind'] == 'proof_attached'
                         and event['data']['proof_id'] == meta['proof_id'])
            self.service.event(c, identifier, 'proof_review_started', queued['actor'], task['status'], {**meta, 'verdict': 'running'})
        started = time.monotonic()

        def record_usage(*, stage, **observation):
            if stage not in ('request_started', 'response_received', 'no_request'):
                raise ValueError('Unknown proof review usage stage')
            data = {key: observation[key] for key in ('model', 'usage_state', 'input_tokens', 'output_tokens',
                    'response_id', 'response_status', 'reason') if key in observation}
            if stage in ('request_started', 'no_request'):
                data.update(api_calls=int(stage == 'request_started'),
                            usage_state='unknown' if stage == 'request_started' else 'no_request')
            with self.service.db.write() as c:
                current = self.service.detail(c, identifier)
                if any(event['kind'] == 'proof_review_usage' and event['data']['review_id'] == review_id
                       and event['data']['stage'] == stage for event in current['events']):
                    return
                self.service.event(c, identifier, 'proof_review_usage', queued['actor'], current['status'], {
                    **{key: meta[key] for key in ('review_id', 'proof_id', 'binding')},
                    'request_ordinal': 1, 'stage': stage, **data})

        try:
            raw = self.reviewer.review(task, {**proof, '_record_usage': record_usage})
            result = validate_review({key: raw[key] for key in ('verdict', 'reason', 'criteria')}, len(task['criteria']))
            result['reviewer'] = raw.get('reviewer', 'configured-reviewer')
        except Exception:
            result = ProofReviewer.inconclusive(task, 'Proof reviewer failed or returned an invalid verdict. No acceptance was recorded.')
        with self.service.db.write() as c:
            current = self.service.detail(c, identifier)
            if not current['proof'] or current['proof']['proof_id'] != proof['proof_id'] or not current['proof']['fresh']:
                result = ProofReviewer.inconclusive(task, 'The proof or its bound context changed during review.')
            self.service.event(c, identifier, 'proof_reviewed', queued['actor'], current['status'],
                               {**meta, **result, 'elapsed_ms': round((time.monotonic() - started) * 1000)})

    def recover(self):
        from app.storage import all_rows
        from app.proof_reviewer import ProofReviewer
        with self.service.db.write() as c:
            for record in all_rows(c, "SELECT DISTINCT task_id FROM events WHERE kind='proof_review_queued'"):
                task = self.service.detail(c, record['task_id'])
                finished = {event['data']['review_id'] for event in task['events'] if event['kind'] == 'proof_reviewed'}
                for event in task['events']:
                    if event['kind'] == 'proof_review_queued' and event['data']['review_id'] not in finished:
                        result = ProofReviewer.inconclusive(task, 'The server restarted during proof review. Request a new review explicitly.')
                        self.service.event(c, task['id'], 'proof_reviewed', event['actor'], task['status'], {**event['data'], **result})

    def human(self, c, actor, payload):
        from app.services import RuleError, event_via, event_intent
        task = self.owner(c, actor, payload['id'])
        proof = task['proof']
        if task['complexity'] != 'LOW' or not proof or not proof['fresh']:
            raise RuleError('Human verification requires a LOW with current proof')
        if event_intent.get() == 'autonomous' or (event_via.get() is not None and event_intent.get() != 'user-directed'):
            raise RuleError('Human verification requires an explicit user-directed action', 403)
        review = proof['review']
        basis = payload.get('review_basis', 'ai-reviewed')
        if basis == 'human-only':
            if review and (review['verdict'] != 'inconclusive' or
                    any(item['verdict'] == 'fail' for item in review.get('criteria', []))):
                raise RuleError('Human-only verification cannot replace a running, passing or failed AI review')
        elif not review or review['verdict'] != 'pass':
            raise RuleError('AI-reviewed verification requires a current passing AI proof review')
        self.service.event(c, task['id'], 'proof_human_reviewed', actor, task['status'], {
            'proof_id': proof['proof_id'], 'binding': proof['binding'], 'review_id': review['review_id'] if review else None,
            'review_basis': basis, 'accepted': payload['accepted'], 'note': payload['note']})
        return self.service.detail(c, task['id'])

    def require(self, c, task):
        from app.services import RuleError
        self.require_dependencies(task)
        if not task['proof'] or not task['proof']['accepted']:
            raise RuleError('Completion requires current accepted proof and explicit human LOW verification')
        return {'proof_id': task['proof']['proof_id'], 'proof_binding': task['proof']['binding'],
                'verification_method': task['proof']['verification_method']}

    def complete(self, c, actor, payload):
        from app.services import now
        task = self.owner(c, actor, payload['id'])
        receipt = self.require(c, task)
        state = 'completed'
        if task['funded']:
            self.service.transfer(c, 'escrow:' + task['id'], 'wallet:' + task['claimant'], task['gold'], 'task_paid', task['id'])
            state = 'settled'
        self.service.event(c, task['id'], 'proof_completed', actor, state,
                           {**receipt, 'note': payload['note'], 'worker': task['claimant']})
        c.exec_driver_sql("UPDATE ai_runs SET status='completed',updated_at=? WHERE task_id=? AND status='ready'", (now(), task['id']))
        return self.service.detail(c, task['id'])
