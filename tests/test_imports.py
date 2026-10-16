import json
import sqlite3
import subprocess

from app.adapters import DemoDeliveryVerifier
from app.importer import import_database, import_git
from app.services import Service
from app.storage import Database, one


def fixture_repository(tmp_path):
    repo = tmp_path / 'source'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    git('remote', 'add', 'origin', 'https://github.com/example/fixture.git')
    directory = repo / 'PLAN/handoffs/prove-demo-open'
    (directory / 'events').mkdir(parents=True)
    manifest = {'schemaVersion': 2, 'taskId': 'prove-demo', 'sender': 'NATE', 'recipient': 'OPEN',
                'createdUtc': '2026-10-15T12:00:00Z', 'title': 'Legacy proof', 'queueItem': 'TAVERN', 'contextFile': 'context.md', 'gold': 150}
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (directory / 'context.md').write_text('Pinned criteria', encoding='utf-8')
    assigned = {'schemaVersion': 1, 'eventId': 'assigned-one', 'taskId': 'prove-demo', 'type': 'assigned',
                'actor': 'NATE', 'createdUtc': manifest['createdUtc'], 'resultPath': '', 'replyTo': ''}
    (directory / 'events/assigned-one.json').write_text(json.dumps(assigned), encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Fixture')
    return repo, directory, git


def initialized(tmp_path):
    db = Database(tmp_path / 'destination.sqlite')
    db.migrate()
    service = Service(db, DemoDeliveryVerifier())
    service.seed()
    return db, service


def test_git_import_repeatable_source_unchanged_and_conflict_reported(tmp_path):
    repo, directory, git = fixture_repository(tmp_path)
    db, service = initialized(tmp_path)
    revision = git('rev-parse', 'HEAD')
    result = import_git(db, repo, revision)
    assert result['imported'] == 1 and not result['gaps']
    assert import_git(db, repo, revision)['unchanged'] == 1
    detail = service.get('prove-demo')
    assert detail['legacy']['context'] == 'Pinned criteria'
    assert detail['status'] == 'pending' and detail['funded'] == 0
    with db.engine.connect() as c:
        assert one(c, 'SELECT COUNT(*) AS count FROM gold_transactions')['count'] == 0
    assert git('status', '--porcelain') == ''
    (directory / 'context.md').write_text('Changed source', encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Conflicting change')
    assert len(import_git(db, repo, 'HEAD')['gaps']) == 1
    assert service.get('prove-demo')['legacy']['context'] == 'Pinned criteria'
    db.engine.dispose()


def test_missing_result_is_gap_and_nothing_imported(tmp_path):
    repo, directory, git = fixture_repository(tmp_path)
    event = {'schemaVersion': 1, 'eventId': 'completed-one', 'taskId': 'prove-demo', 'type': 'completed',
             'actor': 'NATE', 'createdUtc': '2026-10-16T12:00:00Z', 'resultPath': 'missing.md', 'replyTo': ''}
    (directory / 'events/completed-one.json').write_text(json.dumps(event), encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Missing result')
    db, _ = initialized(tmp_path)
    result = import_git(db, repo, 'HEAD')
    assert result['imported'] == 0 and len(result['gaps']) == 1
    db.engine.dispose()


def test_database_rewards_remain_historical(tmp_path):
    legacy = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(legacy) as c:
        c.execute('CREATE TABLE intro_reward_events(reward_id TEXT PRIMARY KEY,person TEXT,gold INTEGER)')
        c.execute("INSERT INTO intro_reward_events VALUES ('intro:demo','STEVE',2000)")
    db, _ = initialized(tmp_path)
    result = import_database(db, legacy)
    assert result['imported'] == 1 and result['spendable_gold_imported'] == 0
    assert import_database(db, legacy)['unchanged'] == 1
    with db.engine.connect() as c:
        assert one(c, 'SELECT COUNT(*) AS count FROM gold_entries')['count'] == 0
    db.engine.dispose()


def test_later_events_append_without_rewriting_prior_history(tmp_path):
    repo, directory, git = fixture_repository(tmp_path)
    db, service = initialized(tmp_path)
    import_git(db, repo, 'HEAD')
    (directory / 'results').mkdir()
    (directory / 'results/result.md').write_text('Preserved result evidence', encoding='utf-8')
    event = {'schemaVersion': 1, 'eventId': 'completed-later', 'taskId': 'prove-demo', 'type': 'completed',
             'actor': 'NATE', 'createdUtc': '2026-10-16T12:00:00Z',
             'resultPath': 'PLAN/handoffs/prove-demo-open/results/result.md', 'replyTo': ''}
    (directory / 'events/completed-later.json').write_text(json.dumps(event), encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Append completion')
    result = import_git(db, repo, 'HEAD')
    assert result['imported'] == 1 and not result['gaps']
    detail = service.get('prove-demo')
    assert detail['status'] == 'completed' and len(detail['events']) == 2
    assert detail['completed_by'] == 'nate'
    assert detail['legacy']['documents'][-1]['content'] == 'Preserved result evidence'
    assert import_git(db, repo, 'HEAD')['unchanged'] == 1
    db.engine.dispose()


def test_legacy_requirements_project_for_new_and_existing_imports(tmp_path):
    repo, directory, git = fixture_repository(tmp_path)
    context = '# Probe\n\n## Goal\n\nRead safely.\n\n## Acceptance criteria\n\n- Only three operations.\n  Keep TLS.\n- No live calls.\n\n## Constraints\nDo not mutate.\n'
    (directory / 'context.md').write_text(context, encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Requirements')
    db, service = initialized(tmp_path)
    assert not import_git(db, repo, 'HEAD')['gaps']
    detail = service.get('prove-demo')
    assert detail['goal'] == 'Read safely.'
    assert detail['criteria'] == ['Only three operations.\nKeep TLS.', 'No live calls.']
    with db.write() as c:
        c.exec_driver_sql("UPDATE bounties SET goal='Historical imported assignment',criteria='[]',repository='' WHERE id='prove-demo'")
    assert service.get('prove-demo') == detail
    assert import_git(db, repo, 'HEAD')['unchanged'] == 1
    assert git('status', '--porcelain') == ''
    db.engine.dispose()
