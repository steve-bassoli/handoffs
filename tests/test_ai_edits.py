import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.ai import SourceEdit, materialize_edits
from app.main import create_app
from conftest import post_bounty, write
from test_ai import FakeLuna, decision, get_run, source_zip


def edited(path='calc.py', before='return a - b', after='return a + b'):
    result = decision('deliver', instructions='Run the proposed tests locally.', plan=[{
        'id': 'fix', 'title': 'Correct addition', 'complexity': 'LOW',
        'work_type': 'implementation', 'files': [path], 'children': []}])
    result.edits = [SourceEdit(path=path, before=before, after=after)]
    return result


def test_edits_produce_complete_download_without_claiming_verification(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=FakeLuna([edited()]))) as client:
        bounty = post_bounty(client).json()['id']
        before = client.get('/api/v1/me/stats').json()
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip()})
        assert get_run(client, bounty)['status'] == 'ready'
        with zipfile.ZipFile(io.BytesIO(client.get(f'/api/v1/bounties/{bounty}/ai/artifact').content)) as archive:
            assert 'return a + b' in archive.read('workspace/calc.py').decode()
            assert '-    return a - b' in archive.read('changes.patch').decode()
            assert 'No build or tests have been run' in archive.read('START_HERE.md').decode()
        assert client.get(f'/api/v1/bounties/{bounty}').json()['phase'] != 'Closed'
        after = client.get('/api/v1/me/stats').json()
        assert (before['available_gold'], before['reserved_gold']) == (after['available_gold'], after['reserved_gold'])


@pytest.mark.parametrize('path,before,after,source', [
    ('../escape.py', 'old', 'new', {'../escape.py': 'old'}),
    ('missing.py', 'old', 'new', {'calc.py': 'old'}),
    ('calc.py', 'old', 'new', {'calc.py': 'old old'}),
    ('calc.py', 'absent', 'new', {'calc.py': 'old'}),
    ('calc.py', 'old', 'old', {'calc.py': 'old'}),
])
def test_edits_reject_unsafe_missing_ambiguous_and_noop_matches(path, before, after, source):
    original = dict(source)
    with pytest.raises(Exception):
        materialize_edits(edited(path, before, after), source)
    assert source == original


def test_edits_reject_conflicting_full_files_and_nonimplementation():
    from app.ai import SourceFile
    result = edited()
    result.files = [SourceFile(path='calc.py', content='something else')]
    with pytest.raises(ValueError, match='overlap'):
        materialize_edits(result, {'calc.py': 'return a - b'})
    result = edited()
    result.action = 'evidence'
    with pytest.raises(ValueError, match='Only implementation'):
        materialize_edits(result, {'calc.py': 'return a - b'})


def test_multiple_edits_preserve_untouched_source_and_plan_gate(tmp_path):
    source = {'calc.py': '# keep me\ndef add(a, b):\n    return a - b\n'}
    result = edited()
    result.edits.append(SourceEdit(path='calc.py', before='def add(a, b):', after='def add(a, b):  # addition'))
    materialize_edits(result, source)
    assert source['calc.py'].endswith('return a - b\n')
    assert len(result.files) == 1 and result.files[0].content.startswith('# keep me\n')
    result.plan[0].files = ['unrelated.py']
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=FakeLuna([result]))) as client:
        bounty = post_bounty(client).json()['id']
        write(client, f'/bounties/{bounty}/ai/start', {'source_zip': source_zip(source)})
        assert get_run(client, bounty)['status'] == 'failed'
