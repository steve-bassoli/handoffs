import hashlib
import json

import httpx
import pytest

from app import intake_screen as module


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    policy = tmp_path / 'intake-policy.md'
    policy.write_bytes(b'Fixed test policy.\n')
    monkeypatch.setattr(module, 'POLICY_PATH', policy)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only-not-a-real-key')
    monkeypatch.setenv('HANDOFFS_INTAKE_MODEL', 'test-model')
    return policy


def reviewer(monkeypatch, result):
    calls, observations, settlements = [], [], []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=result)

    transport = httpx.MockTransport(handler)

    class Permit:
        def post(self, client, url, **kwargs):
            assert observations[-1]['stage'] == 'request_started'
            return client.post(url, **kwargs)

        def settle(self, usage=None):
            settlements.append(usage)

    def reserve(model, maximum, supplied_transport):
        assert model == 'test-model'
        assert maximum == module.MAX_OUTPUT
        assert supplied_transport is transport
        return Permit()

    monkeypatch.setattr(module, 'reserve', reserve)
    screen = module.IntakeScreen(transport, lambda **value: observations.append(value))
    return screen, calls, observations, settlements


@pytest.mark.parametrize('verdict', ['pass', 'veto'])
def test_decision_and_verbatim_policy(monkeypatch, isolated, verdict):
    result = {'status': 'completed', 'usage': {'input_tokens': 12, 'output_tokens': 5},
              'output': [{'type': 'message', 'content': [{'type': 'output_text',
                         'text': json.dumps({'verdict': verdict, 'reason': 'Policy decision.'})}]}]}
    screen, calls, observations, settlements = reviewer(monkeypatch, result)
    answer = screen.screen('Untrusted task text')
    assert answer == {'verdict': verdict, 'reason': 'Policy decision.',
                      'model': 'test-model',
                      'policy_sha256': hashlib.sha256(isolated.read_bytes()).hexdigest()}
    assert calls[0]['instructions'].endswith(isolated.read_bytes().decode('utf-8'))
    assert calls[0]['store'] is False
    assert len(calls) == 1
    assert settlements == [result['usage']]
    assert observations[-1]['usage_state'] == 'reported'


@pytest.mark.parametrize('result', [
    {'status': 'incomplete'},
    {'status': 'completed', 'output': []},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': '{"verdict":"pass","reason":""}'}]}]},
])
def test_invalid_response_unavailable(monkeypatch, isolated, result):
    screen, calls, observations, settlements = reviewer(monkeypatch, result)
    assert screen.screen('task')['verdict'] == 'unavailable'
    assert len(calls) == 1
    assert observations[-1]['usage_state'] == 'unknown'


def test_missing_key_never_reserves(monkeypatch, isolated):
    monkeypatch.delenv('OPENAI_API_KEY')
    def forbidden(*args):
        pytest.fail('must not reserve without a key')
    monkeypatch.setattr(module, 'reserve', forbidden)
    assert module.IntakeScreen().screen('task')['verdict'] == 'unavailable'


def test_missing_policy_unavailable(monkeypatch, isolated):
    isolated.unlink()
    def forbidden(*args):
        pytest.fail('must not reserve without policy')
    monkeypatch.setattr(module, 'reserve', forbidden)
    answer = module.IntakeScreen().screen('task')
    assert answer['verdict'] == 'unavailable'
    assert answer['policy_sha256'] is None


def test_budget_failure_no_dispatch(monkeypatch, isolated):
    def refuse(*args):
        raise RuntimeError('budget unavailable')
    monkeypatch.setattr(module, 'reserve', refuse)
    assert module.IntakeScreen().screen('task')['verdict'] == 'unavailable'


def test_canonical_text_binding():
    task = {'title': 'Title', 'goal': 'Goal', 'criteria': ['One'], 'ignored': 1}
    same = {'criteria': ['One'], 'goal': 'Goal', 'title': 'Title'}
    assert module.canonical_text(task) == module.canonical_text(same)
    before = module.text_sha256(module.canonical_text(task))
    task['criteria'].append('Two')
    assert module.text_sha256(module.canonical_text(task)) != before
