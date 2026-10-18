"""Small pure-JavaScript check; no browser automation or model/network calls."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_request_cache_does_not_store_multi_megabyte_upload_bodies():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the pure JavaScript request-cache check')
    source = Path('app/static/app.js').read_text(encoding='utf-8').split('async function stats()')[0]
    checks = '''
const assert = require('node:assert/strict');
const large = JSON.stringify(['steve', '/packages', {package_zip: 'x'.repeat(6000000)}]);
const key = requestCacheKey(large);
assert.ok(key.length < 100);
assert.equal(key, requestCacheKey(large));
assert.notEqual(key, requestCacheKey(large + 'changed'));
assert.notEqual(requestCacheKey('steve:/packages'), requestCacheKey('nate:/packages'));
'''
    subprocess.run([node, '-e', "const localStorage = {getItem: () => null};\n" + source + checks], check=True, capture_output=True, text=True)


def test_task_links_accept_legacy_hashes_and_write_task_hashes():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the pure JavaScript task-link check')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const show = source.slice(source.indexOf('async function show(id) {'), source.indexOf("  for (const section of ['board'")) + '}';
const startup = source.slice(source.lastIndexOf('run(async () => {'));
(async () => {
  for (const [hash, id] of [
    ['#task=current', 'current'],
    ['#task=current&opp=previous&bounty=old', 'current'],
    ['#opp=nates-offer', 'nates-offer'],
    ['#bounty=nates-offer', 'nates-offer'],
    ['#opp=new&bounty=old', 'new'],
    ['#opp=offer%2Fwith%20space', 'offer/with space'],
    ['', null],
  ]) {
    const requests = [];
    const context = {
      URLSearchParams, encodeURIComponent, user: 'nate', aiPoll: null, proofPoll: null,
      clearTimeout() {}, location: {hash},
      history: {replaceState(_state, _title, url) { context.location.hash = url; }},
      api: async path => { requests.push(path); return path === '/users' ? [{id: 'nate', name: 'Nate'}] : {}; },
      navigate: async () => { context.location.hash = ''; },
      $: () => ({append() {}}),
      element: () => ({cloneNode: () => ({})}),
      document: {querySelector: () => ({append() {}})},
      run: operation => { context.finished = operation(); },
    };
    vm.runInNewContext(show + '\n' + startup, context);
    await context.finished;
    assert.deepEqual(requests, id ? ['/users', '/tasks/' + encodeURIComponent(id)] : ['/users']);
    assert.equal(context.location.hash, id ? '#task=' + encodeURIComponent(id) : '');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run([node, '-e', checks], check=True, capture_output=True, text=True)


def test_model_picker_shows_only_simple_names_and_defaults_to_recommended():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the model-picker check')
    source = Path('app/static/app.js').read_text(encoding='utf-8')
    picker = source[source.index('function modelInput('):source.index('async function aiSection(')]
    checks = r'''
const assert = require('node:assert/strict');
const element = (tag, text) => ({tag, text, children: [], append(...nodes) { this.children.push(...nodes); }});
const settings = {models: [{value: 'sol', name: 'Sol'}, {value: 'terra', name: 'Terra'}, {value: 'luna', name: 'Luna'}], recommended: 'terra'};
for (const choice of [null, 'sol', 'luna']) {
  const form = element('form');
  const select = modelInput(form, {ai_options: settings, ai_run: {model_choice: choice}});
  assert.deepEqual(select.children.map(option => option.text), ['Sol', 'Terra', 'Luna']);
  assert.equal(select.value, choice || 'terra');
  assert.equal(form.children[0].text, 'Model');
  assert.equal(form.children[1].text, 'Recommended: Terra. Selection applies when you submit.');
  assert.equal(select.onchange, undefined, 'Selecting a model must not submit or spend');
}
'''
    subprocess.run([node, '-e', picker + checks],
                   check=True, capture_output=True, text=True)
