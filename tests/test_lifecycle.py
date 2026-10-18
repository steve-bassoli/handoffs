from concurrent.futures import ThreadPoolExecutor

from conftest import post_task, write


def test_competing_claims_and_wrong_actor(client):
    task = post_task(client).json()['id']
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda user: write(client, f'/tasks/{task}/take', user=user), ['nate', 'will']))
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json()['claimant'] for r in results if r.status_code == 200)
    assert write(client, f'/tasks/{task}/status', {'status': 'blocked'}, 'steve').status_code == 403
    assert write(client, f'/tasks/{task}/status', {'status': 'blocked', 'note': 'Waiting'}, winner).json()['status'] == 'blocked'
    assert write(client, f'/tasks/{task}/status', {'status': 'working'}, winner).json()['status'] == 'working'


def test_creator_can_claim_and_target_is_respected(client):
    task = post_task(client).json()['id']
    claimed = write(client, f'/tasks/{task}/take')
    assert claimed.status_code == 200
    assert claimed.json()['claimant'] == 'steve'
    assert write(client, f'/tasks/{task}/take', user='nate').status_code == 409
    targeted = write(client, '/tasks', {'title': 'Targeted work', 'goal': 'Deliver',
        'criteria': ['Works'], 'gold': 10, 'target': 'nate'}).json()['id']
    assert write(client, f'/tasks/{targeted}/take').status_code == 403
    assert write(client, f'/tasks/{targeted}/take', user='will').status_code == 403
    assert write(client, f'/tasks/{targeted}/take', user='nate').status_code == 200
