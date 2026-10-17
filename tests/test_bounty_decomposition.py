import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.importer import import_git
from app.main import create_app
from app.storage import one
from conftest import write
from test_imports import fixture_repository
from test_ai import FakeLuna, decision, source_zip
from test_packages import package


def completed_packet(client, tmp_path):
    import json
    repo, directory, git = fixture_repository(tmp_path)
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['recipient'] = 'STEVE'
    renamed = directory.with_name('prove-demo-steve')
    directory.rename(renamed)
    (renamed / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (renamed / 'context.md').write_text('# Fixture\n\n## Goal\n\nPinned scope\n\n## Acceptance criteria\n\n- Pinned criteria\n', encoding='utf-8')
    event = {'schemaVersion': 1, 'eventId': 'completed-one', 'taskId': 'prove-demo', 'type': 'completed',
             'actor': 'NATE', 'createdUtc': '2026-10-16T12:00:00Z', 'resultPath': '', 'replyTo': ''}
    (renamed / 'events/completed-one.json').write_text(json.dumps(event), encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Completed packet')
    assert not import_git(client.app.state.service.db, repo, 'HEAD')['gaps']
    return 'prove-demo'


def test_reopen_is_authorized_idempotent_and_preserves_completion_evidence_and_gold(client, tmp_path):
    bounty_id = completed_packet(client, tmp_path)
    before = client.get(f'/api/v1/bounties/{bounty_id}').json()
    payload = {'complexity': 'HIGH', 'note': 'Reopen for bounded decomposition, not acceptance.'}
    assert write(client, f'/bounties/{bounty_id}/reopen', payload, user='will').status_code == 403
    for _ in range(2):
        response = write(client, f'/bounties/{bounty_id}/reopen', payload, key='reopen')
        assert response.status_code == 200, response.text
        after = response.json()
        assert after['status'] == 'open' and after['complexity'] == 'HIGH'
        assert after['completed_by'] == 'nate' and after['legacy'] == before['legacy']
        assert after['events'][:-1] == before['events']
        assert after['packages'] == before['packages'] and after['funded'] == 0
    assert write(client, f'/bounties/{bounty_id}/reopen', payload).status_code == 409
    with client.app.state.service.db.engine.connect() as c:
        assert one(c, 'SELECT COUNT(*) AS n FROM gold_transactions')['n'] == 0
        assert one(c, 'SELECT COUNT(*) AS n FROM ai_runs')['n'] == 0
    assert client.get('/api/v1/bounties?view=all').json()['items'][0]['complexity'] == 'HIGH'


def test_reopened_high_processes_original_and_response_then_waits_for_full_human_approval(tmp_path):
    proposals = [{'title': f'Medium outcome {index}', 'goal': 'One bounded remaining outcome',
                  'criteria': ['Actual evidence is recorded'], 'complexity': 'MEDIUM'} for index in range(3)]

    class InspectEvidence(FakeLuna):
        def generate(self, task, data):
            assert task['complexity'] == 'HIGH' and task['completed_by'] == 'nate'
            assert '- Pinned criteria' in data['source']['_bounty/original-context.md']
            assert any(path.endswith('TICKET_RESPONSE.md') and text == 'Fresh-context review'
                       for path, text in data['source'].items())
            assert json.loads(data['source']['_bounty/package-provenance.json'])[0]['input_verified']
            return super().generate(task, data)

    with TestClient(create_app(tmp_path / 'flow.sqlite', ai_model=InspectEvidence([decision('followups', proposals=proposals)]))) as client:
        bounty_id = completed_packet(client, tmp_path)
        original = client.get(f'/api/v1/bounties/{bounty_id}/artifacts/download').content
        response = package(bounty_id, {'TICKET_RESPONSE.md': 'Fresh-context review'}, input_sha256=hashlib.sha256(original).hexdigest())
        assert write(client, f'/bounties/{bounty_id}/packages', {'kind': 'response', 'package_zip': response,
            'input_zip': base64.b64encode(original).decode()}).status_code == 200
        assert write(client, f'/bounties/{bounty_id}/reopen', {'complexity': 'HIGH', 'note': 'Decompose; do not create children yet.'}).status_code == 200
        assert write(client, f'/bounties/{bounty_id}/ai/start', {}).status_code == 200
        task = client.get(f'/api/v1/bounties/{bounty_id}').json()
        assert task['status'] == 'awaiting_approval' and task['ai_run']['status'] == 'followups_pending'
        assert [proposal['complexity'] for proposal in task['ai_run']['result']['proposals']] == ['MEDIUM'] * 3
        assert len(client.get(f'/api/v1/bounties/{bounty_id}/lineage').json()['items']) == 1
        assert write(client, f'/bounties/{bounty_id}/ai/confirm-followups', {'indices': [0, 1]}).status_code == 422
        assert len(client.get(f'/api/v1/bounties/{bounty_id}/lineage').json()['items']) == 1
        approved = write(client, f'/bounties/{bounty_id}/ai/confirm-followups', {'indices': [0, 1, 2]}, key='approval')
        assert approved.status_code == 200 and approved.json()['status'] == 'decomposed'
        assert approved.json()['events'][-1]['data']['acceptance_verified'] is False
        assert write(client, f'/bounties/{bounty_id}/ai/confirm-followups', {'indices': [0, 1, 2]}, key='approval').json() == approved.json()
        items = client.get(f'/api/v1/bounties/{bounty_id}/lineage').json()['items']
        assert len(items) == 4
        for item in items:
            if item['id'] != bounty_id:
                child = client.get('/api/v1/bounties/' + item['id']).json()
                assert child['complexity'] == 'MEDIUM' and child['parent_id'] == bounty_id and child['funded'] == 0
        assert write(client, f'/bounties/{bounty_id}/ai/complete', {'evidence': 'Children exist'}).status_code == 409
        with client.app.state.service.db.engine.connect() as c:
            assert one(c, 'SELECT COUNT(*) AS n FROM gold_transactions')['n'] == 0


@pytest.mark.parametrize('parent,levels', [('HIGH', ['MEDIUM']), ('HIGH', ['LOW'] * 3),
    ('HIGH', ['HIGH', 'MEDIUM']), ('MEDIUM', ['LOW']), ('LOW', ['HIGH'] * 2)])
def test_invalid_child_bounty_splits_cannot_publish_proposals(tmp_path, parent, levels):
    proposals = [{'title': f'Child {index}', 'goal': 'Scope', 'criteria': ['Evidence'], 'complexity': level}
                 for index, level in enumerate(levels)]
    with TestClient(create_app(tmp_path / 'invalid.sqlite', ai_model=FakeLuna([decision('followups', proposals=proposals)]))) as client:
        bounty = write(client, '/bounties', {'title': 'Parent', 'goal': 'Outcome', 'criteria': ['Verified'],
            'gold': 50, 'complexity': parent}).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {})
        task = client.get(f'/api/v1/bounties/{bounty}').json()
        assert task['ai_run']['status'] == 'failed' and task['status'] == 'working'
        assert len(client.get(f'/api/v1/bounties/{bounty}/lineage').json()['items']) == 1


@pytest.mark.parametrize('complexity', ['HIGH', 'MEDIUM'])
def test_composite_bounties_cannot_deliver_implementation(tmp_path, complexity):
    model = FakeLuna([decision('deliver', files=[{'path': 'calc.py', 'content': 'fixed'}], instructions='Test')])
    with TestClient(create_app(tmp_path / 'composite.sqlite', ai_model=model)) as client:
        bounty = write(client, '/bounties', {'title': 'Parent', 'goal': 'Outcome', 'criteria': ['Verified'],
            'gold': 50, 'complexity': complexity}).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        assert client.get(f'/api/v1/bounties/{bounty}').json()['ai_run']['status'] == 'failed'
        assert client.get(f'/api/v1/bounties/{bounty}/ai/artifact').status_code == 409
