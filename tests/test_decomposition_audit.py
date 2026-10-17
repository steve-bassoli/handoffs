"""Synthetic SQLite instrumentation is not actual Service/plugin proof."""
import json
from pathlib import Path
import sqlite3

import pytest

from app.decomposition_audit import (
    DEFAULT_HIGH_CAVEAT, SOURCE, build_decomposition_audit,
)

STAMP = '2026-01-01T00:00:00Z'
CAVEAT = 'Service.detail defaults missing complexity to HIGH.'


def build(reader):
    return build_decomposition_audit(reader, checked_at=STAMP, scope='authorized')


def test_canonical_fixture():
    path = Path(__file__).parent / 'fixtures' / 'decomposition_audit_v1.json'
    fixture = json.loads(path.read_text(encoding='utf-8'))
    rows = [{'parent': v['ticket_id'], 'reason': v['message']}
            for v in fixture['violations']]
    result = build_decomposition_audit(
        lambda: rows, checked_at=fixture['checked_at'], scope=fixture['scope'])
    assert {k: v for k, v in result.items() if k != 'limitations'} == {
        k: v for k, v in fixture.items() if k != 'limitations'}
    assert set(fixture['limitations']) <= set(result['limitations'])
    assert DEFAULT_HIGH_CAVEAT == CAVEAT
    assert CAVEAT in result['limitations']


def test_shape_projection_order_deduplication_and_single_call():
    calls = []
    rows = [
        {'parent': 'b', 'reason': 'z', 'children': {'private': 'LOW'}},
        {'parent': 'a', 'reason': 'y', 'private': 'omit'},
        {'parent': 'a', 'reason': 'x'}, {'parent': 'a', 'reason': 'x'},
    ]
    original = json.dumps(rows, sort_keys=True)

    def reader():
        calls.append(True)
        return rows

    result = build(reader)
    assert calls == [True]
    assert set(result) == {
        'version', 'source', 'checked_at', 'scope', 'status',
        'violations', 'error', 'limitations',
    }
    assert (result['version'], result['source']) == (1, SOURCE)
    assert (result['checked_at'], result['scope']) == (STAMP, 'authorized')
    assert result['status'] == 'findings' and result['error'] is None
    assert CAVEAT in result['limitations']
    assert result['violations'] == [
        {'ticket_id': 'a', 'message': 'x'},
        {'ticket_id': 'a', 'message': 'y'},
        {'ticket_id': 'b', 'message': 'z'},
    ]
    assert json.dumps(rows, sort_keys=True) == original


def test_checked_empty_is_not_unavailable():
    result = build(lambda: [])
    assert result['status'] == 'checked_empty'
    assert result['violations'] == [] and result['error'] is None
    assert CAVEAT in result['limitations']


@pytest.mark.parametrize('raw', [
    None, {}, (), 'secret', [None], [{}],
    [{'parent': 1, 'reason': 'bad'}], [{'parent': 'a', 'reason': None}],
    [{'parent': '', 'reason': 'bad'}], [{'parent': 'a', 'reason': ' '}],
    [{'parent': 'a', 'reason': 'ok'}, {}],
])
def test_malformed_results_are_unavailable(raw):
    result = build(lambda: raw)
    assert result['status'] == 'unavailable'
    assert result['violations'] is None
    assert result['error'] == 'Audit unavailable'
    assert CAVEAT in result['limitations']


def test_exception_sanitized_without_retry():
    calls = []

    def reader():
        calls.append(True)
        raise RuntimeError('secret-token and private SQL')

    result = build(reader)
    assert calls == [True]
    assert result['status'] == 'unavailable' and result['violations'] is None
    assert result['error'] == 'Audit unavailable'
    assert CAVEAT in result['limitations']
    assert 'secret-token' not in json.dumps(result)


def test_invalid_metadata_does_not_call_reader():
    calls = []
    with pytest.raises(TypeError):
        build_decomposition_audit(lambda: calls.append(True),
                                  checked_at=None, scope='authorized')
    assert calls == []


def test_noncallable_is_unavailable():
    result = build(None)
    assert result['status'] == 'unavailable' and result['violations'] is None
    assert CAVEAT in result['limitations']


def test_synthetic_sqlite_reader_has_no_mutations(tmp_path):
    # Test-only setup writes precede instrumentation; no Service is instantiated.
    db = sqlite3.connect(tmp_path / 'audit.sqlite')
    try:
        for table in ('events', 'operations', 'gold_entries'):
            db.execute(f'CREATE TABLE {table} (value TEXT)')
            db.execute(f'INSERT INTO {table} VALUES (?)', ('sentinel',))
        db.commit()
        before = list(db.iterdump())
        writes = []
        mutation_codes = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE,
                          sqlite3.SQLITE_DELETE}

        def authorize(action, arg1, arg2, database, trigger):
            if action in mutation_codes:
                writes.append((action, arg1))
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)
        db.execute('PRAGMA query_only=ON')
        statements = []
        db.set_trace_callback(statements.append)

        def reader():
            return [dict(parent=row[0], reason=row[1]) for row in
                    db.execute("SELECT 'p', 'synthetic finding'")]

        changes = db.total_changes
        assert build(reader)['status'] == 'findings'
        assert writes == [] and db.total_changes == changes
        assert list(db.iterdump()) == before
        assert statements.count("SELECT 'p', 'synthetic finding'") == 1
    finally:
        db.close()
