from conftest import post_bounty, verified_proof, write

from fastapi.testclient import TestClient
from app.main import create_app


def test_earn_and_repost_with_no_double_payment(client):
    bounty = post_bounty(client).json()['id']
    assert write(client, f'/bounties/{bounty}/take', user='nate').status_code == 200
    verified_proof(client, bounty, 'nate')
    payload = {'pr_url': 'https://github.com/example/source/pull/1', 'evidence': 'Criteria demonstrated'}
    result = write(client, f'/bounties/{bounty}/deliveries', payload, 'nate', 'delivery-once')
    assert result.status_code == 200
    assert result.json()['status'] == 'settled'
    assert result.json()['deliveries'][0]['simulated'] == 1
    assert write(client, f'/bounties/{bounty}/deliveries', payload, 'nate', 'delivery-once').json() == result.json()
    assert write(client, f'/bounties/{bounty}/deliveries', payload, 'nate').status_code == 409
    assert write(client, f'/bounties/{bounty}/settle', user='nate').status_code == 409
    assert client.get('/api/v1/me/stats', headers={'X-Demo-User': 'nate'}).json()['available_gold'] == 1150
    assert post_bounty(client, gold=1100, user='nate').status_code == 200
    stats = client.get('/api/v1/me/stats', headers={'X-Demo-User': 'nate'}).json()
    assert (stats['available_gold'], stats['reserved_gold']) == (50, 1100)
    with client.app.state.service.db.engine.connect() as c:
        assert c.exec_driver_sql('SELECT SUM(amount) FROM gold_entries').scalar_one() == 0
        assert c.exec_driver_sql("SELECT -SUM(amount) FROM gold_entries WHERE account_id='issuance'").scalar_one() == 2000
    review = write(client, f'/bounties/{bounty}/reviews', {'decision': 'accepted', 'note': 'Reviewed the criteria'})
    assert review.status_code == 200 and review.json()['status'] == 'settled'
    assert review.json()['deliveries'] == result.json()['deliveries']


def test_cancel_refunds_once_and_never_after_claim(client):
    bounty = post_bounty(client).json()['id']
    assert write(client, f'/bounties/{bounty}/cancel', key='refund').json()['status'] == 'cancelled'
    assert write(client, f'/bounties/{bounty}/cancel', key='refund').status_code == 200
    assert write(client, f'/bounties/{bounty}/cancel').status_code == 409
    assert client.get('/api/v1/me/stats').json()['available_gold'] == 1000
    another = post_bounty(client).json()['id']
    write(client, f'/bounties/{another}/take', user='nate')
    assert write(client, f'/bounties/{another}/cancel').status_code == 409
    assert write(client, f'/bounties/{another}/reviews', {'decision': 'accepted', 'note': 'Not delivered'}).status_code == 409


def test_cycle_survives_service_restart(tmp_path):
    path = tmp_path / 'persistent.sqlite'
    with TestClient(create_app(path)) as first:
        bounty = post_bounty(first).json()['id']
        write(first, f'/bounties/{bounty}/take', user='nate')
        verified_proof(first, bounty, 'nate')
    with TestClient(create_app(path)) as restarted:
        result = write(restarted, f'/bounties/{bounty}/deliveries',
                       {'pr_url': 'https://github.com/example/source/pull/3', 'evidence': 'After restart'}, 'nate')
        assert result.json()['status'] == 'settled'
        assert restarted.get('/api/v1/me/stats').json()['available_gold'] == 850
        assert restarted.get('/api/v1/me/stats', headers={'X-Demo-User': 'nate'}).json()['available_gold'] == 1150
