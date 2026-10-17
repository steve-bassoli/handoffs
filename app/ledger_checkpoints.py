"""Private, read-only exact-snapshot checkpoints; not authenticated ledger history."""

import argparse
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3


DOMAIN = 'the-commons-ledger-exact-snapshot'
VERSION = 1
TABLES = (
    ('accounts', ('id', 'user_id', 'kind'), 'id COLLATE BINARY'),
    ('gold_transactions', ('id', 'kind', 'bounty_id', 'created_at'), 'id COLLATE BINARY'),
    ('gold_entries', ('seq', 'transaction_id', 'account_id', 'amount'), 'seq'),
    ('monthly_allocations', ('user_id', 'month', 'gold'), 'user_id COLLATE BINARY, month COLLATE BINARY'),
)
FIELDS = {'version', 'domain', 'status', 'log_id', 'policy_sha256', 'nonce', 'commitment_sha256'}


def _log_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}', value):
        raise ValueError('Supply a nonidentifying log ID of 1-64 ASCII letters, digits, dot, underscore, colon or hyphen')
    return value


def validate_checkpoint(checkpoint):
    if not isinstance(checkpoint, dict) or set(checkpoint) != FIELDS:
        raise ValueError('Invalid checkpoint fields')
    if (type(checkpoint['version']) is not int or checkpoint['version'] != VERSION
            or checkpoint['domain'] != DOMAIN or checkpoint['status'] != 'UNWITNESSED'):
        raise ValueError('Unsupported checkpoint version or domain')
    _log_id(checkpoint['log_id'])
    if any(not isinstance(checkpoint[key], str) or not re.fullmatch(r'[0-9a-f]{64}', checkpoint[key])
           for key in ('policy_sha256', 'nonce', 'commitment_sha256')):
        raise ValueError('Checkpoint digests and private nonce must be 32-byte lowercase hex')


def _metadata(policy_file, log_id, nonce):
    return {'version': VERSION, 'domain': DOMAIN, 'status': 'UNWITNESSED', 'log_id': _log_id(log_id),
            'policy_sha256': hashlib.sha256(Path(policy_file).read_bytes()).hexdigest(), 'nonce': nonce}


def _commitment(database, metadata):
    # strict resolution plus mode=ro prevents accidental database creation.
    uri = Path(database).resolve(strict=True).as_uri() + '?mode=ro'
    digest = hashlib.sha256()

    def add(value):
        digest.update(json.dumps(value, ensure_ascii=True, separators=(',', ':'), sort_keys=True).encode('utf-8'))
        digest.update(b'\n')

    add(metadata)
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute('PRAGMA query_only = ON')
        connection.execute('BEGIN')
        for table, columns, order in TABLES:
            add({'table': table, 'columns': columns})
            for row in connection.execute(f'SELECT {", ".join(columns)} FROM {table} ORDER BY {order}'):
                add(row)
        connection.rollback()
    return digest.hexdigest()


def export_checkpoint(database, policy_file, log_id):
    """Return a private commitment, not participant rows or an authenticated receipt."""
    metadata = _metadata(policy_file, log_id, secrets.token_hex(32))
    return {**metadata, 'commitment_sha256': _commitment(database, metadata)}


def verify_checkpoint(database, checkpoint, policy_file, log_id):
    """Check exact equality against a caller-supplied, independently retained checkpoint."""
    validate_checkpoint(checkpoint)
    metadata = _metadata(policy_file, log_id, checkpoint['nonce'])
    actual = _commitment(database, metadata)
    return (checkpoint['log_id'] == metadata['log_id']
            and hmac.compare_digest(checkpoint['policy_sha256'], metadata['policy_sha256'])
            and hmac.compare_digest(checkpoint['commitment_sha256'], actual))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('export', 'verify'))
    parser.add_argument('--database', required=True, help='Explicit existing SQLite database')
    parser.add_argument('--log-id', required=True, help='Nonidentifying stable log identifier')
    parser.add_argument('--policy-file', required=True, help='Exact policy bytes to bind')
    parser.add_argument('--checkpoint-file', help='Independently retained private JSON checkpoint (verify only)')
    args = parser.parse_args(argv)
    if (args.action == 'verify') != bool(args.checkpoint_file):
        parser.error('verify requires --checkpoint-file; export does not accept it')
    try:
        if args.action == 'export':
            print(json.dumps(export_checkpoint(args.database, args.policy_file, args.log_id), sort_keys=True))
            return 0
        checkpoint = json.loads(Path(args.checkpoint_file).read_text(encoding='utf-8'), object_pairs_hook=_unique_fields)
        matches = verify_checkpoint(args.database, checkpoint, args.policy_file, args.log_id)
        print(json.dumps({'status': 'MATCHES_SUPPLIED_CHECKPOINT_NOT_AUTHENTICATED' if matches
                         else 'MISMATCH_SUPPLIED_CHECKPOINT'}))
        return 0 if matches else 1
    except (OSError, sqlite3.Error, ValueError, TypeError):
        # Do not echo rows, supplied checkpoint text, paths or underlying SQL errors.
        parser.exit(2, 'Checkpoint operation failed: invalid input, unreadable file or unsupported ledger schema.\n')


def _unique_fields(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('Duplicate checkpoint fields')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
