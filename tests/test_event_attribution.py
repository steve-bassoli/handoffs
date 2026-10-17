import json

from fastapi.testclient import TestClient

from app.automation_mode import AUTOMATION_HEADER, set_mode
from app.main import create_app
from app.services import Service, event_via
from conftest import post_bounty, write


class RecordingCursor:
    def exec_driver_sql(self, statement, parameters):
        self.statement = statement
        self.parameters = parameters


def test_event_preserves_data_without_mutating_input_when_attributed():
    cursor = RecordingCursor()
    data = {'note': 'progress', 'nested': {'kept': True}}
    token = event_via.set('astra/bob-3')
    try:
        Service(None, None).event(cursor, 'bounty', 'working', 'nate', 'working', data)
    finally:
        event_via.reset(token)
    assert data == {'note': 'progress', 'nested': {'kept': True}}
    assert json.loads(cursor.parameters[4]) == {
        'note': 'progress', 'nested': {'kept': True}, 'via': 'astra/bob-3',
    }


def automated_write(client, path, data, user, key, via):
    return client.post('/api/v1' + path, json=data, headers={
        'X-Demo-User': user,
        'Idempotency-Key': key,
        AUTOMATION_HEADER: via,
    })


def test_automation_header_attributes_only_new_events_and_resets(tmp_path, monkeypatch):
    mode_path = tmp_path / 'automation-mode.json'
    monkeypatch.setenv('HANDOFFS_AUTOMATION_MODE', str(mode_path))
    with TestClient(create_app(tmp_path / 'test.sqlite')) as client:
        set_mode('light', 'steve', 'attribution fixture', mode_path)
        tagged = automated_write(client, '/bounties', {
            'title': 'Tagged', 'goal': 'g', 'criteria': ['c'], 'gold': 5,
        }, 'steve', 'tagged-post', 'astra/bob-3')
        assert tagged.status_code == 200
        assert tagged.json()['events'][-1]['data']['via'] == 'astra/bob-3'

        bounty = post_bounty(client).json()
        bounty_id = bounty['id']
        assert 'via' not in bounty['events'][-1]['data']
        assert write(client, f'/bounties/{bounty_id}/take', user='nate').status_code == 200

        tagged_status = automated_write(client, f'/bounties/{bounty_id}/status', {
            'status': 'working', 'note': 'automated progress',
        }, 'nate', 'tagged-status', 'astra/bob-3')
        assert tagged_status.status_code == 200
        events = tagged_status.json()['events']
        assert all('via' not in event['data'] for event in events[:-1])
        assert events[-1]['data']['via'] == 'astra/bob-3'

        failed = automated_write(client, '/bounties', {
            'title': 'Invalid', 'goal': 'g', 'criteria': [], 'gold': 5,
        }, 'steve', 'failed-tagged-post', 'astra/bob-3')
        assert failed.status_code == 422

        untagged_status = write(client, f'/bounties/{bounty_id}/status', {
            'status': 'working', 'note': 'human progress',
        }, user='nate', key='untagged-status')
        assert untagged_status.status_code == 200
        assert 'via' not in untagged_status.json()['events'][-1]['data']


def test_empty_automation_header_is_recorded_when_present(tmp_path, monkeypatch):
    mode_path = tmp_path / 'automation-mode.json'
    monkeypatch.setenv('HANDOFFS_AUTOMATION_MODE', str(mode_path))
    with TestClient(create_app(tmp_path / 'test.sqlite')) as client:
        set_mode('light', 'steve', 'attribution fixture', mode_path)
        response = automated_write(client, '/bounties', {
            'title': 'Empty attribution', 'goal': 'g', 'criteria': ['c'], 'gold': 5,
        }, 'steve', 'empty-via-post', '')
        assert response.status_code == 200
        assert response.json()['events'][-1]['data']['via'] == ''
