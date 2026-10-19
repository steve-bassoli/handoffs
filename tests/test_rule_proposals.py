"""Protected rule texts approved in Decisions (task 2c56ad7a): two signed-in people, one decision each."""
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.prototype as prototype
from app.main import create_app
from app.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
CHANGED = {'SHARED', 'WORKER_PREFIX'}


@pytest.fixture
def board(tmp_path, monkeypatch):
    rules, proposals = tmp_path / 'rules', tmp_path / 'proposals'
    rules.mkdir()
    for name in ('agent-rules.json', 'APPROVALS.json'):
        shutil.copyfile(ROOT / 'rules' / name, rules / name)
    # A synthetic proposal built from whatever rules are live, so these checks never depend on a real proposal.
    folder = proposals / 'synthetic'
    folder.mkdir(parents=True)
    data = json.loads((rules / 'agent-rules.json').read_bytes())
    for name in CHANGED:
        data['texts'][name] += ' (synthetic proposal)'
    (folder / 'agent-rules.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    (folder / 'README.md').write_text('# Proposal: synthetic fixture\n\nAuthor: test fixture.\n', encoding='utf-8')
    monkeypatch.setenv('ASE_RULES_DIR', str(rules))
    monkeypatch.setenv('ASE_PROPOSALS_DIR', str(proposals))
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'allow')
    with TestClient(create_app(tmp_path / 'rules.sqlite')) as client:
        client.people = {}
        for person in ('steve', 'nate'):
            client.app.state.credentials.set_password(person, 'synthetic test password only')
            token = client.post('/api/v1/auth/login', json={'username': person, 'password': 'synthetic test password only'}).json()['access_token']
            client.people[person] = {'Authorization': 'Bearer ' + token}
        client.relay = {'Authorization': 'Bearer ' + client.app.state.credentials.issue('steve', 'relay')['access_token']}
        client.rules, client.proposal = rules, folder
        yield client


def card(client, person):
    items = client.get('/api/v1/digest', headers=client.people[person]).json()['items']
    return next((i for i in items if i['kind'] == 'rule_texts'), None)


def decide(client, person, item, choice, headers=None):
    body = {'kind': 'rule_texts', 'id': item['id'], 'revision': item['revision'], 'decision': choice, 'note': f'{person} read every text'}
    return client.post('/api/v1/digest/decide', json=body, headers={**(headers or client.people[person]), 'Idempotency-Key': str(uuid4())})


def test_card_shows_every_changed_text_and_the_digest(board):
    item = card(board, 'steve')
    assert item['revision'] == __import__('hashlib').sha256((board.proposal / 'agent-rules.json').read_bytes()).hexdigest()
    assert {c['name'] for c in item['details']['changed']} == CHANGED and item['title'] == 'Proposal: synthetic fixture'
    assert item['why_waiting'].startswith('0 of 2 approvals') and item['effect']['reversibility'] == 'irreversible'
    assert item['recommendation'] == {'status': 'unavailable'}


def test_two_people_accept_and_the_server_writes_both_files(board):
    before = (board.rules / 'agent-rules.json').read_bytes()
    first = decide(board, 'steve', card(board, 'steve'), 'yes')
    assert first.status_code == 200 and first.json()['applied'] is False and '1 of 2' in first.json()['message']
    assert card(board, 'steve') is None  # Steve is no longer waited on.
    assert (board.rules / 'agent-rules.json').read_bytes() == before
    waiting = card(board, 'nate')
    assert waiting['why_waiting'].startswith('1 of 2 approvals (steve)')
    second = decide(board, 'nate', waiting, 'yes')
    assert second.status_code == 200, second.text
    result = second.json()
    assert result['applied'] is True and result['restart_required'] is True and result['approved_by'] == ['steve', 'nate']
    assert (board.rules / 'agent-rules.json').read_bytes() == (board.proposal / 'agent-rules.json').read_bytes()
    entry = json.loads((board.rules / 'APPROVALS.json').read_bytes())[-1]
    assert entry['approved_by'] == ['steve', 'nate'] and entry['sha256'] == waiting['revision'] and 'bootstrap' not in entry
    assert '(synthetic proposal)' in load_rules(board.rules / 'agent-rules.json', board.rules / 'APPROVALS.json')['WORKER_PREFIX']
    assert card(board, 'steve') is None and card(board, 'nate') is None


@pytest.mark.parametrize('who', ['relay', 'demo'])
def test_only_signed_in_people_decide_even_with_the_door_off(board, monkeypatch, who):
    monkeypatch.setenv('ASE_DOOR', 'off')
    headers = board.relay if who == 'relay' else {'X-Demo-User': 'steve'}
    assert decide(board, 'steve', card(board, 'steve'), 'yes', headers=headers).status_code == 403
    assert card(board, 'steve')['why_waiting'].startswith('0 of 2')


def test_a_decline_blocks_applying(board):
    before = (board.rules / 'agent-rules.json').read_bytes()
    assert decide(board, 'steve', card(board, 'steve'), 'no').status_code == 200
    late = decide(board, 'nate', card(board, 'nate'), 'yes')
    assert late.status_code == 200 and late.json()['applied'] is False
    assert (board.rules / 'agent-rules.json').read_bytes() == before


def test_a_changed_proposal_never_inherits_approvals(board):
    assert decide(board, 'steve', card(board, 'steve'), 'yes').status_code == 200
    path = board.proposal / 'agent-rules.json'
    data = json.loads(path.read_bytes())
    data['texts']['SHARED'] += ' '
    path.write_text(json.dumps(data), encoding='utf-8')
    fresh = card(board, 'steve')
    assert fresh is not None and fresh['why_waiting'].startswith('0 of 2')  # Steve decides the new digest again.
    after = decide(board, 'nate', card(board, 'nate'), 'yes')
    assert after.status_code == 200 and after.json()['applied'] is False


def test_one_person_counts_once_and_batch_skips_rule_texts(board):
    item = card(board, 'steve')
    assert decide(board, 'steve', item, 'yes').status_code == 200
    assert decide(board, 'steve', item, 'yes').status_code == 409
    batch = {'items': [{'kind': 'rule_texts', 'id': item['id'], 'revision': item['revision']}], 'note': 'batch'}
    refused = board.post('/api/v1/digest/decide-batch', json=batch, headers={**board.people['nate'], 'Idempotency-Key': str(uuid4())})
    assert refused.status_code == 422


def test_second_acceptance_commits_exactly_the_two_rules_files(board):
    import subprocess
    repo = board.rules.parent

    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout
    git('init', '-q')
    git('config', 'user.name', 'Synthetic Tester')
    git('config', 'user.email', 'synthetic@example.invalid')
    git('add', 'rules')
    git('commit', '-q', '-m', 'baseline')
    (repo / 'unrelated.txt').write_text('must stay uncommitted', encoding='utf-8')
    git('add', 'unrelated.txt')  # Staged on purpose: the rules commit must not sweep it in.
    assert decide(board, 'steve', card(board, 'steve'), 'yes').status_code == 200
    result = decide(board, 'nate', card(board, 'nate'), 'yes').json()
    assert result['applied'] is True and result['commit'] and result['message'].startswith('Approved by steve and nate. Committed ')
    assert git('rev-parse', 'HEAD').strip() == result['commit']
    assert sorted(git('show', '--name-only', '--format=', 'HEAD').split()) == ['rules/APPROVALS.json', 'rules/agent-rules.json']
    message = git('log', '-1', '--format=%B')
    assert 'Approved by steve and nate' in message and 'second signed-in approval' in message
    assert 'unrelated.txt' in git('diff', '--cached', '--name-only')
