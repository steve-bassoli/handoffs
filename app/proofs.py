"""One primary immutable proof, bound to intent, change and observation context."""
import base64
import json
import re
from typing import Literal

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
