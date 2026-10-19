"""Manual-step API integration tests.

The credential resolver is stubbed at its trust boundary: these tests exercise
resolved-principal enforcement, not password login or production token verification.
All token strings and secret-pattern samples below are synthetic test data.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import RuleError, event_identity
from app.storage import all_rows

SECRET_TEXT = 'sk-' + 'proj-' + 'synthetic-not-a-credential'
BODY = {
    'title': 'Approve the workstation prompt',
    'what': 'Review and approve the operating-system prompt yourself.',
    'where': 'On your own workstation.',
    'why': 'The local tool is waiting for your permission.',
    'success': 'The prompt closes and the tool reports it is connected.',
}


def headers(principal='human', key=None):
    result = {'Authorization': 'Bearer synthetic-' + principal,
              'X-Action-Intent': 'user-directed'}
    if key is not None:
        result['Idempotency-Key'] = key
    return result


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'refuse')
    monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', 'off')
    monkeypatch.setenv('HANDOFFS_AUTOMATION_MODE', str(tmp_path / 'mode.json'))
    with TestClient(create_app(tmp_path / 'manual-steps.sqlite')) as client:
        def resolve(token):
            for principal in ('human', 'relay', 'agent', 'codex', 'demo-header'):
                if token == 'synthetic-' + principal:
                    return {'user_id': 'steve', 'principal': principal,
                            'principal_id': 'synthetic-principal:' + principal}
            raise RuleError('Invalid credentials', 401)
        monkeypatch.setattr(client.app.state.credentials, 'resolve', resolve)
        yield client


def create_step(board, principal='human', **overrides):
    return board.post('/api/v1/manual-steps', json={**BODY, **overrides},
                      headers=headers(principal, str(uuid4())))


def created_step(board):
    response = create_step(board)
    assert response.status_code == 200, response.text
    return response.json()


def outcome(board, step, value='done', note='I completed the step myself.',
            principal='human', key=None, revision=None):
    return board.post('/api/v1/manual-steps/' + step['id'] + '/outcome', json={
        'outcome': value, 'note': note,
        'revision': step['revision'] if revision is None else revision,
    }, headers=headers(principal, key or str(uuid4())))


def digest_item(board, identifier):
    response = board.get('/api/v1/digest', headers=headers())
    assert response.status_code == 200, response.text
    return next((item for item in response.json()['items']
                 if item['kind'] == 'manual_step' and item['id'] == identifier), None)


def test_human_and_relay_create_and_get(board):
    for principal in ('human', 'relay'):
        response = create_step(board, principal)
        assert response.status_code == 200, response.text
        step = response.json()
        fetched = board.get('/api/v1/manual-steps/' + step['id'], headers=headers())
        assert fetched.status_code == 200
        assert fetched.json() == step
        assert step['state'] == 'open'
        assert step['where'] == BODY['where']
        assert len(step['revision']) == 64


def test_digest_and_batch_refusal(board):
    step = created_step(board)
    card = digest_item(board, step['id'])
    assert card is not None
    assert card['state'] == 'open'
    assert card['revision'] == step['revision']
    assert card['verbs'] == ['done', 'could_not']
    assert card['batch_approvable'] is False
    assert card['details']['what'] == BODY['what']
    refused = board.post('/api/v1/digest/decide-batch', json={
        'items': [{'kind': 'manual_step', 'id': step['id'], 'revision': step['revision']}],
        'note': 'This must not batch decide a manual step.',
    }, headers=headers(key=str(uuid4())))
    assert refused.status_code == 422
    assert digest_item(board, step['id']) is not None


@pytest.mark.parametrize('value', ['done', 'could_not'])
def test_human_outcomes_with_note(board, value):
    step = created_step(board)
    response = outcome(board, step, value, note='I tried this on my own workstation.')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['state'] == result['outcome'] == value
    assert result['note'] == 'I tried this on my own workstation.'
    assert result['decided_by'] == 'synthetic-principal:human'
    assert result['decided_utc']
    assert result['revision'] != step['revision']
    assert digest_item(board, step['id']) is None
    fetched = board.get('/api/v1/manual-steps/' + step['id'], headers=headers()).json()
    assert fetched == result


@pytest.mark.parametrize('principal', ['relay', 'agent', 'codex', 'demo-header'])
def test_nonhuman_refused_before_cached_result(board, principal):
    step = created_step(board)
    key = str(uuid4())
    assert outcome(board, step, key=key).status_code == 200
    assert outcome(board, step, principal=principal, key=key).status_code == 403
    # Also check Service.execute's own pre-cache authorization, not only the route.
    identity = {'user_id': 'steve', 'principal': principal,
                'principal_id': 'synthetic-principal:' + principal}
    token = event_identity.set(identity)
    try:
        with pytest.raises(RuleError) as error:
            board.app.state.service.execute('steve', key, 'ai_manual_step_outcome', {
                'id': step['id'], 'outcome': 'done',
                'note': 'I completed the step myself.', 'revision': step['revision'],
            })
        assert error.value.status == 403
    finally:
        event_identity.reset(token)


def test_nonhuman_cannot_record_fresh_outcome(board):
    step = created_step(board)
    for principal in ('relay', 'agent', 'codex', 'demo-header'):
        assert outcome(board, step, principal=principal).status_code == 403
    assert digest_item(board, step['id']) is not None


@pytest.mark.parametrize('note', ['', '   ', '\n\t'])
def test_blank_note_refused(board, note):
    step = created_step(board)
    assert outcome(board, step, note=note).status_code == 422
    assert digest_item(board, step['id']) is not None


def test_revision_key_and_terminal_conflicts(board):
    step = created_step(board)
    assert outcome(board, step, revision='0' * 64).status_code == 409
    response = board.post('/api/v1/manual-steps/' + step['id'] + '/outcome', json={
        'outcome': 'done', 'note': 'I performed it.', 'revision': step['revision'],
    }, headers=headers())
    assert response.status_code == 422
    first = outcome(board, step)
    assert first.status_code == 200
    assert outcome(board, step).status_code == 409
    assert outcome(board, first.json(), value='could_not').status_code == 409


def test_idempotent_replay_and_changed_payload_refusal(board):
    step = created_step(board)
    key = str(uuid4())
    first = outcome(board, step, key=key)
    replay = outcome(board, step, key=key)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert outcome(board, step, key=key, note='Different input').status_code == 409


@pytest.mark.parametrize('field', list(BODY))
def test_secret_creation_text_refused_without_echo(board, field):
    response = create_step(board, **{field: SECRET_TEXT})
    assert response.status_code == 422
    assert SECRET_TEXT not in response.text
    with board.app.state.service.db.engine.connect() as c:
        assert all_rows(c, 'SELECT * FROM manual_steps') == []


def test_secret_note_refused_without_echo(board):
    step = created_step(board)
    response = outcome(board, step, note=SECRET_TEXT)
    assert response.status_code == 422
    assert SECRET_TEXT not in response.text
    fetched = board.get('/api/v1/manual-steps/' + step['id'], headers=headers()).json()
    assert fetched['state'] == 'open'
    assert fetched['note'] is None


@pytest.mark.parametrize('value', ['', ' ' * 4, 'x' * 2001, 42, 'bad\u0000text'])
def test_invalid_creation_text(board, value):
    assert create_step(board, title=value).status_code == 422


def test_no_task_event_gold_or_monthly_allocation_mutation(board):
    service = board.app.state.service
    tables = ('tasks', 'events', 'gold_transactions', 'gold_entries', 'monthly_allocations')
    def snapshot():
        with service.db.engine.connect() as c:
            return {table: all_rows(c, 'SELECT * FROM ' + table) for table in tables}
    before = snapshot()
    step = created_step(board)
    assert outcome(board, step).status_code == 200
    assert snapshot() == before
