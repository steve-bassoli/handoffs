import pytest
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
