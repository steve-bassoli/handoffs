import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_decomposition_audit_view():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'app/static/decomposition-audit.js').read_text(encoding='utf-8')
    fixture = json.loads((root / 'tests/fixtures/decomposition_audit_v1.json').read_text(encoding='utf-8'))
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable: decomposition audit view coverage not executed')
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {source, fixture} = JSON.parse(fs.readFileSync(0, 'utf8'));
const caveat = 'Service.detail defaults missing complexity to HIGH.';
let sideEffects = 0;
const forbidden = () => { sideEffects++; throw Error('Forbidden side effect'); };
function element(tag) {
  return {tag, children: [], attrs: {}, listeners: {}, textContent: '',
    append(...nodes) { this.children.push(...nodes); },
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(key, callback) { this.listeners[key] = callback; },
    set innerHTML(value) { throw Error('HTML sink used'); }
  };
}
function nodes(root) { return [root, ...root.children.flatMap(nodes)]; }
function texts(root) { return nodes(root).map(n => n.textContent); }
function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze); Object.freeze(value);
  }
  return value;
}
const document = {createElement: element, body: {append: forbidden},
  querySelector: forbidden, write: forbidden};
const window = {};
const context = {window, document, fetch: forbidden, XMLHttpRequest: forbidden,
  WebSocket: forbidden, navigator: {sendBeacon: forbidden},
  localStorage: {setItem: forbidden}, sessionStorage: {setItem: forbidden},
  setTimeout: forbidden, setInterval: forbidden};
vm.runInNewContext(source, context);
assert.deepEqual(Object.keys(window), ['renderDecompositionAudit']);
assert.equal(sideEffects, 0);
const render = window.renderDecompositionAudit;
assert.equal(fixture.version, 1);
assert.equal(fixture.source, 'Service.hierarchy_violations');
assert.equal(fixture.status, 'findings');
assert.equal(fixture.error, null);
assert.ok(fixture.violations.length > 0);
assert.ok(fixture.limitations.includes(caveat));
freeze(fixture);
const before = JSON.stringify(fixture);
const calls = [];
const root = render({audit: fixture, onNavigate: id => calls.push(id)});
assert.equal(root.tag, 'section');
assert.equal(root.attrs['aria-label'], 'Decomposition audit');
assert.ok(texts(root).includes('Reported violations'));
assert.ok(texts(root).includes(caveat));
assert.ok(texts(root).includes(`Scope (display label only): ${fixture.scope}`));
assert.ok(texts(root).some(t => t.includes(fixture.checked_at)));
assert.ok(texts(root).some(t => t.includes(fixture.source)));
const buttons = nodes(root).filter(n => n.tag === 'button');
assert.deepEqual(buttons.map(n => n.textContent), fixture.violations.map(v => v.ticket_id));
assert.deepEqual(nodes(root).filter(n => n.tag === 'ol')[0].children.map(
  row => row.children[1].textContent), fixture.violations.map(v => v.message));
assert.ok(buttons.every(n => n.type === 'button'));
assert.deepEqual(calls, []);
buttons[0].listeners.click();
assert.deepEqual(calls, [fixture.violations[0].ticket_id]);
assert.equal(JSON.stringify(fixture), before);
assert.deepEqual(texts(render({audit: fixture})), texts(render({audit: fixture})));
const hostile = '<img src=x onerror=alert(1)>';
const hostileFeed = freeze({...fixture, scope: hostile,
  limitations: [...fixture.limitations, hostile],
  violations: [{ticket_id: 'Z', message: hostile}, {ticket_id: 'A', message: 'second'}]});
const hostileBefore = JSON.stringify(hostileFeed);
const hostileView = render({audit: hostileFeed, onNavigate: id => calls.push(id)});
assert.ok(texts(hostileView).includes(hostile));
assert.ok(texts(hostileView).includes(`Scope (display label only): ${hostile}`));
assert.ok(!nodes(hostileView).some(n => n.tag === 'img'));
assert.deepEqual(nodes(hostileView).filter(n => n.tag === 'button').map(n => n.textContent), ['Z', 'A']);
assert.equal(JSON.stringify(hostileFeed), hostileBefore);
const inert = render({audit: fixture});
assert.equal(nodes(inert).filter(n => n.tag === 'button').length, 0);
assert.ok(texts(inert).includes(fixture.violations[0].ticket_id));
const empty = {...fixture, status: 'checked_empty', violations: []};
assert.ok(texts(render({audit: empty})).includes('No violations reported'));
const unavailable = {...fixture, status: 'unavailable', violations: null,
  error: 'Audit unavailable'};
assert.ok(texts(render({audit: unavailable})).includes('Audit unavailable'));
const missingCaveat = fixture.limitations.filter(text => text !== caveat);
const malformed = [undefined, null, {}, {...fixture, version: 2},
  {...fixture, source: 'unexpected'}, {...fixture, checked_at: null},
  {...fixture, scope: null}, {...fixture, limitations: [42]},
  {...empty, limitations: missingCaveat},
  {...empty, limitations: [caveat.slice(0, -1)]},
  {...fixture, limitations: missingCaveat},
  {...fixture, violations: []}, {...empty, violations: fixture.violations},
  {...unavailable, violations: []}, {...unavailable, error: 'secret error'},
  {...fixture, error: 'secret error'}, {...fixture, violations: [{ticket_id: 7}]},
  {...fixture, violations: [{ticket_id: '', message: 'bad'}]}];
for (const audit of malformed) {
  const view = render({audit});
  assert.ok(texts(view).includes('Audit unavailable'));
  assert.ok(!texts(view).includes('No violations reported'));
  assert.ok(!texts(view).some(t => t.includes('secret error')));
  assert.equal(nodes(view).filter(n => n.tag === 'button').length, 0);
}
assert.ok(texts(render()).includes('Audit unavailable'));
assert.ok(texts(render(null)).includes('Audit unavailable'));
assert.ok(!texts(root).some(t => t.includes('Verified correct')));
assert.equal(sideEffects, 0);
'''
    result = subprocess.run(
        [node, '-e', script], input=json.dumps({'source': source, 'fixture': fixture}),
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
