from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import sqlite3

import pytest

from app.api_budget import initialize
from app.astra_agents import AgentLimitError, active_leases, agent_lease, require_agent


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize(path, 0, 0, 'Offline tree tests only')
    return path


def test_three_levels_allow_thirteen_nodes_not_infinite_recursion(registry, tmp_path):
    with ExitStack() as stack:
        root = stack.enter_context(agent_lease(tmp_path / 'root', role='coordinator', path=registry))
        parents = [stack.enter_context(agent_lease(tmp_path / f'child-{i}', root['id'], path=registry)) for i in range(3)]
        leaves = [stack.enter_context(agent_lease(tmp_path / f'leaf-{i}-{j}', p['id'], path=registry))
                  for i, p in enumerate(parents) for j in range(3)]
        assert len(active_leases(registry)) == 13
        assert {a['tree_id'] for a in active_leases(registry)} == {root['id']}
        assert [a['level'] for a in active_leases(registry)].count(3) == 9
        with pytest.raises(AgentLimitError, match='level three'):
            with agent_lease(tmp_path / 'forbidden-level-four', leaves[0]['id'], path=registry):
                pytest.fail('Must not launch')
        with pytest.raises(AgentLimitError, match='three children'):
            with agent_lease(tmp_path / 'fourth-child', root['id'], path=registry):
                pytest.fail('Must not launch')
        with pytest.raises(AgentLimitError, match='already active'):
            with agent_lease(tmp_path / 'second-root', path=registry):
                pytest.fail('Must not launch')
    assert active_leases(registry) == []


def test_finished_children_do_not_replenish_lifetime_branch_limit(registry, tmp_path):
    with agent_lease(tmp_path / 'root', path=registry) as root:
        for i in range(3):
            with agent_lease(tmp_path / str(i), root['id'], path=registry):
                pass
        with pytest.raises(AgentLimitError, match='three children'):
            with agent_lease(tmp_path / 'fourth', root['id'], path=registry):
                pytest.fail('Must not launch')
    with pytest.raises(AgentLimitError, match='active registered parent'):
        with agent_lease(tmp_path / 'finished-parent', root['id'], path=registry):
            pytest.fail('Must not launch')


def test_concurrent_sibling_admissions_are_atomic(registry, tmp_path):
    with agent_lease(tmp_path / 'root', path=registry) as root:
        def attempt(i):
            lease = agent_lease(tmp_path / str(i), root['id'], path=registry)
            try:
                return lease, lease.__enter__()
            except AgentLimitError:
                return None
        with ThreadPoolExecutor(max_workers=9) as pool:
            admitted = [result for result in pool.map(attempt, range(9)) if result]
        try:
            assert len(admitted) == 3 and len(active_leases(registry)) == 4
        finally:
            for lease, _ in admitted:
                lease.__exit__(None, None, None)


def test_failed_and_stale_leases_have_distinct_recovery(registry, tmp_path):
    with pytest.raises(RuntimeError):
        with agent_lease(tmp_path / 'failure', path=registry):
            raise RuntimeError('Synthetic failure')
    assert active_leases(registry) == []
    with sqlite3.connect(registry) as db:
        assert db.execute('SELECT state FROM astra_agents').fetchone()[0] == 'failed'
        # Simulated crash record, deliberately not an actual killed process.
        db.execute("INSERT INTO astra_agents VALUES ('stale',NULL,'stale',1,'coordinator',-1,'fixture','past',NULL,'active')")
    assert active_leases(registry)[0]['pid'] == -1
    with pytest.raises(AgentLimitError, match='recovery'):
        with agent_lease(tmp_path / 'must-not-expire', path=registry):
            pytest.fail('A stale lease must not expire automatically')


def test_requests_are_bound_to_active_process_and_run(registry, tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    with agent_lease(run, path=registry) as agent:
        (run / 'agent.json').write_text(json.dumps(agent), encoding='utf-8')
        require_agent(run, path=registry)
        with sqlite3.connect(registry) as db:
            db.execute('UPDATE astra_agents SET pid=-1 WHERE id=?', (agent['id'],))
        with pytest.raises(AgentLimitError):
            require_agent(run, path=registry)
    with pytest.raises(AgentLimitError):
        require_agent(run, path=registry)


def test_existing_launchers_refuse_second_root_before_read_or_network(registry, tmp_path, monkeypatch):
    from app import agent_conduit, astra_chat
    monkeypatch.setenv('HANDOFFS_API_BUDGET_DB', str(registry))
    with agent_lease(tmp_path / 'root', path=registry):
        with pytest.raises(AgentLimitError, match='already active'):
            agent_conduit.execute({}, tmp_path / 'must-not-start')
        with pytest.raises(AgentLimitError, match='already active'):
            astra_chat.talk(tmp_path / 'absent-prompt', tmp_path / 'must-not-start-either')
    assert not (tmp_path / 'must-not-start').exists()
