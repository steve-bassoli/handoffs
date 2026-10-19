from pathlib import Path
import shutil
import subprocess

import pytest


def test_agent_roster_renders_unknowns_and_switches_views_without_spending():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the browser roster check')
    source = Path('app/static/app.js').read_text(encoding='utf-8')
    functions = source[source.index('async function agentRoster()'):source.index('async function mutate(')]
    checks = r'''
const assert = require('node:assert/strict');
const nodes = new Map();
const element = (tag, text) => ({tag, textContent: text, children: [], append(...items) { this.children.push(...items); }, replaceChildren() { this.children = []; }});
const $ = id => { if (!nodes.has(id)) nodes.set(id, element('div')); return nodes.get(id); };
let view, selected, aiPoll, proofPoll, hash, calls = []; const user = 'steve';
let result = {available: true, items: [{id: 'abc12345extra', role: 'worker', level: 1, state: 'active', resting: false, credits: null, admiration: null, growth: null}]};
const api = async (...args) => { calls.push(args); return result; };
const location = {pathname: '/', search: ''};
const history = {replaceState(_a, _b, url) { hash = url; }};
const document = {querySelectorAll: () => []};
const stats = async () => {};
(async () => {
  await navigate('agents');
  assert.equal(hash, '/#agents');
  assert.equal($('dashboard-link').href, '/dashboard?user=steve');
  assert.equal($('agents').hidden, false);
  assert.equal($('board').hidden, true);
  assert.deepEqual(calls, [['/agents'], ['/automation-mode']], 'Roster must only GET, with no paid start');
  const row = $('agent-rows').children[0];
  assert.equal(row.children[0].title, 'abc12345extra');
  assert.deepEqual(row.children.slice(1).map(cell => cell.textContent), ['Working?', '—', '—']);
  result = {available: true, items: [{id: 'def67890', role: 'worker', level: 3, state: 'active', resting: true, credits: null,
    admiration: null, growth: null, name: 'fe_study', session: 'it1', task: 'LOW · crawler', directive: 'Crawl forms', task_id: 'task-123456789'}]};
  await agentRoster();
  const work = $('agent-rows').children[0].children[2];
  assert.equal($('agent-rows').children[0].children[0].textContent, 'Astra fe_study');
  assert.equal(work.children[0].href, '#task=task-123456789');
  assert.deepEqual(work.children.slice(1).map(cell => cell.textContent), ['LOW · crawler', 'Crawl forms']);
  assert.equal($('agents-refresh').disabled, false);
  result = {available: false, items: []}; await agentRoster();
  assert.equal($('agents-summary').textContent, 'Agent registry unavailable.');
  assert.equal($('agent-rows').children.length, 0);
  result = {available: true, items: []}; await agentRoster();
  assert.equal($('agents-summary').textContent, 'No registered Astra runs yet.');
  await navigate('gremlins'); assert.equal($('agents').hidden, true);
  assert.equal(hash, '/');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    # Through stdin: app.js grew past the Windows command-line limit (WinError 206) when it was passed with -e.
    subprocess.run([node, '-'], input=functions + checks, check=True, capture_output=True, text=True, encoding='utf-8')
    assert 'data-view="agents"' in Path('app/static/index.html').read_text(encoding='utf-8')
    assert "location.hash === '#agents'" in source
