import base64
import hashlib
import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from app.packages import build_package
from app.storage import one
from conftest import post_bounty, write
from test_ai import FakeLuna, decision, source_zip
from test_imports import fixture_repository


def package(bounty_id, files=None, **metadata):
    files = files or {'RESPONSE.md': 'Review findings, not a verified implementation.'}
    manifest = {'schema_version': 1, 'task_id': bounty_id, **metadata,
                'files': [{'path': path, 'sha256': hashlib.sha256(content.encode()).hexdigest()} for path, content in files.items()]}
    return source_zip({**files, 'manifest.json': json.dumps(manifest)})


def test_response_roundtrip_is_auditable_idempotent_and_never_completes_or_pays(tmp_path):
    database = tmp_path / 'roundtrip.sqlite'
    with TestClient(create_app(database)) as client:
        bounty_id = post_bounty(client).json()['id']
        original = client.get(f'/api/v1/bounties/{bounty_id}/artifacts/download').content
        original_sha = hashlib.sha256(original).hexdigest()
        payload = {'kind': 'response', 'package_zip': package(bounty_id, input_sha256=original_sha),
                   'input_zip': base64.b64encode(original).decode(), 'note': 'Fresh session review'}
        with client.app.state.service.db.engine.connect() as c:
            allocations = one(c, 'SELECT COUNT(*) AS n FROM monthly_allocations')['n']
            transactions = one(c, 'SELECT COUNT(*) AS n FROM gold_transactions')['n']
        assert write(client, f'/bounties/{bounty_id}/packages', payload, 'nate').status_code == 403
        for key in ('same', 'same', 'different'):
            response = write(client, f'/bounties/{bounty_id}/packages', payload, key=key)
            assert response.status_code == 200, response.text
            detail = response.json()
            assert detail['status'] == 'open' and detail['claimant'] is None and detail['ai_run'] is None
            assert len(detail['packages']) == 1 and detail['packages'][0]['input_verified']
        with client.app.state.service.db.engine.connect() as c:
            assert one(c, 'SELECT COUNT(*) AS n FROM monthly_allocations')['n'] == allocations
            assert one(c, 'SELECT COUNT(*) AS n FROM gold_transactions')['n'] == transactions
        response = client.get(f'/api/v1/bounties/{bounty_id}/artifacts/download')
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            path = next(path for path in archive.namelist() if path.startswith('packages/') and path.endswith('RESPONSE.md'))
            assert archive.read(path).startswith(b'Review findings')
    with TestClient(create_app(database)) as client:
        assert client.get(f'/api/v1/bounties/{bounty_id}').json()['packages'][0]['input_verified']


def test_package_rejects_wrong_identity_tampering_missing_files_and_unsafe_paths(client):
    bounty_id = post_bounty(client).json()['id']
    invalid = [package('another-bounty'), source_zip({'RESPONSE.md': 'No manifest'}),
               source_zip({'manifest.json': json.dumps({'schema_version': 1, 'task_id': bounty_id,
                   'files': [{'path': 'RESPONSE.md', 'sha256': '0' * 64}]}), 'RESPONSE.md': 'tampered'}),
               package(bounty_id, {'../outside.txt': 'no'}), package(bounty_id, {'secret.key': 'no'}),
               source_zip({'manifest.json': '[]'}), package(bounty_id, input_sha256='invalid')]
    for encoded in invalid:
        result = write(client, f'/bounties/{bounty_id}/packages', {'kind': 'response', 'package_zip': encoded})
        assert result.status_code == 422, result.text
    assert client.get(f'/api/v1/bounties/{bounty_id}').json()['packages'] == []


def test_response_input_hash_and_identity_are_checked(client):
    bounty_id = post_bounty(client).json()['id']
    wrong = source_zip({'bounty.json': json.dumps({'id': 'another-bounty'})})
    for sha in ('0' * 64, hashlib.sha256(base64.b64decode(wrong)).hexdigest()):
        response = write(client, f'/bounties/{bounty_id}/packages', {'kind': 'response',
            'package_zip': package(bounty_id, input_sha256=sha), 'input_zip': wrong})
        assert response.status_code == 422


def test_pinned_support_builder_only_exports_selected_committed_files(client, tmp_path):
    repo, directory, git = fixture_repository(tmp_path)
    (repo / 'probe.ps1').write_text('Write-Output "offline"\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Source')
    revision = git('rev-parse', 'HEAD')
    (repo / 'probe.ps1').write_text('uncommitted change', encoding='utf-8')
    bounty_id = post_bounty(client).json()['id']
    raw = build_package(repo, revision, bounty_id, ['probe.ps1'], 'Run only offline checks.')
    assert raw == build_package(repo, revision, bounty_id, ['probe.ps1'], 'Run only offline checks.')
    encoded = base64.b64encode(raw).decode()
    result = write(client, f'/bounties/{bounty_id}/packages', {'kind': 'support', 'package_zip': encoded})
    assert result.status_code == 200, result.text
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.read('source/probe.ps1') == b'Write-Output "offline"\n'
        assert json.loads(archive.read('manifest.json'))['revision'] == revision
    assert client.get(f'/api/v1/bounties/{bounty_id}/artifacts').json()['readiness']['status'] == 'review_required'
    assert (repo / 'probe.ps1').read_text() == 'uncommitted change'


def test_luna_reuses_attached_support_source_without_executing_response_text(tmp_path):
    model = FakeLuna([decision('deliver', files=[{'path': 'calc.py', 'content': 'fixed'}], instructions='Run tests locally')])
    with TestClient(create_app(tmp_path / 'ai.sqlite', ai_model=model)) as client:
        bounty_id = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty_id}/packages', {'kind': 'support',
            'package_zip': package(bounty_id, {'source/calc.py': 'original source'})})
        write(client, f'/bounties/{bounty_id}/packages', {'kind': 'response',
            'package_zip': package(bounty_id, {'calc.py': 'Not approved as source'})})
        assert write(client, f'/bounties/{bounty_id}/ai/start', {}).status_code == 200
        assert client.get(f'/api/v1/bounties/{bounty_id}').json()['ai_run']['status'] == 'ready'
        with zipfile.ZipFile(io.BytesIO(client.get(f'/api/v1/bounties/{bounty_id}/artifacts/download').content)) as archive:
            assert archive.read('ai/source/calc.py') == b'original source'
