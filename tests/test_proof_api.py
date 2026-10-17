import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FixtureProofReviewer, post_bounty, verified_proof, write
from test_ai import FakeLuna, decision
from test_proofs import upload


def claimed(client):
    bounty = post_bounty(client, gold=10).json()['id']
    assert write(client, f'/bounties/{bounty}/take', user='nate').status_code == 200
    return bounty


def test_all_completion_routes_reject_unreviewed_proof_without_payment(client):
    bounty = claimed(client)
    before = client.get('/api/v1/me/stats').json()['reserved_gold']
    assert write(client, f'/bounties/{bounty}/complete', {'note': 'Just trust me'}, 'nate').status_code == 409
    assert write(client, f'/bounties/{bounty}/deliveries', {'pr_url': 'https://github.com/example/repo/pull/1',
        'evidence': 'A PR is not behavioral proof'}, 'nate').status_code == 409
    assert client.get('/api/v1/me/stats').json()['reserved_gold'] == before
    assert not client.get('/api/v1/bounties/' + bounty).json()['deliveries']


def test_one_proof_requires_ai_and_human_and_survives_as_a_direct_artifact(client):
    bounty = claimed(client)
    verified_proof(client, bounty, 'nate')
    task = client.get('/api/v1/bounties/' + bounty).json()
    proof = task['proof']
    assert proof['accepted'] and task['phase'] == 'Claimed'
    assert write(client, f'/bounties/{bounty}/complete', {'note': 'Wrong actor'}, 'will').status_code == 403
    closed = write(client, f'/bounties/{bounty}/complete', {'note': 'Observed the fixture outcome'}, 'nate').json()
    assert closed['phase'] == 'Closed' and closed['disposition'] == 'completed'
    assert closed['completed_by'] == 'nate'
    assert client.get('/api/v1/me/stats').json()['reserved_gold'] == 0
    assert write(client, f'/bounties/{bounty}/complete', {'note': 'No second payout'}, 'nate').status_code == 409
    assert client.get(proof['download_url']).content.startswith(b'SYNTHETIC')
    assert write(client, f'/bounties/{bounty}/profile', task['profile'], 'nate').status_code == 409
    with zipfile.ZipFile(io.BytesIO(client.get(f'/api/v1/bounties/{bounty}/artifacts/download').content)) as archive:
        assert any(path.startswith('proofs/') for path in archive.namelist())


def test_revision_drift_invalidates_acceptance_and_preserves_old_proof(client):
    bounty = claimed(client)
    verified_proof(client, bounty, 'nate')
    before = client.get('/api/v1/bounties/' + bounty).json()
    changed = {**before['profile'], 'candidate_revision': 'new-fixture-revision'}
    assert write(client, f'/bounties/{bounty}/profile', changed, 'nate').status_code == 200
    assert not client.get('/api/v1/bounties/' + bounty).json()['proof']['fresh']
    assert write(client, f'/bounties/{bounty}/complete', {'note': 'Old approval'}, 'nate').status_code == 409
    assert write(client, f'/bounties/{bounty}/proof-review', user='nate').status_code == 409
    verified_proof(client, bounty, 'nate')
    after = client.get('/api/v1/bounties/' + bounty).json()
    assert len(after['proof_history']) == 2 and after['proof']['proof_id'] != before['proof']['proof_id']
    assert client.get(before['proof']['download_url']).content == client.get(after['proof']['download_url']).content


def test_inconclusive_reviewer_cannot_be_overridden_by_a_human_note(tmp_path):
    class Inconclusive(FixtureProofReviewer):
        def review(self, task, proof):
            value = super().review(task, proof)
            value['criteria'][0]['verdict'] = 'inconclusive'
            return value
    with TestClient(create_app(tmp_path / 'inconclusive.sqlite', proof_reviewer=Inconclusive())) as client:
        bounty = claimed(client)
        write(client, f'/bounties/{bounty}/profile', {'baseline_revision': 'base', 'candidate_revision': 'patch', 'environment': 'fixture'}, 'nate')
        write(client, f'/bounties/{bounty}/proofs', upload(), 'nate')
        write(client, f'/bounties/{bounty}/proof-review', user='nate')
        assert client.get('/api/v1/bounties/' + bounty).json()['proof']['review']['verdict'] == 'inconclusive'
        assert write(client, f'/bounties/{bounty}/proof-human', {'accepted': True, 'note': 'Ignore missing proof'}, 'nate').status_code == 409


@pytest.mark.parametrize('count', [2, 3, 4])
def test_verified_children_do_not_close_a_parent_without_integrated_proof(tmp_path, count):
    proposals = [{'title': f'Verify outcome {index}', 'goal': 'Bounded observed outcome', 'criteria': ['Observed'],
                  'complexity': 'LOW', 'work_type': 'verification'} for index in range(count)]
    with TestClient(create_app(tmp_path / 'parent.sqlite', ai_model=FakeLuna([decision('followups', proposals=proposals)]))) as client:
        parent = write(client, '/bounties', {'title': 'Integrated outcome', 'goal': 'Combine all outcomes',
            'criteria': ['Integrated acceptance'], 'complexity': 'MEDIUM', 'gold': 10}).json()['id']
        write(client, f'/bounties/{parent}/ai/start')
        write(client, f'/bounties/{parent}/ai/confirm-followups', {'indices': list(range(count))})
        assert write(client, f'/bounties/{parent}/complete', {'note': 'Children exist'}).status_code == 409
        children = client.get('/api/v1/bounties/' + parent).json()['required_children']
        for child in children:
            write(client, f'/bounties/{child}/take', user='nate')
            verified_proof(client, child, 'nate')
            assert write(client, f'/bounties/{child}/complete', {'note': 'Fixture verified'}, 'nate').status_code == 200
        assert write(client, f'/bounties/{parent}/complete', {'note': 'Children closed'}).status_code == 409
        verified_proof(client, parent)
        assert write(client, f'/bounties/{parent}/proof-human', {'accepted': True, 'note': 'No extra parent human gate'}).status_code == 409
        assert write(client, f'/bounties/{parent}/complete', {'note': 'Separate integrated fixture proof'}).json()['phase'] == 'Closed'
