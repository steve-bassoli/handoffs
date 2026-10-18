import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('publication', Path(__file__).parents[1] / 'scripts/publish-task.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def repositories(tmp_path):
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
    local = tmp_path / 'work'
    subprocess.run(['git', 'init', '-b', 'main', str(local)], check=True, capture_output=True)
    git(local, 'config', 'user.name', 'Fixture')
    git(local, 'config', 'user.email', 'fixture@example.invalid')
    git(local, 'remote', 'add', 'origin', str(remote))
    (local / 'task.txt').write_text('authorized fixture')
    git(local, 'add', 'task.txt')
    git(local, 'commit', '-m', 'Fixture task')
    return local, remote, git(local, 'rev-parse', 'HEAD'), tmp_path / 'receipt.json'


def publish(repo, **changes):
    local, remote, commit, receipt = repo
    args = dict(repository=local, remote='origin', branch='main', expected_url=str(remote),
                commit=commit, receipt=receipt, authorized=True)
    args.update(changes)
    result = publication.publish(**args)
    assert json.loads(receipt.read_text()) == result
    return result


def test_push_exact_commit_and_resume_without_recommit(repositories):
    local, remote, commit, _ = repositories
    (local / 'unrelated.txt').write_text('leave untracked')
    result = publish(repositories)
    assert result['published'] and result['remote_commit'] == commit
    assert git(remote, 'rev-parse', 'refs/heads/main') == commit
    assert git(local, 'status', '--porcelain') == '?? unrelated.txt'
    again = publish(repositories)
    assert again['published'] and not again['push_attempted']


@pytest.mark.parametrize('changes', [dict(authorized=False), dict(branch='other'),
    dict(expected_url='not-the-intended-repository'), dict(commit='0' * 40)])
def test_missing_authority_or_wrong_destination_never_pushes(repositories, changes):
    result = publish(repositories, **changes)
    assert result['state'] == 'blocked' and not result['published'] and not result['push_attempted']
    assert result['next_action']


def test_rejected_non_fast_forward_is_visible_and_preserves_commit(repositories, tmp_path):
    local, remote, commit, _ = repositories
    assert publish(repositories)['published']
    other = tmp_path / 'other'
    subprocess.run(['git', 'clone', '--branch', 'main', str(remote), str(other)], check=True, capture_output=True)
    git(other, 'config', 'user.name', 'Other fixture')
    git(other, 'config', 'user.email', 'other@example.invalid')
    (other / 'other.txt').write_text('independent change')
    git(other, 'add', '.')
    git(other, 'commit', '-m', 'Remote advance')
    git(other, 'push', 'origin', 'main')
    remote_commit = git(other, 'rev-parse', 'HEAD')
    (local / 'task.txt').write_text('next authorized fixture')
    git(local, 'add', 'task.txt')
    git(local, 'commit', '-m', 'Local advance')
    new_commit = git(local, 'rev-parse', 'HEAD')
    result = publish(repositories, commit=new_commit)
    assert not result['published'] and result['push_attempted'] and result['state'] == 'blocked'
    assert git(local, 'rev-parse', 'HEAD') == new_commit
    assert git(remote, 'rev-parse', 'refs/heads/main') == remote_commit
    assert 'push' in result['error'] and result['next_action']
