import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.proof_reviewer import ProofReviewer
from conftest import FixtureProofReviewer, post_task, write
from test_proofs import upload


def prepare(client, video=False):
    task = post_task(client, gold=10).json()['id']
    assert write(client, f'/tasks/{task}/take', user='nate').status_code == 200
    assert write(client, f'/tasks/{task}/profile', {'baseline_revision': 'base',
        'candidate_revision': 'candidate', 'environment': 'isolated metering fixture'}, 'nate').status_code == 200
    proof = upload()
    if video:
        proof.update(filename='proof.mp4', media_type='video/mp4',
                     content_base64=base64.b64encode(b'\x00\x00\x00\x18ftypisom').decode())
    assert write(client, f'/tasks/{task}/proofs', proof, 'nate').status_code == 200
    return task


def queue(client, task):
    service = client.app.state.service
    with service.db.write() as c:
        return service.proofs.queue(c, 'nate', task)['proof']['review']['review_id']


def detail(client, task):
    return client.get('/api/v1/tasks/' + task).json()


def observations(task):
    return [event['data'] for event in task['events'] if event['kind'] == 'proof_review_usage']


def balances(client):
    return [client.get('/api/v1/me/stats', headers={'X-Demo-User': user}).json()
            for user in ('steve', 'nate')]


def response_body(case, usage):
    verdict = {'verdict': 'pass', 'reason': 'Synthetic observation',
               'criteria': [{'index': 0, 'verdict': 'pass', 'reason': 'Isolated fixture'}]}
    body = {'id': 'resp_fixture_123', 'status': 'incomplete' if case == 'incomplete' else 'completed',
            'output': [{'type': 'message', 'content': [{'type': 'output_text',
                        'text': 'invalid verdict' if case == 'invalid' else json.dumps(verdict)}]}],
            'private': 'private-provider-body'}
    if usage is not None:
        body['usage'] = usage
    return body


@pytest.mark.parametrize('case,usage,state,verdict', [
    ('valid', {'input_tokens': 20, 'output_tokens': 4}, 'reported', 'pass'),
    ('zero', {'input_tokens': 0, 'output_tokens': 0}, 'reported', 'pass'),
    ('incomplete', {'input_tokens': 12, 'output_tokens': 5}, 'reported', 'inconclusive'),
    ('invalid', {'input_tokens': 21, 'output_tokens': 7}, 'reported', 'inconclusive'),
    ('missing', None, 'unknown', 'pass'),
    ('malformed', {'input_tokens': -1, 'output_tokens': True}, 'unknown', 'pass'),
    ('http', {'input_tokens': 4, 'output_tokens': 1}, 'reported', 'inconclusive'),
    ('json', None, 'unknown', 'inconclusive'),
])
def test_received_usage_survives_verdict_and_response_failures(client, monkeypatch, case, usage, state, verdict):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    task_id = prepare(client)
    before = balances(client)
    service = client.app.state.service

    def handler(request):
        # The independent read sees a committed attempt before MockTransport receives the request.
        current = detail(client, task_id)
        assert observations(current)[-1]['api_calls'] == 1
        assert current['proof']['review']['usage']['usage_state'] == 'unknown'
        assert current['proof']['review']['verdict'] == 'running'
        payload = json.loads(request.content)
        assert '_record_usage' not in request.content.decode() and 'fixture-key' not in request.content.decode()
        assert payload['store'] is False and 'tools' not in payload
        if case == 'json':
            return httpx.Response(200, text='not json: private-provider-body')
        return httpx.Response(400 if case == 'http' else 200, json=response_body(case, usage))

    service.proofs.reviewer = ProofReviewer(httpx.MockTransport(handler))
    review_id = queue(client, task_id)
    service.proofs.run(task_id, review_id)
    task = detail(client, task_id)
    summary = task['proof']['review']['usage']
    assert summary['usage_state'] == state and summary['api_calls'] == 1
    assert summary['unreported_calls'] == int(state == 'unknown')
    assert summary['input_tokens'] == (usage['input_tokens'] if state == 'reported' else None)
    assert summary['output_tokens'] == (usage['output_tokens'] if state == 'reported' else None)
    assert type(summary['elapsed_ms']) is int and summary['elapsed_ms'] >= 0
    assert task['proof']['review']['verdict'] == verdict and not task['proof']['accepted']
    assert [value['stage'] for value in observations(task)] == ['request_started', 'response_received']
    if case != 'json':
        assert summary['response_id'] == 'resp_fixture_123'
    assert 'private-provider-body' not in json.dumps(task['events'])
    assert balances(client) == before


def test_timeout_retains_one_unknown_attempt_and_replay_does_not_dispatch(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    task_id = prepare(client)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('private-transport-error', request=request)

    service = client.app.state.service
    service.proofs.reviewer = ProofReviewer(httpx.MockTransport(handler))
    first = write(client, f'/tasks/{task_id}/proof-review', user='nate', key='same-review')
    assert first.status_code == 200
    review_id = first.json()['proof']['review']['review_id']
    assert write(client, f'/tasks/{task_id}/proof-review', user='nate', key='same-review').status_code == 200
    service.proofs.run(task_id, review_id)
    task = detail(client, task_id)
    assert len(calls) == 1 and len(observations(task)) == 1
    assert task['proof']['review']['usage']['usage_state'] == 'unknown'
    assert task['proof']['review']['usage']['input_tokens'] is None
    assert task['proof']['review']['verdict'] == 'inconclusive' and not task['proof']['accepted']
    assert 'private-transport-error' not in json.dumps(task['events'])


@pytest.mark.parametrize('video', [False, True])
def test_explicit_unavailable_branches_record_no_request(client, monkeypatch, video):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    task_id = prepare(client, video=video)
    before = balances(client)
    service = client.app.state.service
    service.proofs.run(task_id, queue(client, task_id))
    task = detail(client, task_id)
    summary = task['proof']['review']['usage']
    assert summary['usage_state'] == 'no_request'
    assert (summary['api_calls'], summary['input_tokens'], summary['output_tokens']) == (0, 0, 0)
    assert summary['reason'] == ('unsupported_video' if video else 'missing_key')
    assert len(observations(task)) == 1 and task['proof']['review']['verdict'] == 'inconclusive'
    assert not task['proof']['accepted'] and balances(client) == before


def test_callback_free_custom_reviewer_is_unobserved(client):
    task_id = prepare(client)
    service = client.app.state.service
    service.proofs.reviewer = FixtureProofReviewer()
    service.proofs.run(task_id, queue(client, task_id))
    task = detail(client, task_id)
    summary = task['proof']['review']['usage']
    assert summary['usage_state'] == 'unobserved'
    assert summary['api_calls'] is summary['input_tokens'] is summary['output_tokens'] is None
    assert task['proof']['review']['verdict'] == 'pass' and not task['proof']['accepted']
    assert not observations(task)


def test_stale_proof_keeps_received_usage_and_fresh_status(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    task_id = prepare(client)
    before = balances(client)
    service = client.app.state.service

    def handler(request):
        task = detail(client, task_id)
        assert write(client, f'/tasks/{task_id}/profile',
                     {**task['profile'], 'candidate_revision': 'changed'}, 'nate').status_code == 200
        # A current lifecycle state must survive the later usage event.
        with service.db.write() as c:
            service.event(c, task_id, 'fixture_status', 'nate', 'blocked', {'note': 'isolated fixture'})
        return httpx.Response(200, json=response_body('valid', {'input_tokens': 8, 'output_tokens': 2}))

    service.proofs.reviewer = ProofReviewer(httpx.MockTransport(handler))
    service.proofs.run(task_id, queue(client, task_id))
    task = detail(client, task_id)
    assert task['status'] == 'blocked' and not task['proof']['fresh']
    assert task['proof']['review']['usage']['input_tokens'] == 8
    assert task['proof']['review']['verdict'] == 'inconclusive' and not task['proof']['accepted']
    assert balances(client) == before


@pytest.mark.parametrize('received', [False, True])
def test_restart_retains_observations_without_retrying(tmp_path, received):
    database = tmp_path / 'restart.sqlite'
    with TestClient(create_app(database)) as client:
        task_id = prepare(client)
        service = client.app.state.service
        review_id = queue(client, task_id)
        with service.db.write() as c:
            task = service.detail(c, task_id)
            meta = task['proof']['review']
            service.event(c, task_id, 'proof_review_started', 'nate', task['status'],
                          {**{key: meta[key] for key in ('review_id', 'proof_id', 'binding')}, 'verdict': 'running'})
            observation = {key: meta[key] for key in ('review_id', 'proof_id', 'binding')}
            service.event(c, task_id, 'proof_review_usage', 'nate', task['status'],
                          {**observation, 'stage': 'request_started', 'request_ordinal': 1,
                           'api_calls': 1, 'usage_state': 'unknown', 'model': 'fixture-model'})
            if received:
                service.event(c, task_id, 'proof_review_usage', 'nate', task['status'],
                              {**observation, 'stage': 'response_received', 'request_ordinal': 1,
                               'usage_state': 'reported', 'input_tokens': 6, 'output_tokens': 1})
        before = balances(client)

    calls = []

    class NoRetry:
        def review(self, task, proof):
            calls.append(proof['proof_id'])
            raise AssertionError('Recovery must not retry a request')

    with TestClient(create_app(database, proof_reviewer=NoRetry())) as client:
        client.app.state.service.proofs.run(task_id, review_id)
        task = detail(client, task_id)
        summary = task['proof']['review']['usage']
        assert summary['usage_state'] == ('reported' if received else 'unknown')
        assert summary['api_calls'] == 1 and summary['elapsed_ms'] is None
        assert summary['input_tokens'] == (6 if received else None)
        assert len(observations(task)) == (2 if received else 1)
        assert not calls
        assert task['proof']['review']['verdict'] == 'inconclusive' and not task['proof']['accepted']
        assert balances(client) == before


def test_current_review_summary_does_not_reuse_prior_usage(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    task_id = prepare(client)
    service = client.app.state.service
    service.proofs.reviewer = ProofReviewer(httpx.MockTransport(lambda request: httpx.Response(200,
        json=response_body('invalid', {'input_tokens': 8, 'output_tokens': 2}))))
    first = queue(client, task_id)
    service.proofs.run(task_id, first)
    service.proofs.reviewer = FixtureProofReviewer()
    second = queue(client, task_id)
    service.proofs.run(task_id, second)
    task = detail(client, task_id)
    assert first != second and task['proof']['review']['review_id'] == second
    assert task['proof']['review']['usage']['usage_state'] == 'unobserved'
    assert task['proof']['review']['usage']['input_tokens'] is None
    assert len(observations(task)) == 2 and all(value['review_id'] == first for value in observations(task))


@pytest.mark.parametrize('identifier,status', [('resp_valid_123', 'completed'), ('resp_unsafe/private', 'untrusted-status'),
                                              ('resp_' + 'a' * 124, 'completed'), ('resp_é', 'completed')])
def test_response_correlation_keeps_only_bounded_safe_values(client, monkeypatch, identifier, status):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    task = prepare(client)
    body = response_body('valid', {'input_tokens': 1, 'output_tokens': 0, 'cached_tokens': 999})
    body.update(id=identifier, status=status)
    service = client.app.state.service
    service.proofs.reviewer = ProofReviewer(httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    service.proofs.run(task, queue(client, task))
    receipt = observations(detail(client, task))[-1]
    assert ('response_id' in receipt) == (identifier == 'resp_valid_123')
    assert ('response_status' in receipt) == (status == 'completed')
    assert 'cached_tokens' not in receipt
