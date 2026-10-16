"""Gremlins: deterministic offline comparison, never a live Watson runner."""
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.workflow import digest


class Behavior(BaseModel):
    model_config = ConfigDict(extra='forbid')
    result: Any
    state: dict[str, Any]
    effects: list[dict[str, Any]]


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=2000)
    preconditions: str = Field(min_length=1, max_length=4000)
    stimulus: dict[str, Any]
    expected: Behavior
    preservation_rule: str = Field(min_length=1, max_length=4000)


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    behavior: Behavior


class Mirrors(BaseModel):
    model_config = ConfigDict(extra='forbid')
    legacy: Observation
    rest: Observation
    mcp: Observation


class Comparison(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scope: Literal['SIM'] = 'SIM'
    case: Case
    mirrors: Mirrors


def compare(payload):
    request = Comparison.model_validate(payload)
    document = request.model_dump()
    if len(json.dumps(document, allow_nan=False).encode()) > 200000:
        raise ValueError('Use a focused synthetic case under 200 KB; never submit secrets or live records')
    expected = request.case.expected.model_dump()
    differences = []
    origin = request.mirrors.legacy
    for name in ('legacy', 'rest', 'mcp'):
        observation = getattr(request.mirrors, name)
        for field in ('scenario', 'identity', 'environment'):
            if getattr(observation, field) != getattr(origin, field):
                differences.append(name + '.context.' + field)
        actual = observation.behavior.model_dump()
        for field in ('result', 'state', 'effects'):
            if digest(actual[field]) != digest(expected[field]):
                differences.append(name + '.' + field)
    return {'name': request.case.name, 'verdict': 'fail' if differences else 'pass',
            'scope': 'SIM', 'mode': 'supplied-observation-comparison', 'case_sha256': digest(document),
            'differences': differences, 'watson_executed': False,
            'note': 'Only the comparator ran. Supplied observations and expectations are claims, not independent Watson execution.'}
