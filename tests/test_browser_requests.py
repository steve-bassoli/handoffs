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


def test_opportunity_links_accept_legacy_hashes_and_write_opp_hashes():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the pure JavaScript opportunity-link check')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const show = source.slice(source.indexOf('async function show(id) {'), source.indexOf("  for (const section of ['board'")) + '}';
const startup = source.slice(source.lastIndexOf('run(async () => {'));
(async () => {
  for (const [hash, id] of [
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
    assert.deepEqual(requests, id ? ['/users', '/bounties/' + encodeURIComponent(id)] : ['/users']);
    assert.equal(context.location.hash, id ? '#opp=' + encodeURIComponent(id) : '');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run([node, '-e', checks], check=True, capture_output=True, text=True)
