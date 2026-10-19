import json
from threading import Event

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import architect_chat as chat
from app.api_budget import BudgetError, upper_cents


@pytest.fixture
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-fixture-only')
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        value = {'id': 'resp_fixture', 'status': 'completed',
                 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Advice only.'}]}],
                 'usage': {'input_tokens': 10, 'output_tokens': 20}}
        return httpx.Response(200, content='data: ' + json.dumps({'type': 'response.completed', 'response': value}) + '\n\n')
    return tmp_path / 'threads', httpx.MockTransport(respond), calls


def turn(identifier=None, architect='bob-the-architect', message='Explain this design.'):
    return chat.Turn(architect=architect, message=message, thread_id=identifier)


def test_saved_continuation_persona_cost_and_owner(offline):
    root, transport, calls = offline
    code, first = chat.send(root, 'alice', turn(architect='sue-the-architect'), transport)
    identifier = first['thread_id']
    assert code == 200 and first['state'] == 'ready'
    assert 'You are sue-the-architect' in calls[0]['instructions']
    assert 'tools' not in calls[0]
    assert first['messages'][-1]['cost']['amount'] == upper_cents('gpt-6-astra', 10, 20)
    assert all(item['at_utc'] and item['who'] for item in first['messages'])
    assert chat.read(root, identifier, 'alice') == first
    code, second = chat.send(root, 'alice', turn(identifier, 'sue-the-architect'), transport)
    assert code == 200 and len(second['messages']) == 4
    assert [item['role'] for item in calls[1]['input']] == ['user', 'assistant', 'user']
    assert len(list((root / identifier).glob('*/conversation.json'))) == 2
    with pytest.raises(chat.HTTPException) as error:
        chat.read(root, identifier, 'mallory')
    assert error.value.status_code == 404
    assert chat.listing(root, 'mallory')['items'] == []
    with pytest.raises(chat.HTTPException):
        chat.send(root, 'mallory', turn(identifier, 'sue-the-architect'), transport)
    with pytest.raises(chat.HTTPException):
        chat.send(root, 'alice', turn(identifier), transport)
    assert len(calls) == 2


def test_secret_rejected_without_dispatch(offline):
    root, transport, calls = offline
    with pytest.raises(ValueError, match='secret'):
        chat.send(root, 'alice', turn(message='sk-proj-' + 'x' * 30), transport)
    assert calls == [] and not root.exists()


def test_budget_refusal_is_saved_and_not_replayed(offline, monkeypatch):
    root, transport, calls = offline
    def refuse(*args, **kwargs):
        raise BudgetError('Protected reserve')
    monkeypatch.setattr(chat.astra_chat, 'talk', refuse)
    code, record = chat.send(root, 'alice', turn(), transport)
    assert code == 402 and record['state'] == 'blocked'
    assert 'spending limits were not changed' in record['messages'][-1]['content']
    with pytest.raises(chat.HTTPException):
        chat.send(root, 'alice', turn(record['thread_id']), transport)
    assert calls == []


def test_unknown_usage_blocks_continuation(offline):
    root, _, _ = offline
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('private provider body')
    code, record = chat.send(root, 'alice', turn(), httpx.MockTransport(timeout))
    assert code == 503 and record['state'] == 'blocked'
    assert record['messages'][-1]['cost'] is None
    with pytest.raises(chat.HTTPException):
        chat.send(root, 'alice', turn(record['thread_id']), httpx.MockTransport(timeout))
    assert len(calls) == 1
    assert 'private provider body' not in json.dumps(record)


def test_partial_has_cost_but_cannot_continue(offline):
    root, _, _ = offline
    def partial(request):
        value = {'status': 'incomplete', 'output': [], 'usage': {'input_tokens': 10, 'output_tokens': 20}}
        return httpx.Response(200, content='data: ' + json.dumps({'type': 'response.incomplete', 'response': value}) + '\n\n')
    code, record = chat.send(root, 'alice', turn(), httpx.MockTransport(partial))
    assert code == 503 and record['state'] == 'blocked'
    assert record['messages'][-1]['cost']['amount'] == upper_cents('gpt-6-astra', 10, 20)


def client_app(root):
    app = FastAPI()
    app.state.architect_chat_root = root
    @app.middleware('http')
    async def identity(request, call_next):
        request.state.identity = {'principal': request.headers.get('X-Fixture-Principal', 'demo-header'), 'user_id': 'alice'}
        return await call_next(request)
    chat.install(app)
    return app


def test_routes_require_human_and_validate(offline):
    root, _, _ = offline
    with TestClient(client_app(root)) as client:
        assert client.get('/api/v1/architect-chat').status_code == 401
        assert client.post('/api/v1/architect-chat', json=turn().model_dump()).status_code == 401
        headers = {'X-Fixture-Principal': 'human'}
        assert client.get('/api/v1/architect-chat', headers=headers).json() == {'items': []}
        assert client.post('/api/v1/architect-chat', headers=headers, json={'architect': 'other', 'message': 'Hello'}).status_code == 422
        assert client.post('/api/v1/architect-chat', headers=headers, json={'architect': 'bob-the-architect', 'message': 'sk-proj-' + 'x' * 30}).status_code == 422
        assert client.get('/api/v1/architect-chat/not-a-thread', headers=headers).status_code == 404


def test_route_timeout_keeps_worker_and_pending_lock(offline, monkeypatch):
    root, transport, calls = offline
    entered, release, finished = Event(), Event(), Event()
    original = chat.astra_chat.talk
    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        kwargs['transport'] = transport
        try:
            return original(*args, **kwargs)
        finally:
            finished.set()
    monkeypatch.setattr(chat.astra_chat, 'talk', delayed)
    monkeypatch.setattr(chat, 'TIMEOUT', 0.05)
    identifier = 'a' * 32
    with TestClient(client_app(root)) as client:
        headers = {'X-Fixture-Principal': 'human'}
        try:
            result = client.post('/api/v1/architect-chat', headers=headers, json=turn(identifier).model_dump())
            assert entered.is_set() and result.status_code == 503
            assert result.json()['thread_id'] == identifier
            saved = client.get('/api/v1/architect-chat/' + identifier, headers=headers)
            assert saved.json()['state'] == 'pending'
            assert client.post('/api/v1/architect-chat', headers=headers, json=turn(identifier).model_dump()).status_code == 409
        finally:
            release.set()
            assert finished.wait(5)
    assert len(calls) == 1
