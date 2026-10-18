import pytest

from conftest import post_task, write


PAYLOAD = {
    'baseline': 'fixture-base', 'candidate': 'fixture-patch',
    'environment': 'isolated synthetic fixture',
    'evidence': 'Human explicitly accepts this synthetic fixture outcome; no live execution.',
}


def claimed(client, complexity='LOW'):
    if complexity == 'LOW':
        response = post_task(client, gold=10)
    else:
        response = write(client, '/tasks', {
            'title': 'Fixture task', 'goal': 'Finish', 'criteria': ['Works'],
            'gold': 10, 'complexity': complexity,
        })
    assert response.status_code == 200
    task_id = response.json()['id']
    assert write(client, f'/tasks/{task_id}/take', user='nate').status_code == 200
    return task_id


@pytest.mark.parametrize('complexity', ['LOW', 'MEDIUM'])
def test_close_human_success(client, complexity):
    task_id = claimed(client, complexity)
    response = write(client, f'/tasks/{task_id}/close-human', PAYLOAD, 'nate')
    assert response.status_code == 200, response.text
    task = response.json()
    assert task['phase'] == 'Closed'
    assert task['status'] == 'settled'
    assert task['completed_by'] == 'nate'
    assert task['profile']['baseline_revision'] == PAYLOAD['baseline']
    assert task['profile']['candidate_revision'] == PAYLOAD['candidate']
    assert task['proof']['accepted']
    assert task['proof']['verification_method'] == 'human-only'
    assert client.get(task['proof']['download_url']).content == PAYLOAD['evidence'].encode()
    assert [e['kind'] for e in task['events']][-4:] == [
        'profile_recorded', 'proof_attached', 'proof_human_reviewed', 'proof_completed']
    assert client.get('/api/v1/me/stats').json()['reserved_gold'] == 0


def test_close_human_high_refusal_rolls_back(client):
    task_id = claimed(client, 'HIGH')
    before = client.get('/api/v1/tasks/' + task_id).json()
    response = write(client, f'/tasks/{task_id}/close-human', PAYLOAD, 'nate')
    assert response.status_code == 409
    assert client.get('/api/v1/tasks/' + task_id).json() == before
    assert client.get('/api/v1/me/stats').json()['reserved_gold'] == 10


def test_close_human_retry_returns_same_receipt_without_second_payment(client):
    task_id = claimed(client)
    path = f'/tasks/{task_id}/close-human'
    first = write(client, path, PAYLOAD, 'nate', 'close-once')
    assert first.status_code == 200, first.text
    after = client.get('/api/v1/tasks/' + task_id).json()
    stats = client.get('/api/v1/me/stats', headers={'X-Demo-User': 'nate'}).json()
    retry = write(client, path, PAYLOAD, 'nate', 'close-once')
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert client.get('/api/v1/tasks/' + task_id).json() == after
    assert client.get('/api/v1/me/stats', headers={'X-Demo-User': 'nate'}).json() == stats
    assert write(client, path, {**PAYLOAD, 'candidate': 'different'},
                 'nate', 'close-once').status_code == 409


def test_close_human_requires_existing_claimant(client):
    task_id = claimed(client)
    before = client.get('/api/v1/tasks/' + task_id).json()
    assert write(client, f'/tasks/{task_id}/close-human', PAYLOAD).status_code == 403
    assert client.get('/api/v1/tasks/' + task_id).json() == before
    unclaimed = post_task(client, gold=10).json()['id']
    assert write(client, f'/tasks/{unclaimed}/close-human', PAYLOAD).status_code == 403
    assert client.get('/api/v1/tasks/' + unclaimed).json()['claimant'] is None
