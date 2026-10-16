"""Small source-backed context, lifecycle projection and dependency contracts."""
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Fact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    statement: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=2000)


class Knowledge(BaseModel):
    model_config = ConfigDict(extra='forbid')
    known: list[Fact] = Field(default_factory=list, max_length=30)
    assumed: list[str] = Field(default_factory=list, max_length=30)
    unknown: list[str] = Field(default_factory=list, max_length=30)


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    validation_scope: Literal['SIM', 'ORA', 'LIVE'] = 'SIM'
    migration_stage: Literal['WRAP', 'REPLACE', 'RETIRE'] = 'WRAP'
    baseline_revision: str = Field(default='', max_length=200)
    candidate_revision: str = Field(default='', max_length=200)
    environment: str = Field(default='', max_length=500)
    knowledge: Knowledge = Field(default_factory=Knowledge)


def phase(status):
    if status in ('completed', 'settled', 'cancelled', 'superseded'):
        return 'Closed'
    return 'Posted' if status in ('open', 'pending') else 'Claimed'


def disposition(status):
    return {'completed': 'completed', 'settled': 'completed', 'cancelled': 'cancelled',
            'superseded': 'superseded'}.get(status)


def profile(events):
    return next((event['data']['profile'] for event in reversed(events) if 'profile' in event['data']), None)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


ROLES = {
    'Mapper': 'Discover source-backed behavior, assumptions, unknowns and a bounded decomposition.',
    'Maker': 'Implement only the approved LOW criteria; no independent acceptance claim.',
    'Breaker': 'Challenge the supplied proof against the criteria; fail or abstain when insufficient.',
}
