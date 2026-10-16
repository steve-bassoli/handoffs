import pytest
import time
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite')) as client:
        yield client


def write(client, path, data=None, user='steve', key=None):
    from uuid import uuid4
    return client.post('/api/v1' + path, json=data or {},
                       headers={'X-Demo-User': user, 'Idempotency-Key': key or str(uuid4())})


def post_bounty(client, gold=150, user='steve', key=None):
    return write(client, '/bounties', {'title': 'Prove a useful change', 'goal': 'Deliver a PR',
                 'criteria': ['The change works'], 'gold': gold, 'complexity': 'LOW'}, user, key)


class FixtureProofReviewer:
    def review(self, task, proof):
        return {'verdict': 'pass', 'reason': 'Synthetic test reviewer only, not actual model judgment',
                'criteria': [{'index': index, 'verdict': 'pass', 'reason': 'Isolated fixture'}
                             for index in range(len(task['criteria']))], 'reviewer': 'test-fixture'}


def verified_proof(client, bounty, user='steve'):
    """Exercise the real proof routes using an explicitly isolated fake reviewer."""
    from test_proofs import upload
    if hasattr(client, 'app'):
        client.app.state.service.proofs.reviewer = FixtureProofReviewer()
    task = client.get('/api/v1/bounties/' + bounty).json()
    value = task.get('profile') or {'validation_scope': 'SIM', 'migration_stage': 'WRAP',
        'baseline_revision': 'fixture-baseline', 'candidate_revision': 'fixture-candidate', 'environment': 'isolated unit fixture'}
    assert write(client, f'/bounties/{bounty}/profile', value, user).status_code == 200
    assert write(client, f'/bounties/{bounty}/proofs', upload('SYNTHETIC test proof; no live Watson execution.'), user).status_code == 200
    assert write(client, f'/bounties/{bounty}/proof-review', user=user).status_code == 200
    for _ in range(100):
        task = client.get('/api/v1/bounties/' + bounty).json()
        if task['proof']['review']['verdict'] not in ('queued', 'running'):
            break
        time.sleep(0.01)
    assert task['proof']['review']['verdict'] == 'pass'
    if task['complexity'] == 'LOW':
        assert write(client, f'/bounties/{bounty}/proof-human', {'accepted': True, 'note': 'Explicit test human verification'}, user).status_code == 200
