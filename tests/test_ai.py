import base64
import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import Decision, Luna, archived_plan, read_source
from app.main import create_app
from app.services import RuleError
from conftest import post_bounty, write


def source_zip(files=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path, content in (files or {'calc.py': 'def add(a, b):\n    return a - b\n'}).items():
            archive.writestr(path, content)
    return base64.b64encode(buffer.getvalue()).decode()


def decision(action, **extra):
    return Decision(action=action, summary='Investigated addition', questions=extra.get('questions', []),
        files=extra.get('files', []), instructions=extra.get('instructions', ''), verification=extra.get('verification', []),
        proposals=extra.get('proposals', []), plan=extra.get('plan', [
            {'id': 'fix', 'title': 'Apply the bounded fix', 'complexity': 'LOW', 'children': [],
             'files': [file['path'] for file in extra.get('files', [])]}] if action == 'deliver' else []))


class FakeLuna:
    model = 'gpt-6-luna'

    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.calls = 0

    def check(self):
        pass

    def generate(self, task, data):
        self.calls += 1
        return next(self.decisions), {'api_calls': 1, 'input_tokens': 25, 'output_tokens': 10}


def get_run(client, bounty):
    return client.get('/api/v1/bounties/' + bounty).json()['ai_run']


def test_questions_answers_zip_and_idempotency(tmp_path):
    model = FakeLuna([decision('ask', questions=['Which Python version?']),
        decision('deliver', files=[{'path': 'calc.py', 'content': 'def add(a, b):\n    return a + b\n'}],
                 instructions='Use Python 3.11. Open workspace/ in Codex.', verification=['python -m unittest'])])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        payload = {'source_zip': source_zip()}
        assert write(client, f'/bounties/{bounty}/ai/start', payload, key='start').status_code == 200
        assert get_run(client, bounty)['status'] == 'needs_input'
        assert get_run(client, bounty)['question_count'] == 1
        assert write(client, f'/bounties/{bounty}/ai/answers', {'answers': ['3.11']}, 'nate').status_code == 403
        assert write(client, f'/bounties/{bounty}/ai/answers', {'answers': []}).status_code == 422
        assert write(client, f'/bounties/{bounty}/ai/answers', {'answers': ['3.11']}, key='answer').status_code == 200
        assert get_run(client, bounty)['status'] == 'ready'
        assert get_run(client, bounty)['usage']['input_tokens'] == 50
        assert write(client, f'/bounties/{bounty}/ai/start', payload, key='start').status_code == 200
        assert write(client, f'/bounties/{bounty}/ai/answers', {'answers': ['3.11']}, key='answer').status_code == 200
        assert model.calls == 2
        result = client.get(f'/api/v1/bounties/{bounty}/ai/artifact')
        assert result.status_code == 200
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            assert archive.read('workspace/calc.py').decode().endswith('return a + b\n')
            assert 'START_HERE.md' in archive.namelist()
            assert 'No build or tests have been run' in archive.read('START_HERE.md').decode()
            assert '-    return a - b' in archive.read('changes.patch').decode()
            assert json.loads(archive.read('bounty.json'))['id'] == bounty
            assert json.loads(archive.read('implementation-plan.json'))['steps'][0]['complexity'] == 'LOW'
            assert 'tools/complexity.py' in archive.namelist()
        assert client.get(f'/api/v1/bounties/{bounty}/ai/artifact').content == result.content
        assert client.get(f'/api/v1/bounties/{bounty}').json()['status'] == 'delivered'
        assert write(client, f'/bounties/{bounty}/ai/complete', {'evidence': 'Local checks passed'}, 'nate').status_code == 403
        assert write(client, f'/bounties/{bounty}/ai/complete', {'evidence': 'Local checks passed'}, key='verified').json()['status'] == 'completed'
        assert client.get(f'/api/v1/bounties/{bounty}/ai/artifact').status_code == 200
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as restarted:
        assert get_run(restarted, bounty)['status'] == 'completed'
        assert restarted.get(f'/api/v1/bounties/{bounty}/ai/artifact').status_code == 200


def test_restart_marks_interrupted_turn_for_explicit_retry(tmp_path):
    model = FakeLuna([decision('ask', questions=['Source?'])])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {})
        with client.app.state.service.db.write() as connection:
            connection.exec_driver_sql("UPDATE ai_runs SET status='running' WHERE bounty_id=?", (bounty,))
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as restarted:
        assert get_run(restarted, bounty)['status'] == 'failed'
        assert 'restarted' in get_run(restarted, bounty)['error']


def test_followups_require_confirmation_and_retain_lineage(tmp_path):
    proposals = [{'title': 'Find the contract', 'goal': 'Resolve the missing contract', 'criteria': ['Contract is pinned']},
                 {'title': 'Implement the fix', 'goal': 'Apply the pinned contract', 'criteria': ['Tests pass']}]
    model = FakeLuna([decision('followups', proposals=proposals), decision('ask', questions=['Which contract?'])])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        before = client.get('/api/v1/me/stats').json()
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        assert get_run(client, bounty)['status'] == 'followups_pending'
        tree = client.get(f'/api/v1/bounties/{bounty}/lineage').json()
        assert len(tree['items']) == 1
        assert client.get(f'/api/v1/bounties/{bounty}').json()['status'] == 'completed'
        assert write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': [0]}, 'nate').status_code == 403
        assert write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': [5]}).status_code == 422
        write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': [0]}, key='confirm')
        write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': [0]}, key='confirm')
        tree = client.get(f'/api/v1/bounties/{bounty}/lineage').json()
        assert len(tree['items']) == 2
        child = next(item for item in tree['items'] if item['parent_id'] == bounty)
        assert child['title'] == 'Find the contract'
        assert client.get(f"/api/v1/bounties/{child['id']}/lineage").json()['root_id'] == bounty
        assert write(client, f"/bounties/{child['id']}/ai/start", {}).status_code == 200
        assert get_run(client, child['id'])['status'] == 'needs_input'
        after = client.get('/api/v1/me/stats').json()
        assert (before['available_gold'], before['reserved_gold']) == (after['available_gold'], after['reserved_gold'])


def test_three_question_limit_across_turns(tmp_path):
    model = FakeLuna([decision('ask', questions=['One?', 'Two?']), decision('ask', questions=['Three?']),
                      decision('ask', questions=['Four?'])])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {})
        write(client, f'/bounties/{bounty}/ai/answers', {'answers': ['a', 'b']})
        write(client, f'/bounties/{bounty}/ai/answers', {'answers': ['c']})
        assert get_run(client, bounty)['question_count'] == 3
        assert get_run(client, bounty)['status'] == 'failed'
        assert len(get_run(client, bounty)['conversation']) == 4


@pytest.mark.parametrize('path', ['../escape.py', '/absolute.py', 'C:/absolute.py', '.env', '.git/config', 'auth.json'])
def test_reject_unsafe_source(path):
    with pytest.raises(RuleError):
        read_source(source_zip({path: 'secret'}))


def test_missing_key_does_not_claim_or_create_run(client, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    bounty = post_bounty(client).json()['id']
    result = write(client, f'/bounties/{bounty}/ai/start', {})
    assert result.status_code == 503
    task = client.get('/api/v1/bounties/' + bounty).json()
    assert task['status'] == 'open' and task['ai_run'] is None


def test_provider_tools_and_api_key_stay_out_of_payload(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert 'test-api-key' not in request.content.decode()
        assert request.headers['Authorization'] == 'Bearer test-api-key'
        assert payload['model'] == 'gpt-6-luna'
        assert payload['store'] is False
        if len(requests) == 1:
            output = [{'type': 'function_call', 'name': 'read_file', 'call_id': 'call-1', 'arguments': '{"path":"calc.py"}'}]
        else:
            assert payload['input'][-1]['output'] == '"source"'
            output = [{'type': 'message', 'content': [{'type': 'output_text', 'text': decision('ask', questions=['Version?']).model_dump_json()}]}]
        return httpx.Response(200, json={'status': 'completed', 'output': output, 'usage': {'input_tokens': 10, 'output_tokens': 5}})
    result, usage = Luna(httpx.MockTransport(handler)).generate(
        {'title': 'Task', 'goal': 'Fix', 'criteria': ['Works'], 'repository': '', 'context_links': []},
        {'source': {'calc.py': 'source'}, 'context': '', 'conversation': [], 'question_count': 0})
    assert result.questions == ['Version?']
    assert usage == {'api_calls': 2, 'input_tokens': 20, 'output_tokens': 10}


def test_target_and_claimant_are_respected(tmp_path):
    model = FakeLuna([])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = write(client, '/bounties', {'title': 'Targeted', 'goal': 'Fix', 'criteria': ['Works'], 'gold': 10, 'target': 'nate'}).json()['id']
        assert write(client, f'/bounties/{bounty}/ai/start', {}).status_code == 403
        write(client, f'/bounties/{bounty}/take', user='nate')
        assert write(client, f'/bounties/{bounty}/ai/start', {}, user='will').status_code == 403


@pytest.mark.parametrize('plan', [[], [{'id': 'parent', 'title': 'Too broad', 'complexity': 'MEDIUM', 'children': [], 'files': ['calc.py']}],
    [{'id': 'leaf', 'title': 'Wrong files', 'complexity': 'LOW', 'children': [], 'files': ['unrelated.py']}]])
def test_invalid_complexity_cannot_publish_a_fix(tmp_path, plan):
    model = FakeLuna([decision('deliver', files=[{'path': 'calc.py', 'content': 'fixed'}], instructions='Test', plan=plan)])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        assert get_run(client, bounty)['status'] == 'failed'
        assert client.get(f'/api/v1/bounties/{bounty}/ai/artifact').status_code == 409


def test_retired_labels_are_not_accepted_in_new_model_plans():
    from pydantic import ValidationError
    for level in ('SMALL', 'LARGE'):
        with pytest.raises(ValidationError):
            decision('deliver', files=[{'path': 'calc.py', 'content': 'fixed'}], instructions='Test',
                plan=[{'id': 'leaf', 'title': 'Invalid label', 'complexity': level, 'children': [], 'files': ['calc.py']}])


def test_historical_plan_projection_does_not_rewrite_original():
    original = [{'id': 'old', 'title': 'Historical change', 'complexity': 'SMALL', 'children': [], 'files': ['calc.py']}]
    projected = archived_plan(original)
    assert projected[0]['complexity'] == 'LOW'
    assert original[0]['complexity'] == 'SMALL'
