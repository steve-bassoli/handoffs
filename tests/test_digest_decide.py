"""Decision digest LOW-5: one audited human decision per waiting item (app/digest_decide.py)."""
import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.prototype as prototype
from app.main import create_app
from conftest import post_task, write


class VetoScreen:
    def screen(self, text):
        return {'verdict': 'veto', 'reason': 'Synthetic veto', 'model': 'fixture', 'policy_sha256': 'fixture'}


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'allow')
    monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', 'observe')
    with TestClient(create_app(tmp_path / 'decide.sqlite')) as client:
        client.app.state.credentials.set_password('steve', 'synthetic test password only')
        token = client.post('/api/v1/auth/login', json={'username': 'steve', 'password': 'synthetic test password only'}).json()['access_token']
        client.human = {'Authorization': 'Bearer ' + token}
        client.relay = {'Authorization': 'Bearer ' + client.app.state.credentials.issue('steve', 'relay')['access_token']}
        yield client


def digest(client):
    return client.get('/api/v1/digest', headers=client.human).json()['items']


def item(client, kind, ident):
    return next((i for i in digest(client) if i['kind'] == kind and i['id'] == ident), None)


def decide(client, it, choice, headers=None, key=None, **extra):
    body = {'kind': it['kind'], 'id': it['id'], 'revision': it['revision'], 'decision': choice, 'note': 'Synthetic decision', **extra}
    return client.post('/api/v1/digest/decide', json=body, headers={**(headers or client.human), 'Idempotency-Key': key or str(uuid4())})


def signoff(client):
    body = {'action': 'publish', 'payload': {'commit': str(uuid4())}, 'summary': 'Synthetic publish'}
    sid = client.post('/api/v1/signoffs', json=body, headers=client.relay).json()['id']
    return item(client, 'signoff', sid)


def proofed_task(client, proof=True):
    client.headers.update(client.human)
    task_id = post_task(client, gold=10).json()['id']
    assert write(client, f'/tasks/{task_id}/take').status_code == 200
    if proof:
        write(client, f'/tasks/{task_id}/profile', {'validation_scope': 'SIM', 'migration_stage': 'WRAP', 'baseline_revision': 'a',
                                                    'candidate_revision': 'b', 'environment': 'synthetic'})
        upload = {'filename': 'evidence.txt', 'media_type': 'text/plain', 'content_base64': base64.b64encode(b'Synthetic evidence').decode(),
                  'description': 'Synthetic evidence'}
        assert write(client, f'/tasks/{task_id}/proofs', upload).status_code == 200
    for k in ('Authorization',):
        client.headers.pop(k, None)
    return task_id


def test_signoff_yes_no_change_never_consume(board):
    it = signoff(board)
    assert decide(board, it, 'change').status_code == 200
    assert item(board, 'signoff', it['id']) is not None  # Change keeps it waiting.
    it = item(board, 'signoff', it['id'])
    approved = decide(board, it, 'yes')
    assert approved.status_code == 200 and approved.json()['consumed'] is False
    assert item(board, 'signoff', it['id']) is None
    with board.app.state.service.db.engine.connect() as c:
        row = c.exec_driver_sql('SELECT decision, decision_mode, used_at, change_note FROM signoffs WHERE id=?', (it['id'],)).fetchone()
    assert row == ('approved', 'human', None, 'Synthetic decision')
    other = signoff(board)
    assert decide(board, other, 'no').status_code == 200
    assert item(board, 'signoff', other['id']) is None


@pytest.mark.parametrize('who', ['relay', 'demo'])
def test_only_a_signed_in_person_decides_even_with_the_door_off(board, monkeypatch, who):
    monkeypatch.setenv('ASE_DOOR', 'off')
    it = signoff(board)
    headers = board.relay if who == 'relay' else {'X-Demo-User': 'steve'}
    response = decide(board, it, 'yes', headers=headers)
    assert response.status_code == 403
    assert item(board, 'signoff', it['id']) is not None


def test_stale_revision_and_duplicate_request(board):
    it = signoff(board)
    stale = decide(board, {**it, 'revision': '0' * 64}, 'yes')
    assert stale.status_code == 409 and stale.json()['detail']['revision'] == it['revision']
    first = decide(board, it, 'yes', key='same-key')
    again = decide(board, it, 'yes', key='same-key')
    assert first.status_code == again.status_code == 200 and first.json() == again.json()


def test_intake_veto_yes_overrides_and_no_upholds(tmp_path, monkeypatch):
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', 'observe')
    with TestClient(create_app(tmp_path / 'veto.sqlite', intake_screen=VetoScreen())) as client:
        client.app.state.credentials.set_password('steve', 'synthetic test password only')
        token = client.post('/api/v1/auth/login', json={'username': 'steve', 'password': 'synthetic test password only'}).json()['access_token']
        client.human = {'Authorization': 'Bearer ' + token}
        ids = [post_task(client).json()['id'] for _ in range(2)]
        yes = decide(client, item(client, 'intake_veto', ids[0]), 'yes')
        assert yes.status_code == 200 and item(client, 'intake_veto', ids[0]) is None
        no = decide(client, item(client, 'intake_veto', ids[1]), 'no')
        assert no.status_code == 200 and no.json()['status'] == 'blocked' and item(client, 'intake_veto', ids[1]) is None
        events = client.get('/api/v1/tasks/' + ids[1], headers=client.human).json()['events']
        assert [e['kind'] for e in events][-2:] == ['intake_veto_upheld', 'digest_decided']


def test_a_finished_task_leaves_no_veto_waiting(tmp_path, monkeypatch):
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'allow')
    monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', 'observe')
    with TestClient(create_app(tmp_path / 'done.sqlite', intake_screen=VetoScreen())) as client:
        client.app.state.credentials.set_password('steve', 'synthetic test password only')
        token = client.post('/api/v1/auth/login', json={'username': 'steve', 'password': 'synthetic test password only'}).json()['access_token']
        client.human = {'Authorization': 'Bearer ' + token}
        task_id = proofed_task(client)
        assert item(client, 'intake_veto', task_id) is not None
        assert decide(client, item(client, 'human_close', task_id), 'yes').status_code == 200
        assert item(client, 'intake_veto', task_id) is None


def test_human_close_needs_current_proof_and_records_the_decision(board):
    bare = proofed_task(board, proof=False)
    assert decide(board, item(board, 'human_close', bare), 'yes').status_code == 409
    task_id = proofed_task(board)
    closed = decide(board, item(board, 'human_close', task_id), 'yes')
    assert closed.status_code == 200, closed.text
    assert closed.json()['status'] in ('completed', 'settled')
    events = board.get('/api/v1/tasks/' + task_id, headers=board.human).json()['events']
    audit = [e for e in events if e['kind'] == 'digest_decided'][-1]['data']
    assert audit['decision'] == 'yes' and audit['decided_by'] == 'steve' and audit['principal'] == 'human'


def attach_proof(client, task_id):
    write(client, f'/tasks/{task_id}/profile', {'validation_scope': 'SIM', 'migration_stage': 'WRAP', 'baseline_revision': 'a',
                                               'candidate_revision': 'b', 'environment': 'synthetic'})
    upload = {'filename': 'evidence.txt', 'media_type': 'text/plain', 'content_base64': base64.b64encode(b'Synthetic evidence').decode(),
              'description': 'Synthetic evidence'}
    return write(client, f'/tasks/{task_id}/proofs', upload)


def test_a_high_closes_on_two_accepted_dependencies(board):
    high = write(board, '/tasks', {'title': 'Synthetic HIGH', 'goal': 'Integrate the slices', 'criteria': ['Slices integrate'],
                                   'gold': 10, 'complexity': 'HIGH'}).json()['id']
    first, second = proofed_task(board), proofed_task(board)
    assert write(board, f'/tasks/{high}/dependencies', {'depends_on': [first, second]}).status_code == 200
    assert write(board, f'/tasks/{high}/take').status_code == 200
    assert decide(board, item(board, 'human_close', first), 'yes').status_code == 200
    # One of two dependencies accepted: no proof, no card.
    assert attach_proof(board, high).status_code != 200
    assert item(board, 'human_close', high) is None
    assert decide(board, item(board, 'human_close', second), 'yes').status_code == 200
    assert attach_proof(board, high).status_code == 200
    closed = decide(board, item(board, 'human_close', high), 'yes')
    assert closed.status_code == 200, closed.text
    assert closed.json()['status'] in ('completed', 'settled')


def test_a_high_with_one_dependency_still_needs_a_decomposition(board):
    high = write(board, '/tasks', {'title': 'Synthetic HIGH', 'goal': 'One slice is not a split', 'criteria': ['Slice integrates'],
                                   'gold': 10, 'complexity': 'HIGH'}).json()['id']
    only = proofed_task(board)
    assert decide(board, item(board, 'human_close', only), 'yes').status_code == 200
    assert write(board, f'/tasks/{high}/dependencies', {'depends_on': [only]}).status_code == 200
    assert write(board, f'/tasks/{high}/take').status_code == 200
    refused = attach_proof(board, high)
    assert refused.status_code != 200 and 'decomposition' in refused.text
    assert item(board, 'human_close', high) is None


def test_batch_yes_reports_each_item_and_is_safe_to_retry(board):
    a, b = signoff(board), signoff(board)
    stale = {**signoff(board), 'revision': '0' * 64}
    body = {'items': [{'kind': i['kind'], 'id': i['id'], 'revision': i['revision']} for i in (a, b, stale)], 'note': 'Batch synthetic'}
    first = board.post('/api/v1/digest/decide-batch', json=body, headers={**board.human, 'Idempotency-Key': 'batch-1'}).json()
    assert first['decided'] == 2 and first['failed'] == 1
    assert [r['ok'] for r in first['results']] == [True, True, False] and first['results'][2]['status'] == 409
    again = board.post('/api/v1/digest/decide-batch', json=body, headers={**board.human, 'Idempotency-Key': 'batch-1'}).json()
    assert [r.get('result') for r in again['results'][:2]] == [r['result'] for r in first['results'][:2]]
    refused = board.post('/api/v1/digest/decide-batch', json=body, headers={**board.relay, 'Idempotency-Key': 'batch-2'})
    assert refused.status_code == 403


def test_only_items_a_click_can_complete_are_ready(board):
    bare, proofed = proofed_task(board, proof=False), proofed_task(board)
    data = board.get('/api/v1/digest', headers=board.human).json()
    items = {i['id']: i for i in data['items'] if i['kind'] == 'human_close'}
    assert items[bare]['ready'] is False and items[bare]['waiting_on'] == 'needs proof first'
    assert items[proofed]['ready'] is True and items[proofed]['waiting_on'] is None
    assert data['counts']['ready'] == sum(i['ready'] for i in data['items'])


def test_a_veto_on_claimed_work_waits_instead_of_offering_a_click(tmp_path, monkeypatch):
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', 'observe')
    with TestClient(create_app(tmp_path / 'veto2.sqlite', intake_screen=VetoScreen())) as client:
        client.app.state.credentials.set_password('steve', 'synthetic test password only')
        token = client.post('/api/v1/auth/login', json={'username': 'steve', 'password': 'synthetic test password only'}).json()['access_token']
        client.human = {'Authorization': 'Bearer ' + token}
        open_id, taken_id = post_task(client).json()['id'], post_task(client).json()['id']
        client.headers.update(client.human)
        assert write(client, f'/tasks/{taken_id}/take').status_code == 200
        client.headers.pop('Authorization')
        assert item(client, 'intake_veto', open_id)['ready'] is True
        waiting = item(client, 'intake_veto', taken_id)
        assert waiting['ready'] is False and 'already being worked on' in waiting['waiting_on']


def test_construction_mode_folds_task_closes_but_keeps_vetoes_and_the_gate(board, monkeypatch):
    task_id = proofed_task(board)
    assert item(board, 'human_close', task_id)['ready'] is True
    monkeypatch.setenv('ASE_DOOR', 'off')
    folded = item(board, 'human_close', task_id)
    assert folded['ready'] is False and 'relay closes proven work' in folded['waiting_on']
    # Deciding is unchanged: a demo header still cannot decide, door or no door.
    refused = decide(board, folded, 'yes', headers={'X-Demo-User': 'steve'})
    assert refused.status_code == 403
