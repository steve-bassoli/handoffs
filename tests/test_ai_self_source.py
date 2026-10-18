import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import SourceEdit, read_source
from app.main import create_app
from app.services import RuleError
from conftest import post_task, write
from test_ai import FakeLuna, decision, get_run, source_zip


@pytest.mark.parametrize('path,before,after', [
    ('app/ai.py', '"""Small, persisted AI workflow. Generated code is delivered for local execution."""',
     '"""Small, persisted AI workflow. Generated patches require local verification."""'),
    ('app/services.py', 'def now():', 'def now():  # Current timestamp'),
])
def test_engine_source_roundtrip_and_nonnoop_delivery(tmp_path, path, before, after):
    source = Path(__file__).parents[1].joinpath(path).read_text(encoding='utf-8')
    supplied = source_zip({path: source})
    assert read_source(supplied) == {path: source}
    result = decision('deliver', instructions='Run focused tests locally.',
        verification=['python -m pytest -q tests/test_ai_self_source.py'], plan=[{
            'id': 'self-source', 'title': 'Clarify local verification', 'complexity': 'LOW',
            'work_type': 'implementation', 'files': [path], 'children': []}])
    result.edits = [SourceEdit(path=path, before=before, after=after)]
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=FakeLuna([result]))) as client:
        task_id = post_task(client).json()['id']
        stats = client.get('/api/v1/me/stats').json()
        assert write(client, f'/tasks/{task_id}/ai/start', {'source_zip': supplied}).status_code == 200
        assert get_run(client, task_id)['status'] == 'ready'
        response = client.get(f'/api/v1/tasks/{task_id}/ai/artifact')
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read('workspace/' + path).decode() == source.replace(before, after, 1)
            assert '+' + after in archive.read('changes.patch').decode()
            assert 'No build or tests have been run' in archive.read('START_HERE.md').decode()
        task = client.get(f'/api/v1/tasks/{task_id}').json()
        assert task['phase'] != 'Closed'
        assert client.get('/api/v1/me/stats').json() == stats


def test_api_prefix_profile_still_rejected_without_state_change(client):
    task_id = post_task(client).json()['id']
    profile = {'validation_scope': 'SIM', 'migration_stage': 'WRAP',
               'baseline_revision': 'fixture-base', 'candidate_revision': 'fixture-candidate',
               'environment': 'isolated fixture'}
    assert write(client, f'/tasks/{task_id}/profile', profile).status_code == 200
    stats = client.get('/api/v1/me/stats').json()
    task = client.get(f'/api/v1/tasks/{task_id}').json()
    rejected = write(client, f'/tasks/{task_id}/profile',
                     {**profile, 'environment': 'sk-proj-not-a-real-secret'})
    assert rejected.status_code == 422
    assert 'Keep secrets out of task context' in rejected.text
    assert client.get(f'/api/v1/tasks/{task_id}').json() == task
    assert task['profile']['environment'] == 'isolated fixture'
    assert task['phase'] != 'Closed' and task['ai_run'] is None
    assert client.get('/api/v1/me/stats').json() == stats


@pytest.mark.parametrize('marker', ['sk-proj-', '-----BEGIN PRIVATE KEY-----'])
def test_marker_bearing_source_and_output_still_rejected(tmp_path, marker):
    with pytest.raises(RuleError):
        read_source(source_zip({'calc.py': marker + 'not-a-real-secret'}))
    result = decision('deliver', files=[{'path': 'calc.py', 'content': marker + 'not-a-real-secret'}],
        instructions='Inspect locally.')
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=FakeLuna([result]))) as client:
        task = post_task(client).json()['id']
        stats = client.get('/api/v1/me/stats').json()
        assert write(client, f'/tasks/{task}/ai/start', {'source_zip': source_zip()}).status_code == 200
        assert get_run(client, task)['status'] == 'failed'
        assert 'Secret in model output' in get_run(client, task)['error']
        assert client.get(f'/api/v1/tasks/{task}/ai/artifact').status_code != 200
        assert client.get(f'/api/v1/tasks/{task}').json()['phase'] != 'Closed'
        assert client.get('/api/v1/me/stats').json() == stats


def test_api_prefix_context_and_answers_still_rejected(tmp_path):
    model = FakeLuna([decision('ask', questions=['Which environment?'])])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        task = post_task(client).json()['id']
        stats = client.get('/api/v1/me/stats').json()
        assert write(client, f'/tasks/{task}/ai/start', {'context': 'sk-proj-not-a-real-secret'}).status_code == 422
        assert model.calls == 0 and get_run(client, task) is None
        assert write(client, f'/tasks/{task}/ai/start', {'source_zip': source_zip()}).status_code == 200
        assert write(client, f'/tasks/{task}/ai/answers', {'answers': ['sk-proj-not-a-real-secret']}).status_code == 422
        assert model.calls == 1 and get_run(client, task)['status'] == 'needs_input'
        assert client.get(f'/api/v1/tasks/{task}').json()['phase'] != 'Closed'
        assert client.get('/api/v1/me/stats').json() == stats
