from concurrent.futures import ThreadPoolExecutor

from conftest import post_task


def test_funding_retry_and_insufficient_balance(client):
    first = post_task(client, key='once')
    assert first.status_code == 200
    assert post_task(client, key='once').json()['id'] == first.json()['id']
    stats = client.get('/api/v1/me/stats').json()
    assert (stats['available_gold'], stats['reserved_gold']) == (850, 150)
    assert post_task(client, gold=900).status_code == 409
    assert post_task(client, gold=100, key='once').status_code == 409
    listing = client.get('/api/v1/tasks').json()['items']
    assert len(listing) == 1 and 'goal' not in listing[0]
    assert client.get('/api/v1/tasks/' + first.json()['id']).json()['criteria'] == ['The change works']


def test_concurrent_funding_cannot_overspend(client):
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda _: post_task(client, gold=700).status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert client.get('/api/v1/me/stats').json()['available_gold'] == 300
