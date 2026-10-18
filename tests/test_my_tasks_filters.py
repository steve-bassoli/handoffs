"""My Tasks: open-only status filter and the "assigned by" (creator) filter with its facet."""
from pathlib import Path

from conftest import post_task, write

OPEN = 'open,pending,working,blocked,delivered,awaiting_approval'


def test_mine_filters_by_creator_and_hides_closed(client):
    own = post_task(client).json()
    from_nate = post_task(client, user='nate').json()
    write(client, f"/tasks/{from_nate['id']}/take")
    closed = post_task(client).json()
    write(client, f"/tasks/{closed['id']}/cancel")
    write(client, '/tasks', {'title': 'Not mine', 'goal': 'g', 'criteria': ['c'], 'gold': 1, 'complexity': 'LOW'}, 'ana')

    every = client.get('/api/v1/tasks?view=mine').json()
    assert {row['id'] for row in every['items']} == {own['id'], from_nate['id'], closed['id']}
    assert every['creators'] == ['nate', 'steve']

    open_only = client.get('/api/v1/tasks?view=mine&status=' + OPEN).json()
    assert {row['id'] for row in open_only['items']} == {own['id'], from_nate['id']}

    by_nate = client.get('/api/v1/tasks?view=mine&creator=nate').json()
    assert [row['id'] for row in by_nate['items']] == [from_nate['id']]
    assert by_nate['creators'] == ['nate', 'steve']


def test_my_tasks_page_defaults_to_open_and_has_assigned_by_picker():
    static = Path(__file__).resolve().parents[1] / 'app' / 'static'
    html, script = (static / 'index.html').read_text(encoding='utf-8'), (static / 'app.js').read_text(encoding='utf-8')
    assert 'id="show-closed" type="checkbox"' in html and 'id="assigned-by"' in html
    assert "&status=" + OPEN in script and "'&creator='" in script
    # The toggle always reports what it did, even when no closed task matches.
    assert 'id="mine-note"' in html and 'No closed tasks${who} on this page' in script


def test_static_scripts_revalidate_so_deploys_are_not_stale(client):
    response = client.get('/static/app.js')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-cache'
