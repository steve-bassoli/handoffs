import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from app import ase_conformance as ase


@pytest.fixture(params=['native', 'fallback'])
def checkout(tmp_path, monkeypatch, request):
    if request.param == 'fallback':
        monkeypatch.setattr(ase, '_descriptor_reads_available', lambda: False)
    (tmp_path / 'app').mkdir()
    (tmp_path / 'app/complexity.py').write_text(ase.VALIDATOR_SOURCE, encoding='utf-8')
    (tmp_path / 'PROJECT_CHARTER.md').write_text('Human consent and approval. PRESSURE REST protected.', encoding='utf-8')
    return tmp_path


def first(root):
    return ase.build_scorecard(root)['properties'][0]


def test_passing_baseline_and_contract(checkout):
    model = ase.build_scorecard(checkout)
    assert set(model) == {'schema_version', 'scope', 'properties', 'limitations'}
    assert model['schema_version'] == 'ase-narrow-v1'
    assert [r['id'] for r in model['properties']] == ['decomposition', 'human_gates', 'humane_limits']
    row = model['properties'][0]
    assert row['status'] == 'pass' and row['conflicts'] == []
    digest = hashlib.sha256((checkout / 'app/complexity.py').read_bytes()).hexdigest()
    assert row['evidence'] == [dict(path='app/complexity.py', sha256=digest, kind=k)
                               for k in ('source', 'behavior')]
    assert 'source-extracted validator AST and bounded suite only' in row['scope']
    assert 'enclosing-module execution, runtime bindings and downstream enforcement are not assessed' in row['scope']
    assert all(r['status'] == 'partial' for r in model['properties'][1:])


@pytest.mark.parametrize('parent,children', [
    ('HIGH', ['HIGH', 'HIGH']), ('HIGH', ['MEDIUM', 'MEDIUM']),
    ('MEDIUM', ['LOW', 'LOW'])])
def test_valid_direct_probe(parent, children):
    raw = ase.VALIDATOR_SOURCE.encode()
    validator = ase._extract_validator(raw, hashlib.sha256(raw).hexdigest())
    assert validator(parent, children) == children[0]


@pytest.mark.parametrize('parent,children', [
    ('HIGH', []), ('HIGH', ['HIGH']), ('HIGH', ['HIGH', 'MEDIUM']),
    ('HIGH', ['LOW', 'LOW']), ('MEDIUM', ['HIGH', 'HIGH']),
    ('MEDIUM', ['MEDIUM', 'MEDIUM']), ('LOW', ['LOW', 'LOW']),
    ('LOW', ['HIGH', 'HIGH']), ('LOW', ['MEDIUM', 'MEDIUM']),
    ('UNKNOWN', ['LOW', 'LOW'])])
def test_invalid_direct_probe(parent, children):
    raw = ase.VALIDATOR_SOURCE.encode()
    validator = ase._extract_validator(raw, hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):
        validator(parent, children)


@pytest.mark.parametrize('old,new', [
    ("'LOW': ()", "'LOW': ('HIGH',)"),
    ("'LOW': ()", "'LOW': ('MEDIUM',)"),
    ("'MEDIUM': ('LOW',)", "'MEDIUM': ('LOW', 'MEDIUM')"),
    ('MIN_CHILDREN = 2', 'MIN_CHILDREN = 1')])
def test_temporary_source_conflicts(checkout, old, new):
    assert first(checkout)['status'] == 'pass'
    path = checkout / 'app/complexity.py'
    source = path.read_text(encoding='utf-8')
    assert old in source
    path.write_text(source.replace(old, new), encoding='utf-8')
    row = first(checkout)
    assert row['status'] == 'partial'
    assert 'invalid split accepted' in row['conflicts']
    assert [e['kind'] for e in row['evidence']] == ['source']
    assert row['evidence'][0]['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_binding_mismatch():
    with pytest.raises(ValueError, match='source-binding mismatch'):
        ase._extract_validator(ase.VALIDATOR_SOURCE.encode(), '0' * 64)


@pytest.mark.parametrize('mode', ['accept', 'reject'])
def test_broken_validator_cannot_pass(checkout, monkeypatch, mode):
    assert first(checkout)['status'] == 'pass'
    def broken(parent, children):
        if mode == 'reject':
            raise ValueError('broken')
        return children[0] if children else 'LOW'
    monkeypatch.setattr(ase, '_extract_validator', lambda raw, digest: broken)
    row = first(checkout)
    assert row['status'] == 'partial' and row['conflicts']
    assert all(e['kind'] != 'behavior' for e in row['evidence'])


@pytest.mark.parametrize('fallback', [False, True])
def test_missing_files(tmp_path, monkeypatch, fallback):
    if fallback:
        monkeypatch.setattr(ase, '_descriptor_reads_available', lambda: False)
    model = ase.build_scorecard(tmp_path)
    assert all(row['status'] == 'gap' for row in model['properties'])
    assert all(row['evidence'] == [] for row in model['properties'])
    assert all(row['reason'] == 'FileNotFoundError: source unavailable or unsupported'
               for row in model['properties'])


def test_unsupported_ast_cannot_pass(checkout):
    (checkout / 'app/complexity.py').write_text(
        'def validate_task_split(parent, levels):\n    return levels[0]\n', encoding='utf-8')
    row = first(checkout)
    assert row['status'] == 'partial'
    assert row['reason'] == 'Probe unavailable: ValueError'


def test_enclosing_module_not_executed(checkout):
    path = checkout / 'app/complexity.py'
    path.write_text('raise RuntimeError("must not execute")\n' + ase.VALIDATOR_SOURCE, encoding='utf-8')
    assert first(checkout)['status'] == 'pass'


def test_bounded_source(checkout):
    path = checkout / 'app/complexity.py'
    path.write_bytes(b'x' * (ase.LIMIT + 1))
    assert first(checkout)['status'] == 'gap'


@pytest.mark.parametrize('component', ['', 'app', 'app/complexity.py'])
@pytest.mark.parametrize('kind', ['symlink', 'reparse'])
def test_fallback_rejects_link_metadata(checkout, monkeypatch, component, kind):
    # No Windows symlink privilege required: simulate lstat metadata, not reads.
    monkeypatch.setattr(ase, '_descriptor_reads_available', lambda: False)
    target = checkout / component if component else checkout
    original = Path.lstat
    def fake_lstat(self, *args, **kwargs):
        if self == target:
            return SimpleNamespace(
                st_mode=stat.S_IFLNK if kind == 'symlink' else stat.S_IFDIR,
                st_file_attributes=0x400 if kind == 'reparse' else 0)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', fake_lstat)
    def forbidden_open(*args, **kwargs):
        raise AssertionError('must reject link metadata before opening content')
    monkeypatch.setattr(ase.os, 'open', forbidden_open)
    with pytest.raises(ValueError, match='link or reparse'):
        ase._read(str(checkout), 'app/complexity.py')


@pytest.mark.parametrize('relative', [
    '../outside.py', '/outside.py', 'app/../PROJECT_CHARTER.md',
    'app/other.py', 'app\\complexity.py'])
def test_only_exact_allowlist_is_read(tmp_path, monkeypatch, relative):
    def forbidden(*args, **kwargs):
        raise AssertionError('non-allowlisted path reached a reader')
    monkeypatch.setattr(ase, '_read_descriptor', forbidden)
    monkeypatch.setattr(ase, '_read_fallback', forbidden)
    with pytest.raises(ValueError, match='not allowlisted'):
        ase._read(str(tmp_path), relative)


def test_fallback_rejects_directory_source(checkout, monkeypatch):
    monkeypatch.setattr(ase, '_descriptor_reads_available', lambda: False)
    path = checkout / 'app/complexity.py'
    path.unlink()
    path.mkdir()
    assert first(checkout)['status'] == 'gap'


def test_cli_json(checkout, capsys):
    ase.main(['--repo-root', str(checkout)])
    assert json.loads(capsys.readouterr().out) == ase.build_scorecard(checkout)
