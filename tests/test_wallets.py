from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def test_demo_users_are_distinct(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite')) as client:
        assert client.get('/api/v1/me', headers={'X-Demo-User': 'nate'}).json()['id'] == 'nate'
        assert client.get('/api/v1/me', headers={'X-Demo-User': 'steve'}).json()['id'] == 'steve'
        assert client.get('/api/v1/me').json()['simulated_identity'] is True
        assert client.get('/api/v1/me', headers={'X-Demo-User': 'unknown'}).status_code == 401


def test_grants_once_rollover_and_current_month_catchup(tmp_path):
    path = tmp_path / 'test.sqlite'
    current = [datetime(2026, 10, 15, tzinfo=timezone.utc)]
    for _ in range(2):
        with TestClient(create_app(path, clock=lambda: current[0])) as client:
            for _ in range(2):
                assert client.get('/api/v1/me/stats').json()['available_gold'] == 1000
    current[0] = datetime(2027, 1, 2, tzinfo=timezone.utc)
    with TestClient(create_app(path, clock=lambda: current[0])) as client:
        stats = client.get('/api/v1/me/stats').json()
        assert stats['available_gold'] == 2000
        assert stats['month'] == '2027-01'
        assert stats['next_allocation'].startswith('2027-02-01')
        assert len(client.get('/api/v1/me/transactions').json()) == 2
