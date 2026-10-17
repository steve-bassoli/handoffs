"""Bounded read-only source seams; no implicit adapter or automatic retry."""
import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

GIT_ARGS = ('git', '--no-pager', 'log', '-1', '--format=%H%x09%cI', '--no-decorate')


class SourceUnavailable(Exception):
    pass


def _unavailable(code):
    return {'status': 'unavailable', 'data': None, 'error_code': code}


def read_ledger(path, adapter=None, limit=1000):
    """Adapter(query) supplies R2 ledger data and complete-reservation attestation.

    The observed schema is not an authorization to choose a deployed mapping.
    Every query failure poisons the read, even if the adapter catches it.
    """
    if adapter is None:
        return _unavailable('adapter_required')
    if type(limit) is not int or not 1 <= limit <= 10000:
        return _unavailable('invalid_read_bound')
    conn = None
    try:
        target = Path(path).resolve(strict=True)
        if not target.is_file():
            raise SourceUnavailable()
        conn = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True,
                               timeout=0.25, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ}
        conn.set_authorizer(lambda action, *args: (
            sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY))
        ticks = 0

        def progress():
            nonlocal ticks
            ticks += 1
            return int(ticks > 1000)

        conn.set_progress_handler(progress, 1000)
        queries, remaining, poisoned = 0, limit, False

        def query(sql, parameters=()):
            nonlocal queries, remaining, poisoned
            try:
                queries += 1
                if (queries > 8 or not isinstance(sql, str) or len(sql) > 8192
                        or not re.match(r'^\s*SELECT\b', sql, re.I)):
                    raise SourceUnavailable()
                cursor = conn.execute(sql, parameters)
                rows = cursor.fetchmany(remaining + 1)
                if len(rows) > remaining:
                    raise SourceUnavailable()
                remaining -= len(rows)
                return [dict(row) for row in rows]
            except Exception:
                poisoned = True
                raise

        data = adapter(query)
        if (poisoned or queries == 0 or not isinstance(data, dict)
                or data.get('reservations_complete') is not True
                or not isinstance(data.get('holds'), list)):
            raise SourceUnavailable()
        return {'status': 'ok', 'data': data, 'error_code': None}
    except Exception:
        return _unavailable('ledger_unavailable')
    finally:
        if conn is not None:
            conn.close()


def read_git(repo, runner=subprocess.run):
    """One metadata-only command, no shell, subjects, bodies or test inference."""
    try:
        result = runner(list(GIT_ARGS), cwd=str(repo), shell=False,
                        capture_output=True, text=True, timeout=2,
                        check=False, encoding='utf-8', errors='strict')
        if result.returncode != 0:
            raise SourceUnavailable()
        output = result.stdout
        if not isinstance(output, str) or len(output) > 256:
            raise SourceUnavailable()
        match = re.fullmatch(
            r'([0-9a-f]{40}|[0-9a-f]{64})\t'
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})\n?',
            output)
        if not match:
            raise SourceUnavailable()
        stamp = datetime.fromisoformat(match.group(2))
        if stamp.utcoffset() is None:
            raise SourceUnavailable()
        return {'status': 'ok', 'error_code': None, 'data': {
            'commit': {'hash': match.group(1), 'committed_at': match.group(2)}}}
    except Exception:
        return _unavailable('git_unavailable')
