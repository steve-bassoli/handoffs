import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import one
from conftest import verified_proof, write
from test_ai import FakeLuna, decision, get_run, source_zip


def post(client, complexity='LOW', work_type='implementation', criteria=None):
    return write(client, '/bounties', {'title': 'Bounded outcome', 'goal': 'Meet the criteria',
        'criteria': criteria or ['Observable result'], 'gold': 50,
        'complexity': complexity, 'work_type': work_type}).json()['id']


def test_verification_low_delivers_report_without_patch_commit_or_automatic_acceptance(tmp_path):
    model = FakeLuna([decision('evidence', files=[{'path': 'evidence/review.md',
        'content': 'Source reviewed. Live checks NOT RUN; approval required.'}],
        instructions='Review prerequisites with the human.', verification=['Run only the approved isolated check.'])])
    database = tmp_path / 'evidence.sqlite'
    with TestClient(create_app(database, ai_model=model)) as client:
        bounty = post(client, work_type='verification')
        with client.app.state.service.db.engine.connect() as c:
            transactions = one(c, 'SELECT COUNT(*) AS n FROM gold_transactions')['n']
        assert write(client, f'/bounties/{bounty}/ai/start', {}).status_code == 200
        task = client.get(f'/api/v1/bounties/{bounty}').json()
        assert task['work_type'] == 'verification' and task['status'] == 'delivered'
        assert task['ai_run']['status'] == 'ready' and task['completed_by'] is None
        response = client.get(task['ai_run']['download_url'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert set(archive.namelist()) == {'START_HERE.md', 'bounty.json', 'history.json', 'evidence/review.md'}
            assert 'No tests were executed' in archive.read('START_HERE.md').decode()
            assert json.loads(archive.read('bounty.json'))['work_type'] == 'verification'
        assert client.get(task['ai_run']['download_url']).content == response.content
        with zipfile.ZipFile(io.BytesIO(client.get(f'/api/v1/bounties/{bounty}/artifacts/download').content)) as archive:
            assert 'evidence.zip' in archive.namelist() and 'fix.zip' not in archive.namelist()
        assert len(client.get(f'/api/v1/bounties/{bounty}/lineage').json()['items']) == 1
        with client.app.state.service.db.engine.connect() as c:
            assert one(c, 'SELECT COUNT(*) AS n FROM gold_transactions')['n'] == transactions
        assert write(client, f'/bounties/{bounty}/ai/complete', {'evidence': 'Unapproved'}, 'nate').status_code == 403
        verified_proof(client, bounty)
        assert write(client, f'/bounties/{bounty}/ai/complete', {'evidence': 'Human reviewed the actual isolated results.'}).json()['phase'] == 'Closed'
    with TestClient(create_app(database, ai_model=model)) as client:
        assert get_run(client, bounty)['status'] == 'completed'
        assert client.get(f'/api/v1/bounties/{bounty}/ai/artifact').content != b''


@pytest.mark.parametrize('level,kind,action,path', [
    ('HIGH', 'verification', 'evidence', 'evidence/report.md'),
    ('MEDIUM', 'verification', 'evidence', 'evidence/report.md'),
    ('LOW', 'implementation', 'evidence', 'evidence/report.md'),
    ('LOW', 'verification', 'deliver', 'calc.py'),
    ('LOW', 'verification', 'evidence', 'evidence/script.py'),
    ('LOW', 'verification', 'evidence', 'calc.py'),
    ('LOW', 'verification', 'evidence', 'evidence/../outside.md'),
])
def test_wrong_outcomes_cannot_publish_artifacts(tmp_path, level, kind, action, path):
    model = FakeLuna([decision(action, files=[{'path': path, 'content': 'No execution'}], instructions='Review')])
    with TestClient(create_app(tmp_path / 'invalid.sqlite', ai_model=model)) as client:
        bounty = post(client, level, kind)
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        assert get_run(client, bounty)['status'] == 'failed'
        assert client.get(f'/api/v1/bounties/{bounty}/ai/artifact').status_code == 409


@pytest.mark.parametrize('level,count', [('HIGH', 2), ('HIGH', 3), ('HIGH', 4), ('MEDIUM', 2), ('MEDIUM', 3), ('MEDIUM', 4)])
def test_grounded_high_and_medium_proposals_do_not_force_three(tmp_path, level, count):
    child_level = 'HIGH' if level == 'HIGH' else 'LOW'
    proposals = [{'title': f'Child {i}', 'goal': 'Bounded', 'criteria': ['Proof'], 'complexity': child_level} for i in range(count)]
    with TestClient(create_app(tmp_path / 'count.sqlite', ai_model=FakeLuna([decision('followups', proposals=proposals)]))) as client:
        bounty = post(client, level)
        write(client, f'/bounties/{bounty}/ai/start', {})
        assert get_run(client, bounty)['status'] == 'followups_pending'
        assert len(client.get(f'/api/v1/bounties/{bounty}/lineage').json()['items']) == 1
        assert write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': list(range(count - 1))}).status_code == 422
        assert write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': list(range(count))}).status_code == 200
        assert len(client.get(f'/api/v1/bounties/{bounty}/lineage').json()['items']) == count + 1


def test_three_typed_low_proposals_preserve_coverage_kind_and_human_approval(tmp_path):
    proposals = [{'title': f'Outcome {i}', 'goal': 'One bounded outcome', 'criteria': ['Observed proof'],
                  'complexity': 'LOW', 'work_type': 'verification' if i == 2 else 'implementation',
                  'parent_criteria': [i]} for i in range(3)]
    with TestClient(create_app(tmp_path / 'types.sqlite', ai_model=FakeLuna([decision('followups', proposals=proposals)]))) as client:
        bounty = post(client, 'MEDIUM', criteria=['First', 'Second', 'Third'])
        write(client, f'/bounties/{bounty}/ai/start', {})
        assert get_run(client, bounty)['status'] == 'followups_pending'
        assert write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': [0, 1]}).status_code == 422
        assert write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': [0, 1, 2]}).json()['status'] == 'decomposed'
        items = client.get(f'/api/v1/bounties/{bounty}/lineage').json()['items']
        children = [client.get('/api/v1/bounties/' + item['id']).json() for item in items if item['parent_id'] == bounty]
        assert len(children) == 3
        assert sorted(child['work_type'] for child in children) == ['implementation', 'implementation', 'verification']
        assert sorted(child['events'][0]['data']['parent_criteria'] for child in children) == [[0], [1], [2]]


@pytest.mark.parametrize('mutation', ['missing_mapping', 'out_of_range', 'uncovered', 'no_reason', 'duplicate_titles'])
def test_trio_requires_explanation_and_valid_complete_parent_coverage(tmp_path, mutation):
    proposals = [{'title': f'Outcome {i}', 'goal': 'Bounded', 'criteria': ['Proof'], 'complexity': 'LOW',
                  'parent_criteria': [i]} for i in range(3)]
    why = 'Three independent responsibilities satisfy the three parent criteria.'
    if mutation == 'missing_mapping':
        proposals[0]['parent_criteria'] = []
    elif mutation == 'out_of_range':
        proposals[0]['parent_criteria'] = [3]
    elif mutation == 'uncovered':
        proposals[2]['parent_criteria'] = [1]
    elif mutation == 'no_reason':
        why = ''
    else:
        proposals[2]['title'] = proposals[0]['title']
    model = FakeLuna([decision('followups', proposals=proposals, why_three=why)])
    with TestClient(create_app(tmp_path / 'coverage.sqlite', ai_model=model)) as client:
        bounty = post(client, 'MEDIUM', criteria=['First', 'Second', 'Third'])
        write(client, f'/bounties/{bounty}/ai/start', {})
        assert get_run(client, bounty)['status'] == 'failed'
        assert len(client.get(f'/api/v1/bounties/{bounty}/lineage').json()['items']) == 1


def test_old_or_tampered_proposals_are_revalidated_before_creation(tmp_path):
    proposals = [{'title': f'Outcome {i}', 'goal': 'Bounded', 'criteria': ['Proof'], 'complexity': 'MEDIUM'} for i in range(3)]
    with TestClient(create_app(tmp_path / 'confirm.sqlite', ai_model=FakeLuna([decision('followups', proposals=proposals)]))) as client:
        bounty = post(client, 'HIGH')
        write(client, f'/bounties/{bounty}/ai/start', {})
        with client.app.state.service.db.write() as c:
            row = client.app.state.service.ai.record(c, bounty)
            del row['data']['result']['why_three']
            client.app.state.service.ai.save(c, row)
        response = write(client, f'/bounties/{bounty}/ai/confirm-followups', {'indices': [0, 1, 2]})
        assert response.status_code == 422
        assert len(client.get(f'/api/v1/bounties/{bounty}/lineage').json()['items']) == 1
