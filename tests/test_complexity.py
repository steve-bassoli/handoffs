import pytest

from app.complexity import commit, validate_plan
from test_imports import fixture_repository


def step(identifier='leaf', complexity='LOW', children=None, files=None):
    return {'id': identifier, 'title': 'One bounded change', 'complexity': complexity,
            'children': children or [], 'files': files or []}


def tree(prefix='root'):
    return [step(prefix, 'HIGH', [step(f'{prefix}.m{i}', 'MEDIUM', [step(f'{prefix}.l{i}{j}') for j in range(3)]) for i in range(3)])]


def test_medium_has_three_low_leaves_and_low_is_canonical():
    normalized, leaves = validate_plan(tree())
    assert len(leaves) == 9
    assert normalized[0]['complexity'] == 'HIGH'
    assert validate_plan([step()])[1][0]['complexity'] == 'LOW'


@pytest.mark.parametrize('count', [3])
def test_high_can_split_into_multiple_highs_that_eventually_reach_low(count):
    plan = [step('parent', 'HIGH', [tree(f'branch{i}')[0] for i in range(count)])]
    normalized, leaves = validate_plan(plan)
    assert len(normalized[0]['children']) == count
    assert len(leaves) == count * 9
    assert all(leaf['complexity'] == 'LOW' for leaf in leaves)


@pytest.mark.parametrize('bad', [
    [step('root', 'HIGH')], [step('root', 'MEDIUM', [step('s1'), step('s2')])],
    [step('root', 'MEDIUM', [step('s1'), step('s2'), step('s3'), step('s4')])],
    [step('root', 'HIGH', [step('s1'), step('s2'), step('s3')])],
    [step('root', 'LOW', [step('child')])], [step('same'), step('same')],
    [step(files=['../outside'])], [step(complexity='easy')],
    [step(complexity='SMALL')], [step(complexity='LARGE')], [step('root', 'HIGH', [tree('child')[0]])],
    [step('root', 'HIGH', [tree(f'h{i}')[0] for i in range(2)])],
    [step('root', 'HIGH', [tree(f'h{i}')[0] for i in range(4)])],
    [step('root', 'HIGH', [tree('h')[0], step('medium', 'MEDIUM', [step('l1'), step('l2'), step('l3')])])],
])
def test_invalid_plans_fail_closed(bad):
    with pytest.raises(ValueError):
        validate_plan(bad)


def test_only_selected_low_leaf_can_commit_its_declared_staged_files(tmp_path):
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
    commit(repo, plan, 'one', 'Commit one LOW leaf')
    message = git('log', '-1', '--format=%B')
    assert 'Complexity: LOW' in message and 'Plan-step: one' in message
    assert git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD') == 'one.txt'
    assert (repo / 'two.txt').read_text() == 'two'


def test_same_leaf_cannot_commit_twice_even_with_new_staged_content(tmp_path):
    repo, _, git = fixture_repository(tmp_path)
    plan = [step('fix', files=['one.txt'])]
    (repo / 'one.txt').write_text('first', encoding='utf-8')
    git('add', 'one.txt')
    commit(repo, plan, 'fix', 'One bounded implementation')
    before = git('rev-parse', 'HEAD')
    (repo / 'one.txt').write_text('second', encoding='utf-8')
    git('add', 'one.txt')
    with pytest.raises(ValueError, match='already has its one commit'):
        commit(repo, plan, 'fix', 'Must not repeat')
    assert git('rev-parse', 'HEAD') == before
    assert git('diff', '--cached', '--name-only') == 'one.txt'
    assert not (repo / '.git/handoffs-commit.lock').exists()


def test_verification_leaf_cannot_commit_or_declare_commit_files(tmp_path):
    repo, _, _ = fixture_repository(tmp_path)
    leaf = {**step('evidence'), 'work_type': 'verification'}
    assert validate_plan([leaf])[1][0]['work_type'] == 'verification'
    with pytest.raises(ValueError, match='implementation LOW'):
        commit(repo, [leaf], 'evidence', 'No forced commit')
    with pytest.raises(ValueError, match='verification leaves'):
        validate_plan([{**leaf, 'files': ['report.md']}])


def test_managed_commit_lock_fails_closed(tmp_path):
    repo, _, git = fixture_repository(tmp_path)
    lock = repo / '.git/handoffs-commit.lock'
    lock.write_text('other worker', encoding='utf-8')
    before = git('rev-parse', 'HEAD')
    with pytest.raises(ValueError, match='lock needs inspection'):
        commit(repo, [step(files=['one.txt'])], 'leaf', 'No race')
    assert git('rev-parse', 'HEAD') == before
    assert lock.read_text() == 'other worker'
