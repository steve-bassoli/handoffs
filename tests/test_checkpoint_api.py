import pytest

from app import mcp_server
from conftest import post_task, write


def test_checkpoint_api_idempotency_and_claim_are_separate(client):
    task = post_task(client).json()
    write(client, f"/tasks/{task['id']}/take")
    body = {'notes': 'Done: bounded draft. Remaining: review. Evidence: original artifacts.'}
    path = f"/tasks/{task['id']}/checkpoint"
    first = write(client, path, body, key='save-progress')
    assert first.status_code == 200, first.text
    result = first.json()
    assert result['status'] == 'open' and result['claimant'] is None and result['ai_run'] is None
    assert result['checkpoint']['notes'] == body['notes']
    assert write(client, path, body, key='save-progress').json() == result
    assert write(client, path, body, key='second-checkpoint').status_code == 409
    assert write(client, path, {'notes': 'Different'}, key='save-progress').status_code == 409
    assert client.get('/api/v1/tasks/' + task['id']).json()['continuation_id'] == result['id']


@pytest.mark.parametrize('body', [{}, {'notes': ''}, {'notes': ' '}, {'notes': 'x' * 30001},
                                  {'notes': 'saved', 'accepted': True}])
def test_checkpoint_requires_focused_notes_and_cannot_accept_proof(client, body):
    task = post_task(client).json()
    assert write(client, f"/tasks/{task['id']}/checkpoint", body).status_code == 422
    assert client.get('/api/v1/tasks/' + task['id']).json()['status'] == 'open'


def test_checkpoint_manual_mode_requires_real_user_directed_intent(client):
    task = post_task(client).json()
    path = '/api/v1/tasks/' + task['id'] + '/checkpoint'
    headers = {'X-Demo-User': 'steve', 'X-Automation': 'fixture-campaign', 'Idempotency-Key': 'autonomous-save'}
    response = client.post(path, json={'notes': 'Save'}, headers=headers)
    assert response.status_code == 403
    headers.update({'X-Action-Intent': 'user-directed', 'Idempotency-Key': 'directed-save'})
    response = client.post(path, json={'notes': 'Save at explicit human request'}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['events'][0]['data']['via'] == 'fixture-campaign'


def test_mcp_checkpoint_is_one_explicit_write_without_claim_or_provider(monkeypatch):
    seen = []
    def request(method, path, **kwargs):
        seen.append((method, path, kwargs))
        return {'id': 'continuation', 'status': 'open'}
    monkeypatch.setattr(mcp_server, 'request', request)
    result = mcp_server.checkpoint_task('task/id', 'Done and remaining notes', 'stable-operation')
    assert result['status'] == 'open'
    assert seen == [('POST', '/tasks/task%2Fid/checkpoint',
                     {'body': {'notes': 'Done and remaining notes'}, 'operation_id': 'stable-operation'})]
