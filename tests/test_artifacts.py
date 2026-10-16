import hashlib
import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from app.importer import import_git
from app.storage import one
from conftest import post_bounty, write
from test_ai import FakeLuna, decision, source_zip
from test_imports import fixture_repository


def test_all_downloads_available_before_acceptance_without_writes(client):
    bounty = write(client, '/bounties', {'title': 'Preview me', 'goal': 'Read first', 'criteria': ['Inspect source'],
        'gold': 50, 'context_links': ['https://example.invalid/context'],
        'source_zip': source_zip({'guide.md': 'Review these instructions', 'src/example.py': 'print(1)\n'})}).json()['id']
    before = client.get('/api/v1/bounties/' + bounty).json()
    with client.app.state.service.db.engine.connect() as c:
        counts = [one(c, 'SELECT COUNT(*) AS n FROM ' + table)['n'] for table in ('events', 'ai_runs', 'gold_transactions')]
    inventory = client.get(f'/api/v1/bounties/{bounty}/artifacts', headers={'X-Demo-User': 'nate'}).json()
    response = client.get(inventory['download_url'], headers={'X-Demo-User': 'nate'})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read('posted-source/guide.md') == b'Review these instructions'
        assert archive.read('posted-source/src/example.py') == b'print(1)\n'
        assert json.loads(archive.read('bounty.json'))['criteria'] == ['Inspect source']
        assert json.loads(archive.read('references.json'))['repository_and_context_links'] == ['https://example.invalid/context']
        assert set(archive.namelist()) == {item['path'] for item in inventory['items']}
        for item in inventory['items']:
            content = client.get(item['download_url'], headers={'X-Demo-User': 'will'}).content
            assert content == archive.read(item['path'])
            assert hashlib.sha256(content).hexdigest() == item['sha256']
    after = client.get('/api/v1/bounties/' + bounty).json()
    assert before == after
    assert after['status'] == 'open' and after['claimant'] is None and after['ai_run'] is None
    with client.app.state.service.db.engine.connect() as c:
        assert counts == [one(c, 'SELECT COUNT(*) AS n FROM ' + table)['n'] for table in ('events', 'ai_runs', 'gold_transactions')]
    assert client.get(f'/api/v1/bounties/{bounty}/artifacts/file', params={'path': '../../app/main.py'}).status_code == 404


def test_imported_manifest_context_and_result_are_downloadable_before_claim(client, tmp_path):
    repo, directory, git = fixture_repository(tmp_path)
    (directory / 'updates').mkdir()
    (directory / 'updates/research.md').write_text('Existing research artifact', encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Research evidence')
    assert not import_git(client.app.state.service.db, repo, 'HEAD')['gaps']
    response = client.get('/api/v1/bounties/prove-demo/artifacts/download')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert json.loads(archive.read('imported/manifest.json'))['taskId'] == 'prove-demo'
        assert archive.read('imported/context.md') == b'Pinned criteria'
        assert archive.read('imported/updates/research.md') == b'Existing research artifact'
        assert archive.read('context.md') == b'Pinned criteria'
        assert 'imported/context.md' in archive.read('START_HERE.md').decode()
    assert client.get('/api/v1/bounties/prove-demo').json()['status'] == 'pending'


def test_handoff_checksums_readiness_templates_and_stable_zip(client):
    bounty = post_bounty(client).json()['id']
    first = client.get(f'/api/v1/bounties/{bounty}/artifacts/download').content
    assert client.get(f'/api/v1/bounties/{bounty}/artifacts/download').content == first
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        manifest = json.loads(archive.read('handoff.json'))
        assert manifest['task_id'] == bounty
        assert manifest['readiness']['status'] == 'needs_context'
        assert manifest['readiness']['source_file_count'] == 0
        assert manifest['readiness']['missing']
        assert {entry['path'] for entry in manifest['files']} == set(archive.namelist()) - {'handoff.json'}
        for entry in manifest['files']:
            assert entry['sha256'] == hashlib.sha256(archive.read(entry['path'])).hexdigest()
        assert json.loads(archive.read('response-template/manifest.json'))['task_id'] == bounty
        assert 'does not verify work' in archive.read('START_HERE.md').decode()
    inventory = client.get(f'/api/v1/bounties/{bounty}/artifacts').json()
    assert inventory['readiness'] == manifest['readiness']


def test_posted_source_is_available_to_luna_and_in_artifact_bundle(tmp_path):
    model = FakeLuna([decision('deliver', files=[{'path': 'calc.py', 'content': 'def add(a,b): return a+b\n'}], instructions='Test locally')])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = write(client, '/bounties', {'title': 'Fix addition', 'goal': 'Sum', 'criteria': ['Sums'],
            'gold': 50, 'complexity': 'LOW', 'source_zip': source_zip()}).json()['id']
        assert write(client, f'/bounties/{bounty}/ai/start', {}).status_code == 200
        assert client.get(f'/api/v1/bounties/{bounty}').json()['ai_run']['status'] == 'ready'
        response = client.get(f'/api/v1/bounties/{bounty}/artifacts/download')
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert 'ai/source/calc.py' in archive.namelist()
            assert 'ai/proposed/calc.py' in archive.namelist()
            assert 'fix.zip' in archive.namelist()


def test_bad_attachment_does_not_create_bounty(client):
    response = write(client, '/bounties', {'title': 'Bad', 'goal': 'Bad', 'criteria': ['Bad'],
        'gold': 50, 'source_zip': source_zip({'../outside.py': 'bad'})})
    assert response.status_code == 422
    assert client.get('/api/v1/bounties?view=all').json()['items'] == []
