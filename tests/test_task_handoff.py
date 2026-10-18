"""Accepted-task packages are data for the active session, never worker launches."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from app.task_handoff import prepare, read_package


def task():
    return {'id': 'task-1', 'claimant': 'steve', 'status': 'working',
            'events': [{'seq': 7, 'kind': 'taken'}]}


def package(*, identity='task-1', corrupt=False, unsafe=False):
    files = {'task.json': json.dumps(task()).encode(),
             'context.md': b'Implement only the accepted task criteria.',
             'source.py': b'raise RuntimeError("Do not execute attached source")'}
    if unsafe:
        files['../escape.py'] = b'no'
    entries = [{'path': name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
               for name, raw in files.items()]
    if corrupt:
        files['context.md'] = b'tampered'
    files['handoff.json'] = json.dumps({'schema_version': 1, 'task_id': identity,
                                      'files': entries, 'readiness': {'status': 'review_required'}}).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return buffer.getvalue()


def test_claim_downloads_reads_and_reuses_verified_package_without_execution(tmp_path):
    downloads = []
    raw = package()
    def fetch():
        downloads.append(True)
        return raw
    first = prepare(task(), 'steve', 'http://service', fetch, tmp_path)
    second = prepare(task(), 'steve', 'http://service', fetch, tmp_path)
    assert downloads == [True]
    assert first['state'] == 'context-ready' and not first['reused'] and second['reused']
    assert first['execution_id'] == second['execution_id']
    assert 'accepted task criteria' in first['documents']['context.md']['text']
    assert Path(first['package_path']).read_bytes() == raw
    assert list(tmp_path.rglob('*source.py')) == []  # No extraction or execution.
    assert 'another start prompt' in first['next_action']


def test_changed_context_refreshes_package_in_same_execution(tmp_path):
    calls = []
    def fetch():
        calls.append(True)
        return package()
    first = prepare(task(), 'steve', 'http://service', fetch, tmp_path)
    changed = task()
    changed['events'].append({'seq': 8, 'kind': 'profile_recorded'})
    refreshed = prepare(changed, 'steve', 'http://service', fetch, tmp_path)
    assert calls == [True, True] and not refreshed['reused']
    assert first['execution_id'] == refreshed['execution_id']


@pytest.mark.parametrize('kwargs', [{'identity': 'other'}, {'corrupt': True}, {'unsafe': True}])
def test_invalid_packages_are_blocked_before_caching(tmp_path, kwargs):
    with pytest.raises(ValueError, match='invalid artifact package'):
        prepare(task(), 'steve', 'http://service', lambda: package(**kwargs), tmp_path)
    assert not list(tmp_path.rglob('input.zip'))


def test_other_identity_cannot_read_claimed_context(tmp_path):
    with pytest.raises(ValueError, match='claimant'):
        prepare(task(), 'nate', 'http://service', lambda: pytest.fail('Must not download'), tmp_path)


def test_extra_files_not_covered_by_manifest_are_rejected():
    raw = io.BytesIO(package())
    with zipfile.ZipFile(raw, 'a') as archive:
        archive.writestr('unlisted.txt', 'no')
    with pytest.raises(ValueError, match='every file'):
        read_package(raw.getvalue(), 'task-1')
