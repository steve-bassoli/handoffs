import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import SourceEdit, read_source
from app.main import create_app
from app.services import RuleError
from conftest import post_bounty, write
from test_ai import FakeLuna, decision, get_run, source_zip


def test_engine_source_roundtrip_and_nonnoop_delivery(tmp_path):
    source = Path(__file__).parents[1].joinpath('app/ai.py').read_text(encoding='utf-8')
    supplied = source_zip({'app/ai.py': source})
    assert read_source(supplied) == {'app/ai.py': source}
    before = '"""Small, persisted AI workflow. Generated code is delivered for local execution."""'
    after = '"""Small, persisted AI workflow. Generated patches require local verification."""'
    result = decision('deliver', instructions='Run focused tests locally.',
        verification=['python -m pytest -q tests/test_ai_self_source.py'], plan=[{
            'id': 'self-source', 'title': 'Clarify local verification', 'complexity': 'LOW',
            'work_type': 'implementation', 'files': ['app/ai.py'], 'children': []}])
    result.edits = [SourceEdit(path='app/ai.py', before=before, after=after)]
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=FakeLuna([result]))) as client:
        bounty = post_bounty(client).json()['id']
        stats = client.get('/api/v1/me/stats').json()
        assert write(client, f'/bounties/{bounty}/ai/start', {'source_zip': supplied}).status_code == 200
        assert get_run(client, bounty)['status'] == 'ready'
        response = client.get(f'/api/v1/bounties/{bounty}/ai/artifact')
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read('workspace/app/ai.py').decode() == source.replace(before, after, 1)
            assert '+"""Small, persisted AI workflow. Generated patches' in archive.read('changes.patch').decode()
            assert 'No build or tests have been run' in archive.read('START_HERE.md').decode()
        task = client.get(f'/api/v1/bounties/{bounty}').json()
        assert task['phase'] != 'Closed'
        assert client.get('/api/v1/me/stats').json() == stats


@pytest.mark.parametrize('marker', ['sk-proj-', '-----BEGIN PRIVATE KEY-----'])
def test_marker_bearing_source_and_output_still_rejected(tmp_path, marker):
    with pytest.raises(RuleError):
        read_source(source_zip({'calc.py': marker + 'not-a-real-secret'}))
    result = decision('deliver', files=[{'path': 'calc.py', 'content': marker + 'not-a-real-secret'}],
        instructions='Inspect locally.')
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=FakeLuna([result]))) as client:
        bounty = post_bounty(client).json()['id']
        stats = client.get('/api/v1/me/stats').json()
        assert write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()}).status_code == 200
        assert get_run(client, bounty)['status'] == 'failed'
        assert 'Secret in model output' in get_run(client, bounty)['error']
        assert client.get(f'/api/v1/bounties/{bounty}/ai/artifact').status_code != 200
        assert client.get(f'/api/v1/bounties/{bounty}').json()['phase'] != 'Closed'
        assert client.get('/api/v1/me/stats').json() == stats


def test_api_prefix_context_and_answers_still_rejected(tmp_path):
    model = FakeLuna([decision('ask', questions=['Which environment?'])])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        stats = client.get('/api/v1/me/stats').json()
        assert write(client, f'/bounties/{bounty}/ai/start', {'context': 'sk-proj-not-a-real-secret'}).status_code == 422
        assert model.calls == 0 and get_run(client, bounty) is None
        assert write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()}).status_code == 200
        assert write(client, f'/bounties/{bounty}/ai/answers', {'answers': ['sk-proj-not-a-real-secret']}).status_code == 422
        assert model.calls == 1 and get_run(client, bounty)['status'] == 'needs_input'
        assert client.get(f'/api/v1/bounties/{bounty}').json()['phase'] != 'Closed'
        assert client.get('/api/v1/me/stats').json() == stats
