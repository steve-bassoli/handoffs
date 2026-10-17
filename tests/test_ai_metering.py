import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import Luna
from app.main import create_app
from conftest import post_bounty, write
from test_ai import decision, get_run, source_zip


def response(output=None, status='completed', **extra):
    return {'status': status, 'usage': {'input_tokens': 123, 'output_tokens': 17},
            'output': output or [], **extra}


def message(result):
    return [{'type': 'message', 'content': [{'type': 'output_text', 'text': result.model_dump_json()}]}]


@pytest.mark.parametrize('kind,code,reported', [
    ('limit', 'output_limit', True), ('invalid', 'invalid_outcome', True),
    ('plan', 'invalid_outcome', True), ('timeout', 'transport_error', False),
    ('http', 'http_error', False), ('missing_usage', None, False), ('ok', None, True),
])
def test_provider_attempts_and_usage_survive_failures(tmp_path, monkeypatch, kind, code, reported):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-not-a-real-key')

    def provider(request):
        if kind == 'timeout':
            raise httpx.ReadTimeout('private provider detail', request=request)
        if kind == 'http':
            return httpx.Response(429, json={'error': 'private provider detail'})
        if kind == 'limit':
            return httpx.Response(200, json=response(status='incomplete', incomplete_details={'reason': 'max_output_tokens'}))
        if kind == 'invalid':
            return httpx.Response(200, json=response([{'type': 'message', 'content': [{'type': 'output_text', 'text': 'private provider detail'}]}]))
        result = decision('ask', questions=['Which version?'])
        if kind == 'plan':
            result = decision('deliver', files=[{'path': 'calc.py', 'content': 'fixed'}], instructions='Test locally', plan=[])
        payload = response(message(result))
        if kind == 'missing_usage':
            payload.pop('usage')
        return httpx.Response(200, json=payload)

    db = tmp_path / 'test.sqlite'
    with TestClient(create_app(db, ai_model=Luna(httpx.MockTransport(provider)))) as client:
        bounty = post_bounty(client).json()['id']
        before = client.get('/api/v1/me/stats').json()
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        run = get_run(client, bounty)
        assert run['status'] == ('failed' if code else 'needs_input')
        assert run['usage']['api_calls'] == 1
        assert run['usage']['input_tokens'] == (123 if reported else 0)
        assert run['usage']['output_tokens'] == (17 if reported else 0)
        assert run['usage']['unreported_calls'] == (0 if reported else 1)
        detail = client.get(f'/api/v1/bounties/{bounty}').json()
        assert 'private provider detail' not in json.dumps(detail)
        if code:
            failure = next(event for event in detail['events'] if event['kind'] == 'ai_failed')
            assert failure['data']['code'] == code
            assert failure['data']['usage'] == run['usage']
        after = client.get('/api/v1/me/stats').json()
        assert (before['available_gold'], before['reserved_gold']) == (after['available_gold'], after['reserved_gold'])
    with TestClient(create_app(db, ai_model=Luna(httpx.MockTransport(provider)))) as restarted:
        assert get_run(restarted, bounty)['usage'] == run['usage']


def test_tool_rounds_are_metered_before_final_validation(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-not-a-real-key')
    calls = []

    def provider(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=response([{'type': 'function_call', 'name': 'read_file',
                'call_id': 'source-1', 'arguments': json.dumps({'path': 'calc.py'})}]))
        assert 'return a - b' in request.content.decode()
        return httpx.Response(200, json=response(status='incomplete', incomplete_details={'reason': 'max_output_tokens'}))

    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=Luna(httpx.MockTransport(provider)))) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        run = get_run(client, bounty)
        assert run['status'] == 'failed'
        assert run['usage']['api_calls'] == 2 and run['usage']['input_tokens'] == 246
        assert run['usage']['output_tokens'] == 34 and run['usage']['unreported_calls'] == 0
        assert len(calls) == 2  # no automatic paid retry


def test_tool_limit_stops_without_a_thirteenth_call(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-not-a-real-key')
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(200, json=response([{'type': 'function_call', 'name': 'list_files',
            'call_id': f'call-{len(calls)}', 'arguments': '{}'}]))

    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=Luna(httpx.MockTransport(provider)))) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {})
        run = get_run(client, bounty)
        assert run['status'] == 'failed' and 'source-reading budget' in run['error']
        assert len(calls) == run['usage']['api_calls'] == 12
        assert run['usage']['input_tokens'] == 1476
