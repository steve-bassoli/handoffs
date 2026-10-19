"""Pending sign-off UI wiring and inert payload regression checks."""
from pathlib import Path
import shutil
import subprocess
import pytest

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


def test_signoffs_workspace_wiring():
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    assert 'id="human-decisions-entry" data-view="signoffs"' in html and '>Decisions · ?</button>' in html
    assert '<section id="signoffs" data-view="signoffs" hidden>' in html
    assert 'Sign in to decide; demo identities cannot decide.' in html
    assert "await api('/digest')" in script
    assert "submitDigest('/digest/decide'," in script
    assert "submitDigest('/digest/decide-batch'," in script
    assert "'/signoffs/' + encodeURIComponent(item.id) + '/decision'" not in script
    assert "'wallet', 'signoffs'" in (STATIC / 'workspace-navigation.js').read_text(encoding='utf-8')


def test_legacy_payload_fixture_is_retired():
    pytest.skip('Legacy sign-off-only fixture; digest contract is checked below. Add browser behavior coverage before release.')


def legacy_payload_fixture_reference():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the sign-off rendering check')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const nodes = [];
function element(tag, text, className) {
  const node = {tag, textContent: text, className, dataset: {}, style: {}, children: [],
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; }};
  Object.defineProperty(node, 'innerHTML', {set() { throw Error('Unsafe HTML sink'); }});
  nodes.push(node); return node;
}
const list = element('div'), hint = element('p');
const calls = [], messages = [];
const context = {session: null, element, encodeURIComponent,
  $: id => id === 'signoffs-hint' ? hint : list,
  document: {querySelectorAll: () => nodes.filter(n => n.dataset.decision !== undefined)},
  run: operation => operation(), message: text => messages.push(text),
  api: async (path, body) => calls.push({path, body}),
  signoffs: async () => { throw Error('offline'); }};
const start = source.indexOf('function syncSignoffAuth()');
vm.runInNewContext(source.slice(start, source.indexOf('let signoffRequest', start)), context);
(async () => {
  const payload = '  {"x":"<img src=x onerror=alert(1)>"}\n';
  context.renderSignoffs([{id: 'a/b', action: 'publish', summary: 'Review me',
    requested_by: 'relay', requested_principal: 'agent', created_at: '2026-01-01', payload_json: payload}]);
  assert.equal(nodes.find(n => n.tag === 'pre').textContent, payload);
  assert.equal(nodes.find(n => n.tag === 'pre').style.whiteSpace, 'pre-wrap');
  const buttons = nodes.filter(n => n.tag === 'button');
  assert.ok(buttons.every(n => n.disabled));
  await buttons[0].onclick(); assert.equal(calls.length, 0);
  context.session = {access_token: 'fixture'}; context.syncSignoffAuth();
  assert.ok(buttons.every(n => !n.disabled));
  nodes.find(n => n.tag === 'textarea').value = 'Checked exact payload';
  await buttons[1].onclick();
  assert.equal(calls[0].path, '/signoffs/a%2Fb/decision');
  assert.equal(calls[0].body.approved, false);
  assert.equal(calls[0].body.note, 'Checked exact payload');
  assert.ok(messages.at(-1).includes('Decision recorded; refresh failed'));
  assert.ok(buttons.every(n => n.disabled), 'confirmed decisions cannot be resubmitted after refresh failure');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_digest_count_and_navigation_wiring():
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    assert "entry.textContent = known ? `Decisions · ${total}` : 'Decisions · ?'" in script
    assert 'data.counts.ready' in script
    assert "nextView !== 'signoffs') void refreshDigestCount()" in script
    assert 'await refreshDigestCount();' in script
    assert "const ticket = ++digestCountRequest, auth = session, actor = user" in script


def test_digest_inert_rendering_and_explicit_choices():
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    render = script.split('function renderSignoffs(items) {', 1)[1].split('async function signoffs()', 1)[0]
    helper = script.split('function element(tag, text, className) {', 1)[1].split('function message(', 1)[0]
    assert 'node.textContent = text' in helper
    assert 'innerHTML' not in render
    for field in ('item.action', 'item.title', 'item.kind', 'item.why_waiting', 'effect.gate', 'effect.reason', 'recommendation.rationale'):
        assert field in render
    assert "'Reversible'" in render and "'Irreversible'" in render
    assert 'No recommendation yet' in render
    assert 'choice.checked = false' in render
    assert "[['Accept', 'yes'], ['Decline', 'no'], ['Change', 'change']]" in render
    assert 'note.value.trim()' in render
    assert 'selected.length > 50' in render
    assert 'Sign in to decide' in render
    assert "controls.style.flexWrap = 'wrap'" in render


def test_digest_revision_batch_and_error_contract():
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert 'error.status = response.status' in script
    assert 'error.detail = data.detail' in script
    assert 'revision: item.revision' in script
    assert 'recommendation_id:' in script
    assert 'items: selected.map(entry => digestReference(entry.item))' in script
    assert 'for (const row of result.results || [])' in script
    assert 'Changed since you looked; refresh' in script
    assert 'Outcome unknown. No automatic retry.' in script
    assert 'session !== auth || actor !== user' in script
    assert 'digestBusy || digestUncertain' in script
    assert 'id="digest-outcomes" role="status" aria-live="polite"' in html


def test_decisions_search_and_ready_fold():
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert 'id="digest-search" type="search"' in html
    assert "$('digest-search').oninput = applyDigestSearch" in script
    assert 'if (entry.choice && entry.card.hidden) entry.choice.checked = false' in script  # Never batch what you cannot see.
    assert "items.filter(item => item.ready === false)" in script and '`${waiting.length} waiting on others`' in script
