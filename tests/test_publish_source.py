"""Run the real PowerShell source resolver against disposable Git repos."""
from pathlib import Path
import shutil
import subprocess

import pytest


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repositories(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    git(source, 'init', '-b', 'main')
    git(source, 'config', 'user.name', 'Fixture')
    git(source, 'config', 'user.email', 'fixture@example.invalid')
    (source / 'fixture.txt').write_text('baseline', encoding='utf-8')
    git(source, 'add', 'fixture.txt')
    git(source, 'commit', '-m', 'Baseline')
    subprocess.run(['git', 'clone', str(source), str(target)], check=True, capture_output=True)
    (source / 'fixture.txt').write_text('candidate', encoding='utf-8')
    git(source, 'commit', '-am', 'Candidate')
    return source, target, git(source, 'rev-parse', 'HEAD')


def resolve(source, target, commit):
    shell = shutil.which('pwsh')
    if not shell:
        pytest.skip('PowerShell 7 is required for publisher tests')
    script = str(Path('scripts/publish-demo.ps1').resolve()).replace("'", "''")
    command = f"""$ErrorActionPreference='Stop';
$tokens=$null; $errors=$null;
$ast=[System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$tokens,[ref]$errors);
if($errors){{throw 'Publisher parse failed'}};
$function=$ast.Find({{param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-PublishCommit'}},$true);
. ([scriptblock]::Create($function.Extent.Text));
Get-PublishCommit -TargetRepository '{str(target).replace("'", "''")}' -SourceRepository '{str(source).replace("'", "''")}' -SourceCommit '{commit}'
"""
    return subprocess.run([shell, '-NoProfile', '-Command', command], capture_output=True, text=True)


def test_local_release_is_pinned_without_changing_origin_or_target_head(repositories):
    source, target, commit = repositories
    before = git(target, 'rev-parse', 'HEAD'), git(target, 'config', '--get', 'remote.origin.url'), git(target, 'rev-parse', 'origin/main')
    result = resolve(source, target, commit)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == commit
    assert (git(target, 'rev-parse', 'HEAD'), git(target, 'config', '--get', 'remote.origin.url'), git(target, 'rev-parse', 'origin/main')) == before
    assert git(target, 'rev-parse', 'FETCH_HEAD') == commit


def test_local_release_rejects_unpinned_source_before_fetch(repositories):
    source, target, _ = repositories
    result = resolve(source, target, 'main')
    assert result.returncode != 0 and 'exact full tested commit SHA' in result.stderr
    assert not (target / '.git' / 'FETCH_HEAD').exists()


def test_local_release_rejects_divergence_without_changing_checkout(repositories):
    source, target, commit = repositories
    git(target, 'config', 'user.name', 'Fixture')
    git(target, 'config', 'user.email', 'fixture@example.invalid')
    (target / 'local.txt').write_text('preserved', encoding='utf-8')
    git(target, 'add', 'local.txt')
    git(target, 'commit', '-m', 'Local branch')
    before = git(target, 'rev-parse', 'HEAD')
    result = resolve(source, target, commit)
    assert result.returncode != 0 and 'cannot fast-forward' in result.stderr
    assert git(target, 'rev-parse', 'HEAD') == before
    assert (target / 'local.txt').read_text(encoding='utf-8') == 'preserved'


def test_existing_origin_main_default_remains_supported(repositories):
    source, target, commit = repositories
    before = git(target, 'rev-parse', 'HEAD')
    result = resolve('', target, '')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == commit
    assert git(target, 'rev-parse', 'HEAD') == before
    assert git(target, 'rev-parse', 'origin/main') == commit
