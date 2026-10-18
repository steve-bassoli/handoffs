"""Owner-run spawn creates real children whose parent link shows in the existing lineage endpoint."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import RuleError
from app.spawn import spawn_children
from conftest import write


def medium(client, title='Parent'):
    return write(client, '/tasks', {'title': title, 'goal': 'g', 'criteria': ['c'], 'gold': 5, 'complexity': 'MEDIUM'}).json()['id']


def specs(count=3):
    return [{'title': f'Child {n}', 'goal': 'do it', 'criteria': ['works'], 'complexity': 'LOW', 'assigned_agent': f'bob-{n + 2}'}
            for n in range(count)]


def test_spawn_creates_true_children_visible_in_lineage(tmp_path):
    database = tmp_path / 'test.sqlite'
    with TestClient(create_app(database)) as client:
        parent = medium(client)
        children = spawn_children(database, parent, specs(), 'steve', 'bob (light mode)')
        assert len(children) == 3
        lineage = client.get(f'/api/v1/tasks/{children[0]}/lineage', headers={'X-Demo-User': 'steve'}).json()
        assert lineage['root_id'] == parent
        assert sorted(item['id'] for item in lineage['items'] if item['parent_id'] == parent) == sorted(children)
        child = client.get(f'/api/v1/tasks/{children[1]}', headers={'X-Demo-User': 'steve'}).json()
        assert child['parent_id'] == parent and child['status'] == 'open'
        event = next(e for e in child['events'] if e['kind'] == 'followup_confirmed')
        assert event['data']['spawned_via'] == 'bob (light mode)' and event['data']['assigned_agent'] == 'bob-3'
        top = client.get(f'/api/v1/tasks/{parent}', headers={'X-Demo-User': 'steve'}).json()
        assert top['events'][-1]['kind'] == 'followups_confirmed' and top['events'][-1]['data']['children'] == children


def test_spawn_refuses_bad_shapes(tmp_path):
    database = tmp_path / 'test.sqlite'
    with TestClient(create_app(database)) as client:
        parent = medium(client)
        with pytest.raises(ValueError):
            spawn_children(database, parent, specs(1), 'steve', 'x')
        with pytest.raises(ValueError):
            spawn_children(database, parent, specs(10), 'steve', 'x')
        low = write(client, '/tasks', {'title': 'L', 'goal': 'g', 'criteria': ['c'], 'gold': 5, 'complexity': 'LOW'}).json()['id']
        with pytest.raises(RuleError):
            spawn_children(database, low, specs(), 'steve', 'x')
        spawn_children(database, parent, specs(2), 'steve', 'x')
        with pytest.raises(RuleError):
            spawn_children(database, parent, specs(2), 'steve', 'x')


def high(client, title='Big goal'):
    return write(client, '/tasks', {'title': title, 'goal': 'g', 'criteria': ['c'], 'gold': 5, 'complexity': 'HIGH'}).json()['id']


def child(complexity, n):
    return {'title': f'{complexity} {n}', 'goal': 'do it', 'criteria': ['works'], 'complexity': complexity}


def test_high_may_split_into_several_highs_or_several_mediums_but_never_mixed(tmp_path):
    database = tmp_path / 'test.sqlite'
    with TestClient(create_app(database)) as client:
        first, second, third = high(client, 'A'), high(client, 'B'), high(client, 'C')
        assert len(spawn_children(database, first, [child('HIGH', 1), child('HIGH', 2)], 'steve', 'x')) == 2
        assert len(spawn_children(database, second, [child('MEDIUM', 1), child('MEDIUM', 2), child('MEDIUM', 3), child('MEDIUM', 4)], 'steve', 'x')) == 4
        with pytest.raises(ValueError):
            spawn_children(database, third, [child('HIGH', 1), child('MEDIUM', 2)], 'steve', 'x')
        with pytest.raises(ValueError):
            spawn_children(database, third, [child('LOW', 1), child('LOW', 2)], 'steve', 'x')
        medium_child = client.get(f'/api/v1/tasks/{first}', headers={'X-Demo-User': 'steve'}).json()['events'][-1]['data']['children'][0]
        assert len(spawn_children(database, medium_child, [child('HIGH', 3), child('HIGH', 4)], 'steve', 'x')) == 2, 'A spawned HIGH can split again'


def test_every_child_creating_path_enforces_the_decomposition_rule():
    """Structural guard: any app module that inserts a ticket with a parent_id must call the validator."""
    from pathlib import Path
    from app.complexity import DECOMPOSITION, MIN_CHILDREN
    assert DECOMPOSITION == {'HIGH': ('HIGH', 'MEDIUM'), 'MEDIUM': ('LOW',), 'LOW': ()} and MIN_CHILDREN == 2
    for path in sorted(Path('app').glob('*.py')):
        text = path.read_text(encoding='utf-8')
        if 'INSERT INTO tasks' in text and 'parent_id)' in text:
            assert 'validate_task_split' in text or 'validate_proposals' in text, f'{path} creates children without the decomposition rule'


def test_audit_finds_violations_and_passes_valid_trees(tmp_path):
    from app.services import Service
    from app.adapters import DemoDeliveryVerifier
    from app.storage import Database
    database = tmp_path / 'test.sqlite'
    with TestClient(create_app(database)) as client:
        parent = high(client, 'Root')
        spawn_children(database, parent, [child('HIGH', 1), child('HIGH', 2)], 'steve', 'x')
        db = Database(database)
        try:
            service = Service(db, DemoDeliveryVerifier())
            assert service.hierarchy_violations() == []
            with db.write() as c:  # Simulate a bypass: an extra LOW child slipped under a HIGH.
                c.exec_driver_sql("INSERT INTO tasks(id,title,goal,criteria,repository,context_links,creator,target,gold,created_at,funded,parent_id) "
                                  "VALUES ('bad','Bad','g','[\"c\"]','','[]','steve',NULL,1,'2026-01-01',0,?)", (parent,))
                service.event(c, 'bad', 'followup_confirmed', 'steve', 'open', {'parent_id': parent, 'complexity': 'LOW'})
            violations = service.hierarchy_violations()
            assert len(violations) == 1 and violations[0]['parent'] == parent and violations[0]['children']['bad'] == 'LOW'
        finally:
            db.engine.dispose()
