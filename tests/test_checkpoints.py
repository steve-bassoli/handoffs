import io
import json
import zipfile

import pytest

from app.artifacts import download
from app.services import RuleError
from conftest import post_task, verified_proof, write


def checkpoint(client, identifier, notes='Done: source traced. Remaining: native parity. Evidence: saved draft.', actor='steve', key='checkpoint'):
    return client.app.state.service.execute(actor, key, 'checkpoint', {'id': identifier, 'notes': notes})


def test_atomic_progress_continuation_preserves_scope_gold_and_retry(client):
    original = post_task(client).json()
    identifier = original['id']
    assert write(client, f'/tasks/{identifier}/take').status_code == 200
    prior = client.app.state.service.get(identifier)
    wallet = client.get('/api/v1/me/stats').json()['available_gold']
    result = checkpoint(client, identifier)
    old = client.app.state.service.get(identifier)
    assert old['status'] == 'superseded' and old['phase'] == 'Closed' and old['completed_by'] is None
    assert old['events'][:-1] == prior['events']
    assert old['continuation_id'] == result['id']
    assert result['id'] != identifier and result['status'] == 'open' and result['claimant'] is None
    assert result['target'] == prior['claimant']
    for field in ('title', 'goal', 'criteria', 'repository', 'creator', 'complexity', 'work_type', 'gold', 'funded'):
        assert result[field] == prior[field]
    assert result['checkpoint']['previous_task_id'] == identifier
    assert result['checkpoint']['acceptance_carried_forward'] is False
    assert result['proof'] is None and result['ai_run'] is None
    assert client.get('/api/v1/me/stats').json()['available_gold'] == wallet
    service = client.app.state.service
    with service.db.engine.connect() as c:
        assert service.balance(c, 'escrow:' + identifier) == 0
        assert service.balance(c, 'escrow:' + result['id']) == original['gold']
    assert checkpoint(client, identifier) == result
    with pytest.raises(RuleError):
        checkpoint(client, identifier, key='duplicate')
    with pytest.raises(RuleError):
        service.execute('steve', 'revive-old', 'status', {'id': identifier, 'status': 'working', 'note': 'revive'})
    with zipfile.ZipFile(io.BytesIO(download(service, result['id']))) as archive:
        assert b'Remaining: native parity' in archive.read('context.md')
        assert json.loads(archive.read('checkpoint.json'))['previous_task_id'] == identifier


def test_dependencies_follow_unfinished_work_not_closed_checkpoint(client):
    source, dependent = post_task(client).json(), post_task(client).json()
    client.app.state.service.execute('steve', 'dependencies', 'ai_dependencies',
        {'id': dependent['id'], 'depends_on': [source['id']]})
    successor = checkpoint(client, source['id'])
    task = client.app.state.service.get(dependent['id'])
    assert task['depends_on'] == [successor['id']]
    assert task['requirements'][0]['status'] == 'open'
    assert task['requirements'][0]['proof_id'] is None


def test_prior_acceptance_is_archived_not_reused(client):
    task = post_task(client).json()
    write(client, f"/tasks/{task['id']}/take")
    verified_proof(client, task['id'])
    service = client.app.state.service
    assert service.get(task['id'])['proof']['accepted']
    result = checkpoint(client, task['id'])
    assert result['proof'] is None and result['proof_history'] == []
    assert result['profile']
    assert service.get(task['id'])['proof_history']
    assert service.get(task['id'])['completed_by'] is None


def test_mid_transaction_failure_rolls_back_continuation_and_funding(client, monkeypatch):
    task = post_task(client).json()
    service = client.app.state.service
    before = service.get(task['id'])
    count = service.summary()['total']
    def fail(*args, **kwargs):
        raise RuntimeError('Injected after funding transfer')
    monkeypatch.setattr(service, 'event', fail)
    with pytest.raises(RuntimeError):
        checkpoint(client, task['id'])
    assert service.summary()['total'] == count
    assert service.get(task['id']) == before
    with service.db.engine.connect() as c:
        assert service.balance(c, 'escrow:' + task['id']) == task['gold']


def family(client):
    """Isolated structural fixture, not an approved live decomposition."""
    service = client.app.state.service
    parent = post_task(client, gold=20).json()
    a, b = post_task(client, gold=10).json(), post_task(client, gold=10).json()
    with service.db.write() as c:
        service.event(c, parent['id'], 'fixture-classification', 'steve', 'working', {'complexity': 'MEDIUM'})
        for child in (a, b):
            c.exec_driver_sql('UPDATE tasks SET parent_id=? WHERE id=?', (parent['id'], child['id']))
    return parent, a, b


def test_ro3_child_replacement_keeps_one_leaf_and_parent_requirements(client):
    parent, a, b = family(client)
    service = client.app.state.service
    result = checkpoint(client, a['id'])
    p = service.get(parent['id'])
    assert set(p['required_children']) == {result['id'], b['id']}
    assert result['complexity'] == 'LOW' and result['parent_id'] == parent['id']
    assert not result['required_children']
    assert service.get(a['id'])['parent_id'] is None
    assert service.get(a['id'])['checkpoint'] is None
    assert not service.hierarchy_violations()


def test_ro3_parent_continuation_moves_same_children_without_acceptance(client):
    parent, a, b = family(client)
    service = client.app.state.service
    result = checkpoint(client, parent['id'])
    assert result['complexity'] == 'MEDIUM'
    assert set(result['required_children']) == {a['id'], b['id']}
    assert all(service.get(child['id'])['parent_id'] == result['id'] for child in (a, b))
    assert not service.get(parent['id'])['required_children']
    assert not service.hierarchy_violations()
    assert result['proof'] is None


@pytest.mark.parametrize('change', ['other-actor', 'blank-notes', 'running', 'invalid-ro3'])
def test_failed_checkpoint_leaves_task_and_funds_intact(client, change):
    task = post_task(client).json()
    service = client.app.state.service
    if change == 'running':
        # This test uses a retained-state fixture, never an actual provider call.
        with service.db.write() as c:
            c.exec_driver_sql('INSERT INTO ai_runs VALUES (?,?,?,?,?,?,?)',
                ('fixture-run', task['id'], 'steve', 'running', json.dumps({}), 'now', 'now'))
        # The application projector needs real run metadata; a minimal AI projector is sufficient here.
        service.ai.public = lambda row: None
    if change == 'invalid-ro3':
        child = post_task(client).json()
        with service.db.write() as c:
            c.exec_driver_sql('UPDATE tasks SET parent_id=? WHERE id=?', (task['id'], child['id']))
    before = service.get(task['id'])
    with pytest.raises(RuleError):
        checkpoint(client, task['id'], notes=' ' if change == 'blank-notes' else 'Saved notes',
                   actor='nate' if change == 'other-actor' else 'steve')
    assert service.get(task['id']) == before
    with service.db.engine.connect() as c:
        assert service.balance(c, 'escrow:' + task['id']) == task['gold']
