"""Owner-run spawn creates real children whose parent link shows in the existing lineage endpoint."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import RuleError
from app.spawn import spawn_children
from conftest import write


def medium(client, title='Parent'):
    return write(client, '/bounties', {'title': title, 'goal': 'g', 'criteria': ['c'], 'gold': 5, 'complexity': 'MEDIUM'}).json()['id']


def specs(count=3):
    return [{'title': f'Child {n}', 'goal': 'do it', 'criteria': ['works'], 'complexity': 'LOW', 'assigned_agent': f'bob-{n + 2}'}
            for n in range(count)]


def test_spawn_creates_true_children_visible_in_lineage(tmp_path):
    database = tmp_path / 'test.sqlite'
    with TestClient(create_app(database)) as client:
        parent = medium(client)
        children = spawn_children(database, parent, specs(), 'steve', 'bob (light mode)')
        assert len(children) == 3
        lineage = client.get(f'/api/v1/bounties/{children[0]}/lineage', headers={'X-Demo-User': 'steve'}).json()
        assert lineage['root_id'] == parent
        assert sorted(item['id'] for item in lineage['items'] if item['parent_id'] == parent) == sorted(children)
        child = client.get(f'/api/v1/bounties/{children[1]}', headers={'X-Demo-User': 'steve'}).json()
        assert child['parent_id'] == parent and child['status'] == 'open'
        event = next(e for e in child['events'] if e['kind'] == 'followup_confirmed')
        assert event['data']['spawned_via'] == 'bob (light mode)' and event['data']['assigned_agent'] == 'bob-3'
        top = client.get(f'/api/v1/bounties/{parent}', headers={'X-Demo-User': 'steve'}).json()
        assert top['events'][-1]['kind'] == 'followups_confirmed' and top['events'][-1]['data']['children'] == children


def test_spawn_refuses_bad_shapes(tmp_path):
    database = tmp_path / 'test.sqlite'
    with TestClient(create_app(database)) as client:
        parent = medium(client)
        with pytest.raises(ValueError):
            spawn_children(database, parent, specs(1), 'steve', 'x')
        with pytest.raises(ValueError):
            spawn_children(database, parent, specs(4), 'steve', 'x')
        low = write(client, '/bounties', {'title': 'L', 'goal': 'g', 'criteria': ['c'], 'gold': 5, 'complexity': 'LOW'}).json()['id']
        with pytest.raises(RuleError):
            spawn_children(database, low, specs(), 'steve', 'x')
        spawn_children(database, parent, specs(2), 'steve', 'x')
        with pytest.raises(RuleError):
            spawn_children(database, parent, specs(2), 'steve', 'x')
