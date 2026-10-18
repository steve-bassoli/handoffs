"""Accept: take rules and AI preparation start in one transaction."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import post_bounty, write
from test_ai import FakeLuna, decision, get_run


def accepted_app(tmp_path, decisions=None):
    return TestClient(create_app(tmp_path / 'test.sqlite',
                                 ai_model=FakeLuna(decisions or [decision('ask', questions=['Which Python version?'])])))


@pytest.mark.parametrize('worker', ['nate', 'steve'])
def test_accept_claims_and_starts_preparation_together(tmp_path, worker):
    with accepted_app(tmp_path) as client:
        bounty = post_bounty(client).json()['id']
        result = write(client, f'/bounties/{bounty}/accept', {'model': 'luna'}, worker)
        assert result.status_code == 200
        task = client.get('/api/v1/bounties/' + bounty).json()
        assert task['claimant'] == worker and task['status'] == 'working'
        kinds = [event['kind'] for event in task['events']]
        assert kinds.index('taken') < kinds.index('ai_started') and kinds.count('taken') == 1
        assert get_run(client, bounty)['status'] == 'needs_input'
        assert get_run(client, bounty)['actor'] == worker


def test_accept_keeps_take_rules(tmp_path):
    with accepted_app(tmp_path) as client:
        bounty = write(client, '/bounties', {'title': 'Targeted task', 'goal': 'Deliver',
            'criteria': ['Works'], 'gold': 10, 'target': 'nate'}).json()['id']
        assert write(client, f'/bounties/{bounty}/accept', {}, 'steve').status_code == 403
        task = client.get('/api/v1/bounties/' + bounty).json()
        assert task['status'] == 'open' and task['claimant'] is None and task['ai_run'] is None
        assert write(client, f'/bounties/{bounty}/take', user='nate').status_code == 200
        assert write(client, f'/bounties/{bounty}/accept', {}, 'nate').status_code == 409
        assert client.get('/api/v1/bounties/' + bounty).json()['ai_run'] is None


def test_unavailable_ai_leaves_bounty_unclaimed(client, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    bounty = post_bounty(client).json()['id']
    assert write(client, f'/bounties/{bounty}/accept', {}, 'nate').status_code == 503
    task = client.get('/api/v1/bounties/' + bounty).json()
    assert task['status'] == 'open' and task['claimant'] is None and task['ai_run'] is None


def test_accept_replay_returns_same_result_without_second_run(tmp_path):
    model = FakeLuna([decision('ask', questions=['Which Python version?'])])
    with TestClient(create_app(tmp_path / 'test.sqlite', ai_model=model)) as client:
        bounty = post_bounty(client).json()['id']
        first = write(client, f'/bounties/{bounty}/accept', {}, 'nate', key='accept')
        second = write(client, f'/bounties/{bounty}/accept', {}, 'nate', key='accept')
        assert first.status_code == second.status_code == 200 and first.json() == second.json()
        assert model.calls == 1


def test_accept_button_loads_immediately_and_updates_one_notice():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the accept-flow check')
    source = Path('app/static/app.js').read_text(encoding='utf-8')
    flow = source[source.index('const acceptStages = {'):source.index('async function show(id) {')]
    checks = r'''
const assert = require('node:assert/strict');
const nodes = {};
const element = (tag, text, className) => ({tag, textContent: text, className: className || '', children: [], attrs: {},
  classList: {add(name) { this.owner.className += ' ' + name; }, remove(name) { this.owner.className = this.owner.className.replace(' ' + name, ''); }},
  setAttribute(key, value) { this.attrs[key] = value; }, removeAttribute(key) { delete this.attrs[key]; },
  replaceChildren(...children) { this.children = children; }, remove() { delete nodes[this.id]; }});
const make = (...args) => { const node = element(...args); node.classList.owner = node; return node; };
let status = 'queued', timers = 0, fail = false, appended = 0;
const context = {
  acceptPoll: null, $: id => nodes[id], element: make, clearTimeout() {}, setTimeout: () => ++timers, encodeURIComponent,
  document: {body: {append(node) { appended++; nodes[node.id] = node; }}},
  run: operation => operation(), show: async () => {},
  api: async () => ({ai_run: {status}}),
};
context.mutate = async () => { assert.equal(context.button.textContent, 'Accepting…'); if (fail) throw new Error('This task is not available to this user'); };
vm.runInNewContext(flow + '\nthis.accept = accept; this.trackAccept = trackAccept;', context);
const data = {id: 'b1', title: 'Fix rounding', ai_options: {recommended: 'luna'}};
(async () => {
  context.button = make('button', 'Accept', 'primary');
  await context.accept(data, context.button);
  const notice = nodes['accept-notice'];
  assert.equal(notice.children[1].textContent, 'Accepted · queued for AI preparation');
  assert.equal(notice.children[2].textContent, 'Fix rounding');
  assert.equal(notice.children[2].href, '#task=b1');
  assert.equal(timers, 1);
  status = 'needs_input';
  await context.trackAccept('b1', 'Fix rounding');
  assert.equal(nodes['accept-notice'], notice);
  assert.equal(appended, 1);
  assert.equal(notice.className, 'attention');
  assert.equal(timers, 1, 'Polling stops once AI needs the developer');
  fail = true;
  context.button = make('button', 'Accept', 'primary');
  await assert.rejects(context.accept(data, context.button));
  assert.equal(context.button.textContent, 'Accept');
  assert.equal(context.button.attrs['aria-busy'], undefined);
  assert.equal(notice.className, 'error');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    script = "const vm = require('node:vm');\nconst flow = " + json.dumps(flow) + ";\n" + checks
    result = subprocess.run([node], input=script, capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
