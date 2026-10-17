"""Persisted launch limits for the controlled Astra engine, not an OS security boundary."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import httpx

from app.api_budget import BudgetError, budget_path, connection


TREE_RULES = ('Astra delegation stops at three levels including the root: at most three total children '
    'per parent and thirteen nodes per tree. Level-three agents cannot spawn. A task tree is not '
    'permission to launch agents. Only the controlled launcher admits agents and binds their parent; '
    'all agents share the existing sponsor allocation, never a fresh budget per child. '
    'Report verified live agents separately from interrupted occupied leases.')
SCHEMA = '''CREATE TABLE IF NOT EXISTS astra_agents (
    id TEXT PRIMARY KEY, parent_id TEXT, tree_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 3), role TEXT NOT NULL,
    pid INTEGER NOT NULL, run TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
    state TEXT NOT NULL CHECK(state IN ('active','released','failed')))'''


class AgentLimitError(BudgetError):
    pass


@contextmanager
def agent_lease(run, parent_agent=None, role='worker', transport=None, path=None):
    if role not in ('coordinator', 'worker') or (parent_agent is not None and not isinstance(parent_agent, str)):
        raise AgentLimitError('Invalid trusted launcher attribution')
    if isinstance(transport, httpx.MockTransport):
        yield None  # Explicit offline protocol fixtures do not occupy paid-agent slots.
        return
    path = Path(path or budget_path())
    identifier = uuid4().hex
    try:
        with connection(path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute(SCHEMA)
            if parent_agent is None:
                if db.execute("SELECT COUNT(*) FROM astra_agents WHERE state='active'").fetchone()[0]:
                    raise AgentLimitError('An Astra tree is already active or awaits explicit recovery')
                level, tree = 1, identifier
            else:
                parent = db.execute('SELECT level,tree_id,state FROM astra_agents WHERE id=?', (parent_agent,)).fetchone()
                if not parent or parent[2] != 'active':
                    raise AgentLimitError('An active registered parent is required')
                if parent[0] >= 3:
                    raise AgentLimitError('Astra delegation stops at level three')
                if db.execute('SELECT COUNT(*) FROM astra_agents WHERE parent_id=?', (parent_agent,)).fetchone()[0] >= 3:
                    raise AgentLimitError('A parent may create at most three children in its tree')
                level, tree = parent[0] + 1, parent[1]
            agent = {'id': identifier, 'parent_id': parent_agent, 'tree_id': tree, 'level': level,
                     'role': role, 'pid': os.getpid(), 'run': str(Path(run).resolve()),
                     'started': datetime.now(timezone.utc).isoformat()}
            db.execute('INSERT INTO astra_agents VALUES (?,?,?,?,?,?,?,?,NULL,?)',
                       (*agent.values(), 'active'))
    except (sqlite3.Error, OSError, TypeError):
        raise AgentLimitError('Agent launch accounting is unavailable; no agent started') from None
    state = 'released'
    try:
        yield agent
    except BaseException:
        state = 'failed'
        raise
    finally:
        # A killed process never reaches this block: its slot is deliberately not expired.
        with connection(path) as db:
            db.execute("UPDATE astra_agents SET state=?,ended=? WHERE id=? AND state='active'",
                       (state, datetime.now(timezone.utc).isoformat(), identifier))


def require_agent(run, transport=None, path=None):
    if isinstance(transport, httpx.MockTransport):
        return
    try:
        agent = json.loads((Path(run) / 'agent.json').read_text(encoding='utf-8'))
        with connection(path or budget_path()) as db:
            row = db.execute('SELECT pid,run,state FROM astra_agents WHERE id=?', (agent['id'],)).fetchone()
        if not row or row != (os.getpid(), str(Path(run).resolve()), 'active'):
            raise AgentLimitError('No active launcher-bound Astra agent for this process/run')
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
        raise AgentLimitError('No active launcher-bound Astra agent for this process/run') from None


def active_leases(path=None):
    """Occupied slots, not evidence that the recorded PIDs are still live."""
    with connection(path or budget_path()) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='astra_agents'").fetchone():
            return []
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM astra_agents WHERE state='active'")]
