import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import Luna
from app.main import create_app
from conftest import post_bounty, write
from test_ai import decision, get_run, source_zip


def response(output=None, status='completed', **extra):
    return {'id': 'resp_fixture', 'status': status, 'usage': {'input_tokens': 123, 'output_tokens': 17},
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
        service = client.app.state.service
        with service.db.engine.connect() as connection:
            persisted = service.ai.record(connection, bounty)
            assert persisted['data']['request_ordinal'] == 1
            assert persisted['data']['usage']['api_calls'] == 1
            assert persisted['data']['usage']['unreported_calls'] == 1
            attempted = [event for event in service.detail(connection, bounty)['events'] if event['kind'] == 'ai_usage']
            assert len(attempted) == 1
            assert attempted[0]['data']['request_ordinal'] == 1
            assert attempted[0]['data']['usage_state'] == 'unknown'
            assert 'response_received' not in attempted[0]['data']
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
        usage_events = [event['data'] for event in detail['events'] if event['kind'] == 'ai_usage']
        assert all(event['run_id'] == run['id'] and event['request_ordinal'] == 1 for event in usage_events)
        received = [event for event in usage_events if event.get('response_received')]
        assert len(received) == (0 if kind in ('timeout', 'http') else 1)
        if received:
            assert received[0]['response_id'] == 'resp_fixture'
            assert received[0]['response_status'] == ('incomplete' if kind == 'limit' else 'completed')
            assert received[0]['usage_state'] == ('reported' if reported else 'unknown')
        else:
            assert all('response_id' not in event and 'response_status' not in event for event in usage_events)
        assert 'private provider detail' not in json.dumps(detail)
        if code:
            failure = next(event for event in detail['events'] if event['kind'] == 'ai_failed')
            assert failure['data']['code'] == code
            assert failure['data']['usage'] == run['usage']
            assert failure['data']['request_ordinal'] == 1
            if kind == 'plan':
                assert failure['data']['stage'] == 'implementation_plan'
                assert 'Provide at least one plan item' in run['error']
            if kind == 'invalid':
                assert failure['data']['stage'] == 'provider_response'
        after = client.get('/api/v1/me/stats').json()
        assert (before['available_gold'], before['reserved_gold']) == (after['available_gold'], after['reserved_gold'])
    with TestClient(create_app(db, ai_model=Luna(httpx.MockTransport(provider)))) as restarted:
        assert get_run(restarted, bounty)['usage'] == run['usage']
        assert [event['data'] for event in restarted.get(f'/api/v1/bounties/{bounty}').json()['events']
                if event['kind'] == 'ai_usage'] == usage_events


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
        events = client.get(f'/api/v1/bounties/{bounty}').json()['events']
        assert [event['data']['request_ordinal'] for event in events
                if event['kind'] == 'ai_usage' and event['data'].get('response_received')] == [1, 2]


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


def test_bad_edit_exposes_only_a_fixed_safe_rule(tmp_path):
    from app.ai import SourceEdit
    from test_ai import FakeLuna
    result = decision('deliver', instructions='Test locally')
    result.edits = [SourceEdit(path='calc.py', before='private source excerpt not present', after='replacement')]
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=FakeLuna([result]))) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        task = client.get('/api/v1/bounties/' + bounty).json()
        assert 'uniquely match the supplied source' in task['ai_run']['error']
        assert 'private source excerpt' not in json.dumps(task)
        assert next(event for event in task['events'] if event['kind'] == 'ai_failed')['data']['stage'] == 'source_edits'


def test_request_ordinals_span_tools_answers_retry_and_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-not-a-real-key')
    calls = []

    def provider(request):
        calls.append(request)
        service = client.app.state.service
        with service.db.engine.connect() as connection:
            persisted = service.ai.record(connection, bounty)
            assert persisted['data']['request_ordinal'] == len(calls)
            assert persisted['data']['usage']['api_calls'] == len(calls)
        if len(calls) == 1:
            output = [{'type': 'function_call', 'name': 'list_files', 'call_id': 'call-1', 'arguments': '{}'}]
        elif len(calls) == 3:
            output = message(decision('deliver', files=[{'path': 'calc.py', 'content': 'fixed'}],
                                      instructions='Test locally', plan=[]))
        else:
            output = message(decision('ask', questions=['Which version?']))
        return httpx.Response(200, json=response(output, id=f'resp_fixture_{len(calls)}'))

    db = tmp_path / 'test.sqlite'
    model = Luna(httpx.MockTransport(provider))
    with TestClient(create_app(db, ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        assert get_run(client, bounty)['status'] == 'needs_input'
        write(client, f'/bounties/{bounty}/ai/answers', {'answers': ['3.11']})
        task = client.get(f'/api/v1/bounties/{bounty}').json()
        failure = next(event['data'] for event in task['events'] if event['kind'] == 'ai_failed')
        assert failure['request_ordinal'] == 3 and failure['stage'] == 'implementation_plan'
        with client.app.state.service.db.write() as connection:
            connection.exec_driver_sql("UPDATE ai_runs SET status='running' WHERE bounty_id=?", (bounty,))
    with TestClient(create_app(db, ai_model=model)) as client:
        task = client.get(f'/api/v1/bounties/{bounty}').json()
        interrupted = next(event['data'] for event in task['events'] if event['kind'] == 'ai_interrupted')
        assert interrupted == {'run_id': task['ai_run']['id'], 'stage': 'restart', 'request_ordinal': 3}
        received = [event['data'] for event in task['events']
                    if event['kind'] == 'ai_usage' and event['data'].get('response_received')]
        assert received[-1]['response_id'] == 'resp_fixture_3'
        write(client, f'/bounties/{bounty}/ai/retry')
        task = client.get(f'/api/v1/bounties/{bounty}').json()
        attempts = [event['data'] for event in task['events'] if event['kind'] == 'ai_usage']
        assert [event['request_ordinal'] for event in attempts] == [1, 1, 2, 2, 3, 3, 4, 4]
        assert [event['response_id'] for event in attempts if event.get('response_received')] == [
            'resp_fixture_1', 'resp_fixture_2', 'resp_fixture_3', 'resp_fixture_4']
        assert all(event['run_id'] == task['ai_run']['id'] for event in attempts)
        assert len(calls) == task['ai_run']['usage']['api_calls'] == 4
        assert task['ai_run']['usage']['input_tokens'] == 492
        assert task['ai_run']['usage']['unreported_calls'] == 0


@pytest.mark.parametrize('metadata', [
    {'id': None}, {'id': {'private provider detail': True}},
    {'id': 'resp_private provider detail'}, {'id': 'resp_' + 'x' * 124},
    {'id': 'resp_private\nprovider'}, {'id': 'resp_é'}, {'id': 'private-provider-detail'},
    {'id': 'resp_fixture', 'status': ['private provider detail']},
    {'id': 'resp_fixture', 'status': 'private provider detail'},
    {'id': 'resp_fixture', 'status': 'x' * 1000},
])
def test_malformed_provider_metadata_is_omitted(tmp_path, monkeypatch, metadata):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-not-a-real-key')

    def provider(request):
        payload = response(message(decision('ask', questions=['Which version?'])))
        payload.update(metadata)
        return httpx.Response(200, json=payload)

    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=Luna(httpx.MockTransport(provider)))) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {})
        task = client.get(f'/api/v1/bounties/{bounty}').json()
        received = [event['data'] for event in task['events']
                    if event['kind'] == 'ai_usage' and event['data'].get('response_received')]
        assert len(received) == 1
        if metadata.get('id') == 'resp_fixture':
            assert received[0]['response_id'] == 'resp_fixture'
            assert 'response_status' not in received[0]
        else:
            assert 'response_id' not in received[0]
            assert received[0]['response_status'] == 'completed'
        assert 'private provider detail' not in json.dumps(task)
        assert task['ai_run']['usage']['api_calls'] == 1
        assert task['ai_run']['usage']['input_tokens'] == 123
