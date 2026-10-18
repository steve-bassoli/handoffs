"""One fast read for "how many tickets are left?": summary, status filter and short-id lookup."""
from conftest import post_task, write


def test_summary_counts_derived_states_and_lists_only_active_work(client):
    open_task = post_task(client).json()
    taken = post_task(client).json()
    assert write(client, f"/tasks/{taken['id']}/take", user='nate').status_code == 200
    summary = client.get('/api/v1/tasks/summary')
    assert summary.status_code == 200 and summary.headers['cache-control'] == 'no-store'
    body = summary.json()
    assert body['total'] == 2
    assert body['counts'] == {'open': 1, 'working': 1}
    active = {row['id']: row for row in body['active']}
    assert set(active) == {open_task['id'], taken['id']}
    assert active[taken['id']]['claimant'] == 'nate' and active[taken['id']]['status'] == 'working'
    assert active[open_task['id']]['short_id'] == open_task['id'][:8]
    assert active[open_task['id']]['complexity'] == 'LOW'


def test_status_filter_searches_whole_board_and_rejects_unknown_states(client):
    open_task = post_task(client).json()
    taken = post_task(client).json()
    write(client, f"/tasks/{taken['id']}/take", user='nate')
    working = client.get('/api/v1/tasks?status=working').json()['items']
    assert [row['id'] for row in working] == [taken['id']]
    both = client.get('/api/v1/tasks?status=working,open').json()['items']
    assert {row['id'] for row in both} == {open_task['id'], taken['id']}
    repeated = client.get('/api/v1/tasks?status=working&status=open').json()['items']
    assert {row['id'] for row in repeated} == {open_task['id'], taken['id']}
    unknown = client.get('/api/v1/tasks?status=bogus')
    assert unknown.status_code == 422 and unknown.json()['detail']['statuses'] == ['bogus']


def test_short_id_lookup_unique_ambiguous_and_unknown(client):
    task = post_task(client).json()
    assert client.get('/api/v1/tasks/' + task['id'][:8]).json()['id'] == task['id']
    assert client.get('/api/v1/tasks/' + task['id'][:7]).status_code == 404
    assert client.get('/api/v1/tasks/ffffffff-none').status_code == 404
    service = client.app.state.service
    with service.db.write() as c:
        for twin in ('abcdef12-0000-aaaa', 'abcdef12-1111-bbbb'):
            c.exec_driver_sql("INSERT INTO tasks(id,title,goal,criteria,repository,context_links,creator,target,gold,created_at) "
                              "VALUES (?,'t','g','[]','','[]','steve',NULL,1,'2026-10-18T00:00:00+00:00')", (twin,))
    clash = client.get('/api/v1/tasks/abcdef12')
    assert clash.status_code == 409
    assert clash.json()['detail']['matches'] == ['abcdef12-0000-aaaa', 'abcdef12-1111-bbbb']
