import pytest

from conftest import post_task, write
from app.services import RuleError


FIELDS = ('title', 'goal', 'criteria', 'complexity', 'work_type',
          'context_links', 'repository', 'target', 'gold')


def body(task, **changes):
    return {**{field: task[field] for field in FIELDS}, **changes}


def fetch(client, task_id):
    return client.get('/api/v1/tasks/' + task_id).json()


def balances(client, task_id):
    service = client.app.state.service
    with service.db.engine.connect() as c:
        return (service.balance(c, 'wallet:steve'), service.balance(c, 'escrow:' + task_id))


def test_edit_fields_identity_and_append_only_audit(client):
    original = post_task(client).json()
    task_id = original['id']
    payload = body(original, title='Revised title', goal='Revised goal',
                   criteria=['First check', 'Second check'], complexity='MEDIUM',
                   work_type='verification', context_links=['https://example.test/context'],
                   repository='owner/repo', target='nate')
    response = write(client, f'/tasks/{task_id}/edit', payload)
    assert response.status_code == 200, response.text
    edited = response.json()
    assert {key: edited[key] for key in FIELDS} == payload
    for field in ('id', 'creator', 'created_at', 'parent_id', 'funded'):
        assert edited[field] == original[field]
    assert edited['status'] == 'open' and edited['claimant'] is None
    assert edited['events'][:-1] == original['events']
    event = edited['events'][-1]
    assert (event['kind'], event['actor'], event['state']) == ('edited', 'steve', 'open')
    assert event['data']['changes'] == {
        field: {'before': original[field], 'after': payload[field]}
        for field in FIELDS if original[field] != payload[field]}
    assert event['data']['complexity'] == 'MEDIUM'
    assert event['data']['work_type'] == 'verification'
    cleared = write(client, f'/tasks/{task_id}/edit', body(edited, target=None))
    assert cleared.status_code == 200
    assert cleared.json()['target'] is None
    listing = client.get('/api/v1/tasks?view=all').json()['items']
    assert next(item for item in listing if item['id'] == task_id)['complexity'] == 'MEDIUM'


def test_gold_adjustments_and_idempotent_retry(client):
    original = post_task(client).json()
    task_id = original['id']
    before = balances(client, task_id)
    payload = body(original, gold=200)
    first = write(client, f'/tasks/{task_id}/edit', payload, key='raise-gold')
    assert first.status_code == 200, first.text
    assert balances(client, task_id) == (before[0] - 50, before[1] + 50)
    retry = write(client, f'/tasks/{task_id}/edit', payload, key='raise-gold')
    assert retry.status_code == 200 and retry.json() == first.json()
    assert balances(client, task_id) == (before[0] - 50, before[1] + 50)
    conflict = write(client, f'/tasks/{task_id}/edit', body(original, gold=201), key='raise-gold')
    assert conflict.status_code == 409
    reduced = write(client, f'/tasks/{task_id}/edit', body(first.json(), gold=100))
    assert reduced.status_code == 200, reduced.text
    assert balances(client, task_id) == (before[0] + 50, before[1] - 50)
    unchanged = write(client, f'/tasks/{task_id}/edit', body(reduced.json()))
    assert unchanged.status_code == 200
    assert unchanged.json()['events'][-1]['data']['changes'] == {}
    transactions = client.get('/api/v1/me/transactions').json()
    adjusted = [row for row in transactions if row['kind'] == 'task_edited']
    assert len({row['id'] for row in adjusted}) == 2
    assert sum(row['amount'] for row in adjusted) == 0
    assert len([e for e in fetch(client, task_id)['events'] if e['kind'] == 'edited']) == 3


@pytest.mark.parametrize('state', ['open', 'claimed', 'closed', 'reopened_after_claim'])
def test_refusals_are_clear_rule_errors(client, state):
    task = post_task(client).json()
    task_id = task['id']
    actor, status, message = 'steve', 409, 'Only open, unclaimed tasks'
    if state == 'open':
        actor, status, message = 'nate', 403, 'Only the creator'
    elif state in ('claimed', 'reopened_after_claim'):
        assert write(client, f'/tasks/{task_id}/take', user='nate').status_code == 200
        if state == 'reopened_after_claim':
            # Synthetic state: even an open record with a historic claim is locked.
            service = client.app.state.service
            with service.db.write() as c:
                service.event(c, task_id, 'reopened', 'steve', 'open')
    else:
        assert write(client, f'/tasks/{task_id}/cancel').status_code == 200
    before = fetch(client, task_id)
    funds = balances(client, task_id)
    response = write(client, f'/tasks/{task_id}/edit', body(task, title='Forbidden'), actor)
    assert response.status_code == status
    assert message in response.json()['detail']
    with pytest.raises(RuleError, match=message):
        client.app.state.service.execute(actor, 'direct-refusal', 'edit',
                                         {'id': task_id, **body(task, title='Forbidden')})
    assert fetch(client, task_id) == before
    assert balances(client, task_id) == funds


def test_failed_edit_rolls_back_and_retry_after_claim_is_cached(client):
    task = post_task(client).json()
    task_id = task['id']
    funds = balances(client, task_id)
    for changes, status in [({'gold': 1000000}, 409), ({'target': 'missing'}, 422)]:
        response = write(client, f'/tasks/{task_id}/edit', body(task, **changes))
        assert response.status_code == status, response.text
        assert fetch(client, task_id) == task
        assert balances(client, task_id) == funds
    payload = body(task, title='Saved before claim')
    first = write(client, f'/tasks/{task_id}/edit', payload, key='saved-edit')
    assert first.status_code == 200
    assert write(client, f'/tasks/{task_id}/take', user='nate').status_code == 200
    retry = write(client, f'/tasks/{task_id}/edit', payload, key='saved-edit')
    assert retry.json() == first.json()
    current = fetch(client, task_id)
    assert current['status'] == 'working'
    assert len([event for event in current['events'] if event['kind'] == 'edited']) == 1


@pytest.mark.parametrize('changes', [
    {'gold': 0}, {'gold': True}, {'complexity': 'INVALID'},
    {'work_type': 'INVALID'}, {'title': ''}, {'criteria': []}, {'id': 'replacement'},
])
def test_edit_request_validation(client, changes):
    task = post_task(client).json()
    response = write(client, f"/tasks/{task['id']}/edit", body(task, **changes))
    assert response.status_code == 422
    assert fetch(client, task['id']) == task
