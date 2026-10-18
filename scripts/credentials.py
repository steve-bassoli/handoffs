"""Local operator tool. Run from the repository: python scripts/credentials.py --help.

Use only against an explicitly authorized database. Tokens go to stdout once;
never redirect into repository files, transcripts or shared logs.
"""
import argparse
import getpass
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.credentials import Credentials
from app.storage import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=os.environ.get('HANDOFFS_DB', '.data/handoffs.sqlite'))
    commands = parser.add_subparsers(dest='command', required=True)
    password = commands.add_parser('password')
    password.add_argument('user')
    token = commands.add_parser('token')
    token.add_argument('user')
    token.add_argument('--kind', required=True, choices=['relay', 'codex', 'agent'])
    token.add_argument('--ttl', type=int, default=86400)
    revoke = commands.add_parser('revoke')
    revoke.add_argument('principal_id')
    args = parser.parse_args()
    # Deliberately do not create, migrate or seed an operational database here.
    if not Path(args.db).is_file():
        parser.error('Database must already exist and be migrated through 004')
    db = Database(args.db)
    credentials = Credentials(db)
    try:
        if args.command == 'password':
            value = getpass.getpass('New password: ')
            if value != getpass.getpass('Confirm password: '):
                parser.error('Passwords do not match')
            credentials.set_password(args.user, value)
            print('Password set; previous human sessions revoked.')
        elif args.command == 'token':
            result = credentials.issue(args.user, args.kind, args.ttl)
            print('Principal ID: ' + result['principal_id'], file=sys.stderr)
            print(result['access_token'])
        else:
            credentials.revoke(args.principal_id)
            print('Revocation requested.')
    finally:
        db.engine.dispose()


if __name__ == '__main__':
    main()
