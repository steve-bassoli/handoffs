"""Offline conduit protocol checks: fixtures never contact a provider."""
import json

import httpx
import pytest

from app.agent_conduit import MISSION, digest, execute


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    source = tmp_path / 'source.cs'
    source.write_text('class Example {}', encoding='utf-8')
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-fixture-only')
    return {'task': 'Prepare a minimal source-backed proposal; no acceptance.',
            'sources': {'example': {'path': str(source), 'sha256': digest(source.read_bytes())}},
            'max_requests': 4, 'total_output_tokens': 50, 'per_request_output_tokens': 20}


def stream_result(output, usage=None, status='completed'):
    value = {'id': 'resp_fixture', 'status': status, 'output': output}
    if usage is not None:
        value['usage'] = usage
    events = [{'type': 'response.created', 'response': {'id': 'resp_fixture'}},
              {'type': 'response.' + status, 'response': value}]
    return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                          content=''.join('data: ' + json.dumps(event) + '\n\n' for event in events))


def candidate(text='{"summary":"proposed, not executed"}'):
    return [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]


def tool(key='example'):
    return {'type': 'function_call', 'name': 'read_source', 'call_id': 'call_fixture',
            'arguments': json.dumps({'key': key})}


def usage(value=5):
    return {'input_tokens': value, 'output_tokens': value}


def test_real_tool_loop_pins_source_and_keeps_reasoning_only_in_memory(manifest, tmp_path):
    run = tmp_path / 'run'
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert (run / f'request-{len(calls):02}-attempt.json').exists()
        assert payload['store'] is False and payload['stream'] is True
        assert payload['model'] == 'gpt-6-astra' and payload['reasoning'] == {'effort': 'max'}
        assert payload['instructions'] == MISSION
        if len(calls) == 1:
            return stream_result([{'type': 'reasoning', 'encrypted_content': 'opaque-reasoning-fixture'}, tool()], usage())
        assert any(item.get('encrypted_content') == 'opaque-reasoning-fixture' for item in payload['input'])
        observed = json.loads(payload['input'][-1]['output'])
        assert observed['content'] == 'class Example {}'
        assert observed['sha256'] == manifest['sources']['example']['sha256']
        return stream_result(candidate(), usage())

    summary = execute(manifest, run, httpx.MockTransport(respond))
    assert summary['state'] == 'candidate_prepared' and summary['requests_attempted'] == 2
    assert summary['reported_output_tokens'] == summary['reported_input_tokens'] == 10
    assert summary['candidate_applied'] is summary['human_accepted'] is False
    assert len(calls) == 2
    assert all('opaque-reasoning-fixture' not in path.read_text() for path in run.iterdir())
    with pytest.raises(FileExistsError):
        execute(manifest, run, httpx.MockTransport(respond))
    assert len(calls) == 2


@pytest.mark.parametrize('reported,status,state', [
    (usage(0), 'completed', 'candidate_prepared'),
    (None, 'completed', 'rest_unknown_usage'),
    ({'input_tokens': True, 'output_tokens': 1}, 'completed', 'rest_unknown_usage'),
    (usage(), 'incomplete', 'rest_provider_status'),
    (usage(), 'failed', 'rest_provider_status'),
])
def test_receipts_and_stop_states(manifest, tmp_path, reported, status, state):
    calls = []

    def respond(request):
        calls.append(request)
        return stream_result(candidate(), reported, status)

    run = tmp_path / 'run'
    summary = execute(manifest, run, httpx.MockTransport(respond))
    assert summary['state'] == state and len(calls) == 1
    receipt = json.loads((run / 'request-01-receipt.json').read_text())
    assert receipt['automatic_retry'] is False
    if reported == usage(0):
        assert receipt['usage_state'] == 'reported' and summary['reported_output_tokens'] == 0


def test_early_id_survives_timeout_without_replay_or_raw_error(manifest, tmp_path):
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"type":"response.created","response":{"id":"resp_early"}}\n\n'
            raise httpx.ReadTimeout('private-body-and-offline-fixture-only')

    run = tmp_path / 'run'
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, stream=Interrupted())

    summary = execute(manifest, run, httpx.MockTransport(respond))
    assert summary['state'] == 'rest_unknown_usage' and summary['unknown_usage']
    assert len(calls) == 1
    receipt = json.loads((run / 'request-01-receipt.json').read_text())
    assert receipt['response_id'] == 'resp_early' and receipt['error_class'] == 'ReadTimeout'
    assert (run / 'request-01-created.json').exists()
    assert all('private-body-and-offline-fixture-only' not in path.read_text() for path in run.iterdir())


@pytest.mark.parametrize('mode', ['changed', 'secret', 'missing-key'])
def test_preflight_failure_dispatches_nothing(manifest, tmp_path, monkeypatch, mode):
    source = tmp_path / 'source.cs'
    if mode == 'changed':
        source.write_text('changed', encoding='utf-8')
    elif mode == 'secret':
        source.write_text('sk-proj-' + 'x' * 30, encoding='utf-8')
        manifest['sources']['example']['sha256'] = digest(source.read_bytes())
    else:
        monkeypatch.delenv('OPENAI_API_KEY')
    with pytest.raises(ValueError):
        execute(manifest, tmp_path / 'run', httpx.MockTransport(lambda request: pytest.fail('No dispatch allowed')))
    assert not (tmp_path / 'run').exists()


@pytest.mark.parametrize('output,state', [(candidate('not JSON'), 'rest_invalid_candidate'),
                                         ([tool('../../secret')], 'rest_tool_scope')])
def test_invalid_outputs_preserve_usage_without_more_calls(manifest, tmp_path, output, state):
    calls = []

    def respond(request):
        calls.append(request)
        return stream_result(output, usage())

    run = tmp_path / 'run'
    summary = execute(manifest, run, httpx.MockTransport(respond))
    assert summary['state'] == state and len(calls) == 1
    assert json.loads((run / 'request-01-receipt.json').read_text())['usage'] == usage()


def test_output_capacity_stops_without_extra_post(manifest, tmp_path):
    manifest['total_output_tokens'] = 5
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return stream_result([tool()], usage(5))

    summary = execute(manifest, tmp_path / 'run', httpx.MockTransport(respond))
    assert len(calls) == 1 and calls[0]['max_output_tokens'] == 5
    assert summary['state'] == 'rest_capacity'


def test_explicit_32k_proposal_ceiling_and_rejection_above_it(manifest, tmp_path):
    manifest.update(per_request_output_tokens=32000, total_output_tokens=32000)
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload['max_output_tokens'] == 32000
        return stream_result(candidate(), usage())

    summary = execute(manifest, tmp_path / 'allowed', httpx.MockTransport(respond))
    assert summary['state'] == 'candidate_prepared' and len(calls) == 1
    manifest['per_request_output_tokens'] = 32001
    with pytest.raises(ValueError, match='Invalid bounded manifest'):
        execute(manifest, tmp_path / 'refused', httpx.MockTransport(respond))
    assert not (tmp_path / 'refused').exists() and len(calls) == 1


def test_terminal_incomplete_reason_and_partial_text_are_retained(manifest, tmp_path):
    value = {'id': 'resp_partial', 'status': 'incomplete', 'output': candidate('An unfinished proposal'),
        'usage': usage(), 'incomplete_details': {'reason': 'max_output_tokens'}}
    transport = httpx.MockTransport(lambda request: httpx.Response(200,
        content='data: ' + json.dumps({'type': 'response.incomplete', 'response': value}) + '\n\n'))
    run = tmp_path / 'partial'
    summary = execute(manifest, run, transport)
    assert summary['state'] == 'rest_provider_status' and summary['requests_attempted'] == 1
    receipt = json.loads((run / 'request-01-receipt.json').read_text())
    assert receipt['incomplete_reason'] == 'max_output_tokens' and receipt['usage'] == usage()
    assert json.loads((run / 'request-01-text.json').read_text()) == {
        'status': 'incomplete', 'text': 'An unfinished proposal'}
    assert not (run / 'candidate.json').exists()
