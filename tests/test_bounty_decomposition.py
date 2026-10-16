from app.importer import import_git
from app.storage import one
from conftest import write
from test_imports import fixture_repository


def completed_packet(client, tmp_path):
    import json
    repo, directory, git = fixture_repository(tmp_path)
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['recipient'] = 'STEVE'
    renamed = directory.with_name('prove-demo-steve')
    directory.rename(renamed)
    (renamed / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    event = {'schemaVersion': 1, 'eventId': 'completed-one', 'taskId': 'prove-demo', 'type': 'completed',
             'actor': 'NATE', 'createdUtc': '2026-10-16T12:00:00Z', 'resultPath': '', 'replyTo': ''}
    (renamed / 'events/completed-one.json').write_text(json.dumps(event), encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Completed packet')
    assert not import_git(client.app.state.service.db, repo, 'HEAD')['gaps']
    return 'prove-demo'


def test_reopen_is_authorized_idempotent_and_preserves_completion_evidence_and_gold(client, tmp_path):
    bounty_id = completed_packet(client, tmp_path)
    before = client.get(f'/api/v1/bounties/{bounty_id}').json()
    payload = {'complexity': 'HIGH', 'note': 'Reopen for bounded decomposition, not acceptance.'}
    assert write(client, f'/bounties/{bounty_id}/reopen', payload, user='will').status_code == 403
    for _ in range(2):
        response = write(client, f'/bounties/{bounty_id}/reopen', payload, key='reopen')
        assert response.status_code == 200, response.text
        after = response.json()
        assert after['status'] == 'open' and after['complexity'] == 'HIGH'
        assert after['completed_by'] == 'nate' and after['legacy'] == before['legacy']
        assert after['events'][:-1] == before['events']
        assert after['packages'] == before['packages'] and after['funded'] == 0
    assert write(client, f'/bounties/{bounty_id}/reopen', payload).status_code == 409
    with client.app.state.service.db.engine.connect() as c:
        assert one(c, 'SELECT COUNT(*) AS n FROM gold_transactions')['n'] == 0
        assert one(c, 'SELECT COUNT(*) AS n FROM ai_runs')['n'] == 0
    assert client.get('/api/v1/bounties?view=all').json()['items'][0]['complexity'] == 'HIGH'
