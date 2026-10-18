"""Commit approval consumption BEFORE an external-store effect; never retry implicitly."""
import os
from pathlib import Path

from sqlalchemy import create_engine

from app.signoffs import require_signoff


def consume_signoff(action, payload, *, signoff_id, db=None):
    path = Path(db or os.environ.get('HANDOFFS_DB') or Path(__file__).resolve().parents[1] / '.data' / 'handoffs.sqlite')
    # Do not create or migrate an approval database as an executor side effect.
    engine = create_engine('sqlite+pysqlite://', creator=lambda: __import__('sqlite3').connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10))
    try:
        with engine.connect() as c:
            c.exec_driver_sql('BEGIN IMMEDIATE')
            require_signoff(c, action, payload, signoff_id=signoff_id)
            c.commit()
    finally:
        engine.dispose()


FAIL_CLOSED = 'Sign-off was consumed; application failed or is uncertain. Request a new sign-off; do not automatically retry.'
