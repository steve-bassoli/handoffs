from concurrent.futures import ThreadPoolExecutor

from conftest import post_bounty, write


def test_competing_claims_and_wrong_actor(client):
    bounty = post_bounty(client).json()['id']
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda user: write(client, f'/bounties/{bounty}/take', user=user), ['nate', 'will']))
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json()['claimant'] for r in results if r.status_code == 200)
    assert write(client, f'/bounties/{bounty}/status', {'status': 'blocked'}, 'steve').status_code == 403
    assert write(client, f'/bounties/{bounty}/status', {'status': 'blocked', 'note': 'Waiting'}, winner).json()['status'] == 'blocked'
    assert write(client, f'/bounties/{bounty}/status', {'status': 'working'}, winner).json()['status'] == 'working'


def test_self_claim_and_target(client):
    bounty = post_bounty(client).json()['id']
    assert write(client, f'/bounties/{bounty}/take').status_code == 403
