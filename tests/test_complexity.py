import pytest

from app.complexity import commit, validate_plan
from test_imports import fixture_repository


def step(identifier='leaf', complexity='SMALL', children=None, files=None):
    return {'id': identifier, 'title': 'One bounded change', 'complexity': complexity,
            'children': children or [], 'files': files or []}


def tree():
    return [step('root', 'HIGH', [step(f'm{i}', 'MEDIUM', [step(f's{i}{j}') for j in range(3)]) for i in range(3)])]


def test_exact_three_way_decomposition_and_low_alias():
    normalized, leaves = validate_plan(tree())
    assert len(leaves) == 9
    assert normalized[0]['complexity'] == 'HIGH'
    assert validate_plan([step(complexity='LOW')])[1][0]['complexity'] == 'SMALL'


@pytest.mark.parametrize('bad', [
    [step('root', 'HIGH')], [step('root', 'MEDIUM', [step('s1'), step('s2')])],
    [step('root', 'MEDIUM', [step('s1'), step('s2'), step('s3'), step('s4')])],
    [step('root', 'HIGH', [step('s1'), step('s2'), step('s3')])],
    [step('root', 'SMALL', [step('child')])], [step('same'), step('same')],
    [step(files=['../outside'])], [step(complexity='easy')],
])
def test_invalid_plans_fail_closed(bad):
    with pytest.raises(ValueError):
        validate_plan(bad)


def test_only_selected_small_leaf_can_commit_its_declared_staged_files(tmp_path):
    repo, _, git = fixture_repository(tmp_path)
    plan = [step('parent', 'MEDIUM', [step('one', files=['one.txt']), step('two', files=['two.txt']), step('three')])]
    (repo / 'one.txt').write_text('one', encoding='utf-8')
    (repo / 'two.txt').write_text('two', encoding='utf-8')
    git('add', '.')
    before = git('rev-parse', 'HEAD')
    for identifier in ('parent', 'one', 'three'):
        with pytest.raises(ValueError):
            commit(repo, plan, identifier, 'Must not commit')
        assert git('rev-parse', 'HEAD') == before
    git('restore', '--staged', 'two.txt')
    commit(repo, plan, 'one', 'Commit one SMALL leaf')
    message = git('log', '-1', '--format=%B')
    assert 'Complexity: SMALL' in message and 'Plan-step: one' in message
    assert git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD') == 'one.txt'
    assert (repo / 'two.txt').read_text() == 'two'
