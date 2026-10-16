import copy

import pytest
from pydantic import ValidationError

from app.gremlins import compare


def fixture():
    behavior = {'result': {'ids': [1003, 1001]}, 'state': {}, 'effects': []}
    observation = {'scenario': 'assigned-study-title', 'identity': 'fictional-user', 'environment': 'isolated synthetic',
                   'revision': 'demo-baseline', 'behavior': behavior}
    return {'scope': 'SIM', 'case': {'name': 'Literal title match', 'source': 'synthetic fixture, not Watson',
        'preconditions': 'Fictional project and assignments', 'stimulus': {'project': 101, 'title': 'ABC'},
        'expected': copy.deepcopy(behavior), 'preservation_rule': 'Keep descending ordering'},
        'mirrors': {name: copy.deepcopy(observation) for name in ('legacy', 'rest', 'mcp')}}


def test_three_mirrors_require_independent_expectations_and_preserve_input():
    payload = fixture()
    before = copy.deepcopy(payload)
    result = compare(payload)
    assert result['verdict'] == 'pass' and result['scope'] == 'SIM' and not result['watson_executed']
    assert payload == before
    for name in ('legacy', 'rest', 'mcp'):
        payload['mirrors'][name]['behavior']['result']['ids'] = [1001, 1003]
    assert compare(payload)['differences'] == ['legacy.result', 'rest.result', 'mcp.result']


@pytest.mark.parametrize('field,value', [('result', {'wrong': True}), ('state', {'changed': True}), ('effects', [{'audit': 'unexpected'}])])
def test_compare_catches_each_behavior_dimension(field, value):
    payload = fixture()
    payload['mirrors']['mcp']['behavior'][field] = value
    assert compare(payload)['differences'] == ['mcp.' + field]


def test_context_mismatch_and_live_claims_cannot_hide_in_green_result():
    payload = fixture()
    payload['mirrors']['rest']['identity'] = 'another-user'
    assert compare(payload)['verdict'] == 'fail'
    for scope in ('ORA', 'LIVE'):
        with pytest.raises(ValidationError):
            compare({**payload, 'scope': scope})
