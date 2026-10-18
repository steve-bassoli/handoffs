"""Bounded source guards and synthetic SQLite boundary tests, not live DB proof.

The AST check is lexical evidence, not control-flow dominance or general SQL
analysis. Only literal first-argument exec_driver_sql INSERTs are recognized.
"""
import ast
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3

import pytest

from app import spawn
from app.ai import validate_proposals
from app.complexity import validate_bounty_split


ROOT = Path(__file__).resolve().parents[1]
REVIEWED = {'app/services.py', 'app/spawn.py', 'app/ai.py', 'app/importer.py'}
VALIDATORS = {'validate_bounty_split', 'validate_proposals'}
INSERT = re.compile(r'^\s*INSERT\s+INTO\s+bounties\b', re.I)
COLUMNS = re.compile(r'^\s*INSERT\s+INTO\s+bounties\s*\(([^)]*)\)', re.I)


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def exec_driver_sql(self, sql, parameters=()):
        return self.raw.execute(sql, parameters)


class LocalDatabase:
    """Minimal spawn adapter: actual SQLite commit/rollback, no app schema claim."""
    def __init__(self, database):
        self.raw = sqlite3.connect(str(database))
        self.engine = self

    @contextmanager
    def write(self):
        try:
            with self.raw:
                yield Connection(self.raw)
        finally:
            pass

    def dispose(self):
        self.raw.close()


class LocalService:
    """Only detail/event are faked; spawn_children itself is not replaced."""
    def __init__(self, database, verifier):
        self.database = database

    def detail(self, connection, identifier):
        row = connection.exec_driver_sql(
            'SELECT id, complexity FROM bounties WHERE id=?', (identifier,)
        ).fetchone()
        assert row is not None
        return {'id': row[0], 'complexity': row[1], 'status': 'open',
                'repository': 'synthetic', 'context_links': [],
                'criteria': ['parent criterion']}

    def event(self, connection, identifier, kind, actor, status, data):
        connection.exec_driver_sql(
            'INSERT INTO events VALUES (?,?,?,?,?)',
            (identifier, kind, actor, status, spawn.encode(data)))


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / 'boundary.sqlite'
    with sqlite3.connect(str(path)) as connection:
        connection.execute('''CREATE TABLE bounties (
            id TEXT PRIMARY KEY, title TEXT, goal TEXT, criteria TEXT,
            repository TEXT, context_links TEXT, creator TEXT, target TEXT,
            gold INTEGER, created_at TEXT, funded INTEGER, parent_id TEXT,
            complexity TEXT)''')
        connection.execute('''CREATE TABLE events (
            ticket TEXT, kind TEXT, actor TEXT, status TEXT, data TEXT)''')
    monkeypatch.setattr(spawn, 'Database', LocalDatabase)
    monkeypatch.setattr(spawn, 'Service', LocalService)
    monkeypatch.setattr(spawn, 'DemoDeliveryVerifier', lambda: object())
    return path


def seed(path, level):
    with sqlite3.connect(str(path)) as connection:
        connection.execute(
            'INSERT INTO bounties (id,title,complexity) VALUES (?,?,?)',
            ('parent', 'Synthetic parent', level))
        connection.execute('INSERT INTO events VALUES (?,?,?,?,?)',
                           ('parent', 'sentinel', 'tester', 'open', '{}'))


def snapshot(path):
    with sqlite3.connect(str(path)) as connection:
        return tuple(tuple(connection.execute(
            'SELECT * FROM ' + table + ' ORDER BY rowid'))
            for table in ('bounties', 'events'))


def proposals(levels):
    return [{'title': 'Child ' + str(index), 'goal': 'Bounded work',
             'criteria': ['Demonstrate result'], 'complexity': level,
             'work_type': 'implementation', 'parent_criteria': [0]}
            for index, level in enumerate(levels)]


CASES = [
    pytest.param(parent, [child] * count, True,
                 id=f'{parent}-to-{count}-{child}')
    for parent, child in [('HIGH', 'HIGH'), ('HIGH', 'MEDIUM'),
                          ('MEDIUM', 'LOW')]
    for count in (2, 4)
] + [
    pytest.param('HIGH', ['HIGH'], False, id='singleton-high'),
    pytest.param('MEDIUM', ['LOW'], False, id='singleton-medium'),
    pytest.param('HIGH', ['HIGH', 'MEDIUM'], False, id='mixed-high'),
    pytest.param('MEDIUM', ['LOW', 'MEDIUM'], False, id='mixed-medium'),
    pytest.param('HIGH', ['LOW', 'LOW'], False, id='wrong-high'),
    pytest.param('MEDIUM', ['HIGH', 'HIGH'], False, id='wrong-medium'),
    pytest.param('LOW', ['LOW', 'LOW'], False, id='low-parent-two'),
    pytest.param('LOW', ['HIGH'] * 4, False, id='low-parent-four'),
]


@pytest.mark.parametrize('parent,levels,accepted', CASES)
def test_split_boundaries(database, parent, levels, accepted):
    seed(database, parent)
    children = proposals(levels)
    task = {'complexity': parent, 'criteria': ['parent criterion']}
    before = snapshot(database)
    if accepted:
        assert validate_bounty_split(parent, levels) == levels[0]
        validate_proposals(task, children, 'Each responsibility is distinct.')
        assert snapshot(database) == before  # Pure AI validation performs no writes.
        created = spawn.spawn_children(
            str(database), 'parent', children, 'tester', 'boundary-test')
        assert len(created) == len(levels) == len(set(created))
        after = snapshot(database)
        assert len(after[0]) == len(before[0]) + len(levels)
        assert len(after[1]) == len(before[1]) + len(levels) + 1
        child_rows = {row[0]: row for row in after[0] if row[0] in created}
        assert set(child_rows) == set(created)
        assert all(row[11] == 'parent' for row in child_rows.values())
        assert [row[1] for row in after[1][1:]] == (
            ['followup_confirmed'] * len(levels) + ['followups_confirmed'])
    else:
        with pytest.raises(ValueError):
            validate_bounty_split(parent, levels)
        with pytest.raises(ValueError):
            validate_proposals(task, children, 'Distinct responsibilities.')
        assert snapshot(database) == before
        with pytest.raises((ValueError, spawn.RuleError)):
            spawn.spawn_children(str(database), 'parent', children,
                                 'tester', 'boundary-test')
        assert snapshot(database) == before


def test_late_invalid_child_rolls_back_rows_and_events(database):
    seed(database, 'HIGH')
    children = proposals(['MEDIUM', 'MEDIUM'])
    children[-1]['goal'] = ''
    before = snapshot(database)
    with pytest.raises(ValueError, match='Each child needs'):
        spawn.spawn_children(str(database), 'parent', children,
                             'tester', 'boundary-test')
    assert snapshot(database) == before


def inserted_sql(node):
    if (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'exec_driver_sql' and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and INSERT.match(node.args[0].value)):
        return node.args[0].value
    return None


def named_validator(node):
    return (isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in VALIDATORS)


def scan(source):
    """Discover all recognized calls, then reconcile a bounded lexical pass.

    Only standalone named validator calls count. A validator earlier in a try
    body counts lexically after that try, but is NOT dominance evidence.
    Exception handlers and non-statement expression scopes fail closed.
    Nested functions have independent validator state. Call identity, not line
    number, reconciles discovery, preserving multiple calls on a single line.
    """
    tree = ast.parse(source)
    discovered = {id(node): node for node in ast.walk(tree)
                  if inserted_sql(node) is not None}
    classified = {}

    def record(node, owner, guarded):
        key = id(node)
        assert key not in classified, 'duplicate lexical accounting'
        classified[key] = (owner, guarded)

    def expression_nodes(node):
        # Do not accidentally classify writes in comprehensions or lambdas.
        if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp,
                             ast.DictComp, ast.GeneratorExp)):
            return
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.stmt, ast.ExceptHandler)):
                yield from expression_nodes(child)

    def block(statements, owner, guarded=False):
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef)):
                continue  # Each function is visited independently below.
            for node in expression_nodes(statement):
                if id(node) in discovered:
                    record(node, owner, guarded)
            if named_validator(statement):
                guarded = True
            for field, value in ast.iter_fields(statement):
                if field == 'handlers':
                    continue  # Discovered calls remain explicitly unhandled.
                if isinstance(value, list) and value and all(
                        isinstance(item, ast.stmt) for item in value):
                    guarded = block(value, owner, guarded)
        return guarded

    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            block(function.body, function.name)
    result = []
    for key, node in discovered.items():
        owner, guarded = classified.get(key, ('<unhandled>', False))
        sql = inserted_sql(node)
        match = COLUMNS.match(sql)
        columns = ({part.strip().casefold() for part in match.group(1).split(',')}
                   if match else None)
        result.append({'owner': owner, 'guarded': guarded,
                       'line': node.lineno, 'columns': columns})
    return result


def violations(module, sites):
    problems = []
    for site in sites:
        label = f"{module}:{site['line']}:{site['owner']}"
        if module not in REVIEWED:
            problems.append(label + ': unclassified direct write')
            continue
        if site['owner'] == '<unhandled>' or site['columns'] is None:
            problems.append(label + ': unsupported placement or column syntax')
            continue
        if module == 'app/services.py':
            # The sole reviewed services write is the single-task post path.
            allowed = site['owner'] == 'do_post' and 'parent_id' not in site['columns']
        elif module == 'app/importer.py':
            # Legacy standalone import is not permission for child imports.
            allowed = 'parent_id' not in site['columns']
        elif module == 'app/spawn.py':
            allowed = site['owner'] == 'spawn_children' and site['guarded']
        else:
            allowed = site['owner'] == 'confirm' and site['guarded']
        if not allowed:
            problems.append(label + ': not a reviewed standalone/guarded write')
    return problems


def test_reviewed_direct_write_inventory():
    counts = Counter()
    problems = []
    for path in sorted((ROOT / 'app').rglob('*.py')):
        module = path.relative_to(ROOT).as_posix()
        sites = scan(path.read_text(encoding='utf-8-sig'))
        if sites:
            counts[module] += len(sites)
            problems.extend(violations(module, sites))
    assert counts == Counter({module: 1 for module in REVIEWED}), dict(counts)
    assert not problems, '\n'.join(problems)


def test_comment_only_copy_preserves_guard(tmp_path):
    original = (ROOT / 'app' / 'spawn.py').read_text(encoding='utf-8-sig')
    copy = tmp_path / 'spawn_comment.py'
    copy.write_text('# Comment-only mutant: validate_proposals is not a call.\n'
                    + original, encoding='utf-8')
    baseline = scan(original)
    changed = scan(copy.read_text(encoding='utf-8'))
    assert len(baseline) == len(changed) == 1
    assert not violations('app/spawn.py', baseline)
    assert not violations('app/spawn.py', changed)
    assert [{k: v for k, v in site.items() if k != 'line'} for site in baseline] == [
        {k: v for k, v in site.items() if k != 'line'} for site in changed]


@pytest.mark.parametrize('mutation', ['delete', 'after-write'])
def test_validator_mutants_fail_on_temporary_copies(tmp_path, mutation):
    tree = ast.parse((ROOT / 'app' / 'spawn.py').read_text(encoding='utf-8-sig'))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == 'spawn_children')
    matches = []
    for node in ast.walk(function):
        for _, value in ast.iter_fields(node):
            if isinstance(value, list):
                for index, statement in enumerate(value):
                    if named_validator(statement):
                        matches.append((value, index, statement))
    assert len(matches) == 1, 'Review changed spawn validator placement'
    statements, index, validator = matches[0]
    statements.pop(index)
    if mutation == 'after-write':
        # Same function and same transaction body, but after the child loop.
        statements.append(validator)
    ast.fix_missing_locations(tree)
    copy = tmp_path / ('spawn_' + mutation + '.py')
    copy.write_text(ast.unparse(tree), encoding='utf-8')
    sites = scan(copy.read_text(encoding='utf-8'))
    assert len(sites) == 1
    assert not sites[0]['guarded']
    assert violations('app/spawn.py', sites)


def test_exception_handler_write_is_discovered_but_unhandled():
    source = '''
def spawn_children():
    validate_bounty_split(parent, levels)
    try:
        pass
    except ValueError:
        c.exec_driver_sql('INSERT INTO bounties(id,parent_id) VALUES (?,?)')
'''
    sites = scan(source)
    assert len(sites) == 1
    assert sites[0]['owner'] == '<unhandled>'
    assert violations('app/spawn.py', sites)


def test_same_line_calls_are_independent_sites():
    source = '''
def spawn_children():
    validate_bounty_split(parent, levels)
    c.exec_driver_sql('INSERT INTO bounties(id,parent_id) VALUES (?,?)'); c.exec_driver_sql('INSERT INTO bounties(id,parent_id) VALUES (?,?)')
'''
    sites = scan(source)
    assert len(sites) == 2
    assert sites[0]['line'] == sites[1]['line']
    assert all(site['guarded'] for site in sites)
    assert not violations('app/spawn.py', sites)


def test_comment_validator_does_not_guard_a_write():
    sites = scan('''
def spawn_children():
    # validate_bounty_split(parent, levels)
    c.exec_driver_sql('INSERT INTO bounties(id,parent_id) VALUES (?,?)')
''')
    assert len(sites) == 1
    assert violations('app/spawn.py', sites)


def test_nested_validator_does_not_guard_outer_function():
    sites = scan('''
def spawn_children():
    def helper():
        validate_bounty_split(parent, levels)
    c.exec_driver_sql('INSERT INTO bounties(id,parent_id) VALUES (?,?)')
''')
    assert len(sites) == 1
    assert violations('app/spawn.py', sites)


def test_unknown_module_direct_write_fails_even_with_validator():
    sites = scan('''
def other():
    validate_bounty_split(parent, levels)
    c.exec_driver_sql('INSERT INTO bounties(id,parent_id) VALUES (?,?)')
''')
    assert len(sites) == 1
    assert 'unclassified direct write' in violations('app/unknown.py', sites)[0]


@pytest.mark.parametrize('column,accepted', [('parent_id', False),
                                            ('parent_identifier', True)])
def test_standalone_classification_uses_exact_column_token(column, accepted):
    sites = scan(f'''
def do_post():
    c.exec_driver_sql('  insert  into  bounties (id, {column}) VALUES (?,?)')
''')
    assert len(sites) == 1
    assert (not violations('app/services.py', sites)) is accepted
