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


def dependencies(events):
    return next((event['data']['depends_on'] for event in reversed(events) if event['kind'] == 'dependencies_set'), [])


def constellation(nodes):
    """Edges point from an outcome to required child work or a shared prerequisite."""
    edges = []
    for node in nodes:
        if node.get('parent_id'):
            edges.append({'from': node['parent_id'], 'to': node['id'], 'kind': 'child'})
        edges.extend({'from': node['id'], 'to': target, 'kind': 'prerequisite'} for target in node.get('depends_on', []))
    return {'nodes': nodes, 'edges': edges}


def validate_dependencies(nodes, source, targets):
    ids = {node['id'] for node in nodes}
    if source not in ids or len(targets) != len(set(targets)) or any(target not in ids for target in targets):
        raise ValueError('Use distinct existing prerequisite task IDs')
    updated = [{**node, 'depends_on': targets if node['id'] == source else node.get('depends_on', [])} for node in nodes]
    graph = {identifier: [] for identifier in ids}
    for edge in constellation(updated)['edges']:
        graph[edge['from']].append(edge['to'])
    active, visited = set(), set()
    def visit(identifier):
        if identifier in active:
            raise ValueError('A prerequisite cannot create a cycle through task ancestry or dependencies')
        if identifier in visited:
            return
        active.add(identifier)
        for target in graph[identifier]:
            visit(target)
        active.remove(identifier)
        visited.add(identifier)
    for identifier in ids:
        visit(identifier)
    return targets
