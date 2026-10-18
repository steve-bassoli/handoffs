from fastapi.testclient import TestClient

from app.main import create_app
from conftest import post_task, write


class NotVerified:
    def verify(self, url):
        return {'verified': False, 'simulated': True, 'pr_url': url}


def test_failed_verification_does_not_pay(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite', verifier=NotVerified())) as client:
        task = post_task(client).json()['id']
        write(client, f'/tasks/{task}/take', user='nate')
        result = write(client, f'/tasks/{task}/deliveries', {'pr_url': 'https://github.com/example/source/pull/1', 'evidence': 'Unverified'}, 'nate')
        assert result.json()['status'] == 'delivered'
        assert write(client, f'/tasks/{task}/settle', user='nate').status_code == 409
        assert client.get('/api/v1/me/stats', headers={'X-Demo-User': 'nate'}).json()['available_gold'] == 1000
        assert client.get('/api/v1/me/stats').json()['reserved_gold'] == 150
