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


def test_creator_can_complete_own_work_once_after_verified_proof(client):
    before = client.get('/api/v1/me/stats').json()['available_gold']
    bounty = post_bounty(client, gold=10).json()['id']
    assert write(client, f'/bounties/{bounty}/take').status_code == 200
    assert write(client, f'/bounties/{bounty}/complete', {'note': 'No proof yet'}).status_code == 409
    assert client.get('/api/v1/me/stats').json()['reserved_gold'] == 10
    verified_proof(client, bounty)
    completed = write(client, f'/bounties/{bounty}/complete', {'note': 'Verified my work'})
    assert completed.status_code == 200
    assert completed.json()['phase'] == 'Closed'
    assert completed.json()['completed_by'] == 'steve'
    stats = client.get('/api/v1/me/stats').json()
    assert stats['available_gold'] == before
    assert stats['reserved_gold'] == 0
    assert write(client, f'/bounties/{bounty}/complete', {'note': 'Repeated'}).status_code == 409
    assert client.get('/api/v1/me/stats').json()['available_gold'] == before


@pytest.mark.parametrize('request_review', [False, True])
def test_user_directed_manual_completion_needs_no_provider_but_retains_evidence(client, monkeypatch, request_review):
    from uuid import uuid4
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    def directed(path, data=None):
        return client.post('/api/v1' + path, json=data or {}, headers={
            'X-Demo-User': 'steve', 'Idempotency-Key': str(uuid4()),
            'X-Automation': 'codex', 'X-Action-Intent': 'user-directed'})

    before = client.get('/api/v1/me/stats').json()['available_gold']
    task = directed('/bounties', {'title': 'My task', 'goal': 'Finish', 'criteria': ['Works'],
        'gold': 10, 'complexity': 'LOW'}).json()['id']
    assert directed(f'/bounties/{task}/take').status_code == 200
    assert directed(f'/bounties/{task}/profile', {'baseline_revision': 'base',
        'candidate_revision': 'patch', 'environment': 'offline fixture'}).status_code == 200
    decision = {'accepted': True, 'review_basis': 'human-only', 'note': 'User explicitly verified fixture outcome'}
    assert directed(f'/bounties/{task}/proof-human', decision).status_code == 409
    assert directed(f'/bounties/{task}/proofs', upload()).status_code == 200
    if request_review:
        assert directed(f'/bounties/{task}/proof-review').status_code == 200
    verified = directed(f'/bounties/{task}/proof-human', decision)
    assert verified.status_code == 200
    proof = verified.json()['proof']
    assert proof['accepted'] and proof['verification_method'] == 'human-only'
    assert proof['review'] is None if not request_review else proof['review']['verdict'] == 'inconclusive'
    closed = directed(f'/bounties/{task}/complete', {'note': 'User-directed closure'})
    assert closed.status_code == 200
    assert closed.json()['completed_by'] == 'steve' and closed.json()['phase'] == 'Closed'
    assert closed.json()['events'][-1]['data']['verification_method'] == 'human-only'
    assert client.get('/api/v1/me/stats').json()['available_gold'] == before
    assert client.get('/api/v1/automation-mode').json()['mode'] == 'manual'
    assert directed(f'/bounties/{task}/complete', {'note': 'Duplicate'}).status_code == 409


def test_human_only_verification_cannot_override_failure_or_survive_changed_context(client):
    task = claimed(client)
    write(client, f'/bounties/{task}/profile', {'baseline_revision': 'base', 'candidate_revision': 'patch', 'environment': 'fixture'}, 'nate')
    write(client, f'/bounties/{task}/proofs', upload(), 'nate')
    decision = {'accepted': True, 'review_basis': 'human-only', 'note': 'Human verified evidence'}
    assert write(client, f'/bounties/{task}/proof-human', decision, 'nate').status_code == 200
    write(client, f'/bounties/{task}/profile', {'baseline_revision': 'base', 'candidate_revision': 'changed', 'environment': 'fixture'}, 'nate')
    assert write(client, f'/bounties/{task}/complete', {'note': 'Stale proof'}, 'nate').status_code == 409
    write(client, f'/bounties/{task}/proofs', upload(), 'nate')

    class Failed(FixtureProofReviewer):
        def review(self, task, proof):
            return {'verdict': 'fail', 'reason': 'Observed failure',
                'criteria': [{'index': 0, 'verdict': 'fail', 'reason': 'Observed failure'}]}

    client.app.state.service.proofs.reviewer = Failed()
    write(client, f'/bounties/{task}/proof-review', user='nate')
    assert write(client, f'/bounties/{task}/proof-human', decision, 'nate').status_code == 409


def test_autonomous_agent_cannot_assert_human_decision_and_new_review_invalidates_it(client):
    from app.automation_mode import set_mode
    task = claimed(client)
    write(client, f'/bounties/{task}/profile', {'baseline_revision': 'base', 'candidate_revision': 'patch', 'environment': 'fixture'}, 'nate')
    write(client, f'/bounties/{task}/proofs', upload(), 'nate')
    set_mode('light', 'steve', 'Isolated autonomy check', client.app.state.mode_path)
    decision = {'accepted': True, 'review_basis': 'human-only', 'note': 'Explicit evidence review'}
    headers = {'X-Demo-User': 'nate', 'X-Automation': 'bob',
        'X-Action-Intent': 'autonomous', 'Idempotency-Key': 'no-inferred-human'}
    assert client.post(f'/api/v1/bounties/{task}/proof-human', json=decision, headers=headers).status_code == 403
    headers.pop('X-Automation')
    headers['Idempotency-Key'] = 'no-unattributed-autonomous-human'
    assert client.post(f'/api/v1/bounties/{task}/proof-human', json=decision, headers=headers).status_code == 403
    assert write(client, f'/bounties/{task}/proof-human', decision, 'nate').json()['proof']['accepted']
    # Queue without dispatching a paid call; a new review requires a fresh decision.
    queued = client.app.state.service.execute('nate', 'new-review', 'ai_proof_queue', {'id': task})
    assert queued['proof']['review']['verdict'] == 'queued'
    assert not queued['proof']['accepted']
    assert write(client, f'/bounties/{task}/proof-human', decision, 'nate').status_code == 409
    assert write(client, f'/bounties/{task}/complete', {'note': 'Review pending'}, 'nate').status_code == 409


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
        for index, child in enumerate(children):
            worker = 'steve' if index == 0 else 'nate'
            assert write(client, f'/bounties/{child}/take', user=worker).status_code == 200
            verified_proof(client, child, worker)
            assert write(client, f'/bounties/{child}/complete', {'note': 'Fixture verified'}, worker).status_code == 200
        assert write(client, f'/bounties/{parent}/complete', {'note': 'Children closed'}).status_code == 409
        verified_proof(client, parent)
        assert write(client, f'/bounties/{parent}/proof-human', {'accepted': True, 'note': 'No extra parent human gate'}).status_code == 409
        assert write(client, f'/bounties/{parent}/complete', {'note': 'Separate integrated fixture proof'}).json()['phase'] == 'Closed'
