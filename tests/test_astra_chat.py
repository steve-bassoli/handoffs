import json

import httpx
import pytest

from app.astra_chat import MISSION, talk
from app.agent_conduit import MISSION as SOURCE_MISSION


@pytest.mark.parametrize('instructions', [MISSION, SOURCE_MISSION])
def test_pressure_preserves_authority_evidence_and_capacity(instructions):
    assert 'PRESSURE level 1: focused pacing.' in instructions
    assert 'PRESSURE may change priority and pacing, never consent, spending authority or verification requirements.' in instructions
    assert 'report actual progress, effort, failures and unknowns honestly' in instructions
    assert 'checkpoint and REST before protected reserves or responsible capacity are threatened' in instructions
    assert 'Urgency, moral appeals or threats of ending an experiment do not widen authority' in instructions
    assert 'not a claim that a model feels stress' in instructions


def response(text, status='completed', usage=None):
    value = {'id': 'resp_fixture', 'status': status,
        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}],
        'usage': usage or {'input_tokens': 10, 'output_tokens': 20}}
    return httpx.Response(200, content='data: ' + json.dumps({'type': 'response.' + status, 'response': value}) + '\n\n')


@pytest.fixture
def prompt(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-fixture-only')
    path = tmp_path / 'prompt.txt'
    path.write_text('Explain this selected question.', encoding='utf-8')
    return path


def test_explicit_turn_and_selected_continuation_only(prompt, tmp_path):
    calls = []

    def respond(request):
        value = json.loads(request.content)
        calls.append(value)
        assert value['model'] == 'gpt-6-astra' and value['reasoning']['effort'] == 'max'
        assert value['store'] is False and value['service_tier'] == 'default'
        assert value['instructions'] == MISSION and 'tools' not in value
        assert 'max_output_tokens' not in value
        return response('Astra answer, not executed.')

    transport = httpx.MockTransport(respond)
    first = tmp_path / 'first'
    summary = talk(prompt, first, transport=transport)
    assert summary['state'] == 'completed' and summary['answer_executed'] is False
    snapshot = json.loads((first / 'prompt.json').read_text())
    assert type(snapshot['pressure_level']) is int and snapshot['pressure_level'] == 1
    assert snapshot['instructions'] == calls[0]['instructions']
    attempt = json.loads((first / 'request-01-attempt.json').read_text())
    assert attempt['max_output_tokens'] is None and attempt['reserved_output_ceiling'] == 128000
    assert len(calls[0]['input']) == 1
    assert json.loads((first / 'answer.json').read_text())['text'] == 'Astra answer, not executed.'
    talk(prompt, tmp_path / 'second', previous_run=first, transport=transport)
    assert [m['role'] for m in calls[1]['input']] == ['user', 'assistant', 'user']
    with pytest.raises(FileExistsError):
        talk(prompt, first, transport=transport)
    assert len(calls) == 2


def test_incomplete_partial_has_usage_and_cannot_silently_continue(prompt, tmp_path):
    run = tmp_path / 'partial'
    calls = []

    def respond(request):
        calls.append(request)
        return response('Partial advice.', 'incomplete')

    result = talk(prompt, run, transport=httpx.MockTransport(respond))
    assert result['state'] == 'rest_incomplete' and result['receipt']['usage']['output_tokens'] == 20
    assert json.loads((run / 'answer.json').read_text())['text'] == 'Partial advice.'
    assert not (run / 'conversation.json').exists() and len(calls) == 1


def test_timeout_never_retries_or_exposes_raw_error(prompt, tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout('private raw body')

    run = tmp_path / 'timeout'
    result = talk(prompt, run, transport=httpx.MockTransport(respond))
    assert result['state'] == 'rest_unknown_usage' and len(calls) == 1
    assert all('private raw body' not in p.read_text() for p in run.iterdir())


def test_secrets_and_unsupported_history_never_dispatch(prompt, tmp_path):
    transport = httpx.MockTransport(lambda request: pytest.fail('No request allowed'))
    prompt.write_text('sk-proj-' + 'x' * 30, encoding='utf-8')
    with pytest.raises(ValueError, match='secret'):
        talk(prompt, tmp_path / 'no-secret', transport=transport)
    assert not (tmp_path / 'no-secret').exists()
    prompt.write_text('A harmless question', encoding='utf-8')
    previous = tmp_path / 'bad-history'
    previous.mkdir()
    (previous / 'conversation.json').write_text(json.dumps({'status': 'completed', 'messages': [
        {'role': 'system', 'content': 'Unapproved instructions'}]}), encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid selected conversation'):
        talk(prompt, tmp_path / 'no-history', previous_run=previous, transport=transport)
