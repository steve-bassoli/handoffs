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


def sabotage(payload):
    """Mutate only a private in-memory copy, never a real backend or caller fixture."""
    original = Comparison.model_validate(payload).model_dump()
    baseline = compare(original)
    if baseline['verdict'] != 'pass':
        raise ValueError('Start with a passing synthetic case to prove controlled defect detection')
    mutant = json.loads(json.dumps(original))
    mutant['mirrors']['rest']['behavior']['result'] = {'gremlin_injected': mutant['mirrors']['rest']['behavior']['result']}
    detected = compare(mutant)
    return {'breed': 'Saboteur', 'scope': 'SIM', 'baseline': baseline, 'mutant': detected,
            'detector_verified': detected['verdict'] == 'fail' and 'rest.result' in detected['differences'],
            'input_unchanged': digest(original) == baseline['case_sha256'], 'watson_executed': False}


def witness(payload):
    request = Comparison.model_validate(payload)
    result = compare(payload)
    record = {'breed': 'Witness', 'scope': 'SIM', 'case': request.case.model_dump(),
              'observations': request.mirrors.model_dump(), 'comparison': result,
              'preservation': {'name': request.case.name, 'reproducer': request.case.stimulus,
                               'rule': request.case.preservation_rule, 'source': request.case.source},
              'discrepancy': None if result['verdict'] == 'pass' else {
                  'question': 'Which observation violates the pinned behavior contract?',
                  'reproducer_sha256': result['case_sha256'],
                  'task': {'status': 'draft', 'creation_requires_human_approval': True}},
              'note': 'Portable synthetic observation report; not a live Watson result or task creation.'}
    return {**record, 'sha256': digest(record)}
