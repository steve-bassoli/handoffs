from conftest import post_bounty, write


def test_context_profile_is_idempotent_and_does_not_claim_or_promote_evidence(client):
    bounty = post_bounty(client).json()['id']
    payload = {'validation_scope': 'LIVE', 'migration_stage': 'REPLACE', 'baseline_revision': 'base',
               'candidate_revision': 'patch', 'environment': 'approved test host',
               'knowledge': {'known': [{'statement': 'Declared source version', 'source': 'repo@sha:file:12'}],
                             'assumed': ['Deployment matches source'], 'unknown': ['Measured schema?']}}
    assert write(client, f'/bounties/{bounty}/profile', payload, 'nate').status_code == 403
    first = write(client, f'/bounties/{bounty}/profile', payload, key='profile')
    assert first.status_code == 200
    assert write(client, f'/bounties/{bounty}/profile', payload, key='profile').json() == first.json()
    data = first.json()
    assert data['phase'] == 'Posted' and data['claimant'] is None and data['ai_run'] is None
    assert data['coordinates']['validation_target'] == 'LIVE'
    assert data['profile']['knowledge']['unknown'] == ['Measured schema?']
    assert set(data['roles']) == {'Mapper', 'Maker', 'Breaker'}


def test_dependency_graph_reuses_one_setup_and_rejects_cycles(client):
    ids = [post_bounty(client, gold=10).json()['id'] for _ in range(3)]
    for identifier in ids[:2]:
        assert write(client, f'/bounties/{identifier}/dependencies', {'depends_on': [ids[2]]}).status_code == 200
    graph = client.get(f'/api/v1/bounties/{ids[0]}/constellation').json()
    assert len(graph['nodes']) == 3 and len(graph['edges']) == 2
    assert write(client, f'/bounties/{ids[2]}/dependencies', {'depends_on': [ids[0]]}).status_code == 422
    assert client.get(f'/api/v1/bounties/{ids[0]}').json()['phase'] == 'Posted'


def test_gremlins_workbench_runs_only_offline_comparison(client):
    from test_gremlins import fixture
    before = client.get('/api/v1/bounties').json()
    assert client.post('/api/v1/gremlins/mimic', json=fixture()).json()['watson_executed'] is False
    assert client.post('/api/v1/gremlins/saboteur', json=fixture()).json()['detector_verified']
    assert client.post('/api/v1/gremlins/witness', json=fixture()).json()['preservation']['rule']
    assert client.post('/api/v1/gremlins/mimic', json={**fixture(), 'scope': 'LIVE'}).status_code == 422
    assert client.get('/api/v1/bounties').json()['items'] == before['items']
    assert 'gremlins-form' in client.get('/').text
