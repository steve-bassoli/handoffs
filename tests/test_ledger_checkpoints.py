import hashlib
import json
import sqlite3

import pytest

from app import ledger_checkpoints as checkpoints


@pytest.fixture
def ledger(tmp_path):
    database = tmp_path / 'private ledger#%.sqlite'
    with sqlite3.connect(database) as connection:
        connection.executescript('''
            CREATE TABLE accounts(id TEXT PRIMARY KEY, user_id TEXT, kind TEXT);
            CREATE TABLE gold_transactions(id TEXT PRIMARY KEY, kind TEXT, task_id TEXT, created_at TEXT);
            CREATE TABLE gold_entries(seq INTEGER PRIMARY KEY, transaction_id TEXT, account_id TEXT, amount INTEGER);
            CREATE TABLE monthly_allocations(user_id TEXT, month TEXT, gold INTEGER, PRIMARY KEY(user_id, month));
            INSERT INTO accounts VALUES ('wallet-a', 'private-user', 'wallet'), ('issuer', NULL, 'issuer');
            INSERT INTO gold_transactions VALUES ('tx-a', 'allocation', NULL, '2026-10-01T00:00:00Z');
            INSERT INTO gold_entries VALUES (1, 'tx-a', 'wallet-a', 100), (2, 'tx-a', 'issuer', -100);
            INSERT INTO monthly_allocations VALUES ('private-user', '2026-10', 100);
        ''')
    policy = tmp_path / 'policy.txt'
    policy.write_bytes(b'No debt. Preserve agency.\n')
    return database, policy


def export(ledger):
    return checkpoints.export_checkpoint(*ledger, 'fixture-log')


def verify(ledger, checkpoint, log_id='fixture-log'):
    return checkpoints.verify_checkpoint(ledger[0], checkpoint, ledger[1], log_id)


def test_private_nonce_and_deterministic_verification_without_rows_or_db_writes(ledger):
    before = ledger[0].read_bytes()
    first, second = export(ledger), export(ledger)
    assert first['nonce'] != second['nonce'] and len(bytes.fromhex(first['nonce'])) == 32
    assert first['commitment_sha256'] != second['commitment_sha256']
    assert first['policy_sha256'] == hashlib.sha256(ledger[1].read_bytes()).hexdigest()
    assert first['status'] == 'UNWITNESSED'
    assert verify(ledger, first) and verify(ledger, second) and verify(ledger, first)
    assert ledger[0].read_bytes() == before
    assert 'private-user' not in json.dumps(first) and 'wallet-a' not in json.dumps(first)
    assert '100' not in first.values()


@pytest.mark.parametrize('sql', [
    'UPDATE gold_entries SET amount=999 WHERE seq=1',
    'UPDATE gold_entries SET seq=3 WHERE seq=1',
    'DELETE FROM gold_entries WHERE seq=2',
    "INSERT INTO gold_entries VALUES (3, 'tx-a', 'wallet-a', 10)",
    "UPDATE accounts SET user_id='replacement' WHERE id='wallet-a'",
    "UPDATE accounts SET kind='issuer' WHERE id='wallet-a'",
    "UPDATE accounts SET id='replacement' WHERE id='wallet-a'",
    "UPDATE gold_transactions SET id='replacement' WHERE id='tx-a'",
    "UPDATE gold_transactions SET kind='replacement' WHERE id='tx-a'",
    "UPDATE gold_transactions SET task_id='other' WHERE id='tx-a'",
    "UPDATE gold_transactions SET created_at='later' WHERE id='tx-a'",
    "UPDATE gold_entries SET transaction_id='replacement' WHERE seq=1",
    "UPDATE gold_entries SET account_id='replacement' WHERE seq=1",
    'UPDATE monthly_allocations SET gold=1000',
    "UPDATE monthly_allocations SET month='2026-11'",
    "UPDATE monthly_allocations SET user_id='replacement'",
    "DELETE FROM accounts WHERE id='issuer'",
])
def test_exact_snapshot_detects_changes_deletions_and_legitimate_appends(ledger, sql):
    original = export(ledger)
    with sqlite3.connect(ledger[0]) as connection:
        connection.execute(sql)
    assert not verify(ledger, original)
    rewritten = export(ledger)
    assert verify(ledger, rewritten)  # Self-consistency is not independent authenticity.
    assert not verify(ledger, original)


def test_physical_insertion_order_is_not_ledger_sequence(ledger):
    original = export(ledger)
    with sqlite3.connect(ledger[0]) as connection:
        for table, columns, _ in checkpoints.TABLES:
            rows = connection.execute(f'SELECT {", ".join(columns)} FROM {table}').fetchall()
            connection.execute(f'DELETE FROM {table}')
            connection.executemany(f'INSERT INTO {table} VALUES ({", ".join("?" for _ in columns)})', reversed(rows))
    assert verify(ledger, original)


def test_policy_bytes_and_expected_log_identity_are_bound(ledger):
    original = export(ledger)
    assert not verify(ledger, original, 'different-log')
    changed_identity = {**original, 'log_id': 'different-log'}
    assert not verify(ledger, changed_identity, 'different-log')
    ledger[1].write_bytes(ledger[1].read_bytes() + b' ')
    assert not verify(ledger, original)


@pytest.mark.parametrize('change', [
    lambda value: None,
    lambda value: {**value, 'extra': 1},
    lambda value: {key: field for key, field in value.items() if key != 'nonce'},
    lambda value: {**value, 'version': True},
    lambda value: {**value, 'version': 2},
    lambda value: {**value, 'domain': 'another-domain'},
    lambda value: {**value, 'status': 'VERIFIED'},
    lambda value: {**value, 'log_id': '../private log'},
    lambda value: {**value, 'log_id': ''},
    lambda value: {**value, 'log_id': 'x' * 65},
    lambda value: {**value, 'nonce': '00'},
    lambda value: {**value, 'nonce': 'G' * 64},
    lambda value: {**value, 'policy_sha256': []},
    lambda value: {**value, 'commitment_sha256': 'F' * 64},
])
def test_supplied_checkpoint_is_strictly_validated(ledger, change):
    with pytest.raises(ValueError):
        verify(ledger, change(export(ledger)))


def test_missing_database_is_never_created(ledger, tmp_path):
    missing = tmp_path / 'must-not-exist.sqlite'
    with pytest.raises(FileNotFoundError):
        checkpoints.export_checkpoint(missing, ledger[1], 'fixture-log')
    assert not missing.exists()


def test_read_only_connection_and_single_snapshot_transaction(ledger, monkeypatch):
    connect = sqlite3.connect
    observed = []

    def read_only(database_uri, **kwargs):
        assert database_uri.endswith('?mode=ro') and kwargs == {'uri': True}
        connection = connect(database_uri, **kwargs)
        connection.set_trace_callback(observed.append)
        return connection

    monkeypatch.setattr(checkpoints.sqlite3, 'connect', read_only)
    export(ledger)
    assert observed[0:2] == ['PRAGMA query_only = ON', 'BEGIN']
    assert len([statement for statement in observed if statement.startswith('SELECT ')]) == 4
    assert observed[-1] == 'ROLLBACK'


def test_cli_export_and_independent_verify_exit_codes(ledger, tmp_path, capsys):
    args = ['--database', str(ledger[0]), '--policy-file', str(ledger[1]), '--log-id', 'fixture-log']
    assert checkpoints.main(['export', *args]) == 0
    supplied = json.loads(capsys.readouterr().out)
    assert supplied['status'] == 'UNWITNESSED'
    retained = tmp_path / 'independent.json'
    retained.write_text(json.dumps(supplied), encoding='utf-8')
    verify_args = ['verify', *args, '--checkpoint-file', str(retained)]
    assert checkpoints.main(verify_args) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'MATCHES_SUPPLIED_CHECKPOINT_NOT_AUTHENTICATED'
    with sqlite3.connect(ledger[0]) as connection:
        connection.execute('DELETE FROM gold_entries')
    assert checkpoints.main(verify_args) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'MISMATCH_SUPPLIED_CHECKPOINT'
    retained.write_text('{"nonce": "private invalid input"}', encoding='utf-8')
    with pytest.raises(SystemExit) as error:
        checkpoints.main(verify_args)
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == '' and 'private invalid input' not in output.err
    with pytest.raises(SystemExit) as error:
        checkpoints.main(['verify', *args])
    assert error.value.code == 2


def test_cli_rejects_duplicate_fields(ledger, tmp_path, capsys):
    supplied = export(ledger)
    text = json.dumps(supplied)
    path = tmp_path / 'duplicate.json'
    path.write_text(text[:-1] + ', "version": 1}', encoding='utf-8')
    with pytest.raises(SystemExit) as error:
        checkpoints.main(['verify', '--database', str(ledger[0]), '--policy-file', str(ledger[1]),
                          '--log-id', 'fixture-log', '--checkpoint-file', str(path)])
    assert error.value.code == 2 and capsys.readouterr().out == ''
