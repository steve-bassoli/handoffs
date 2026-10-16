from fastapi.testclient import TestClient

from app.main import create_app
from conftest import post_bounty, write


class NotVerified:
    def verify(self, url):
        return {'verified': False, 'simulated': True, 'pr_url': url}


def test_failed_verification_does_not_pay(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite', verifier=NotVerified())) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/take', user='nate')
        result = write(client, f'/bounties/{bounty}/deliveries', {'pr_url': 'https://github.com/example/source/pull/1', 'evidence': 'Unverified'}, 'nate')
        assert result.json()['status'] == 'delivered'
        assert write(client, f'/bounties/{bounty}/settle', user='nate').status_code == 409
        assert client.get('/api/v1/me/stats', headers={'X-Demo-User': 'nate'}).json()['available_gold'] == 1000
        assert client.get('/api/v1/me/stats').json()['reserved_gold'] == 150
