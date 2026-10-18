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
    assert "await api('/signoffs')" in script
    assert "await api('/signoffs/' + encodeURIComponent(item.id) + '/decision', {approved, note: note.value})" in script
    assert "'wallet', 'signoffs'" in (STATIC / 'workspace-navigation.js').read_text(encoding='utf-8')


def test_payload_is_inert_and_decisions_are_explicit():
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
