import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.decomposition_teaching import build_teaching


ROOT = Path(__file__).resolve().parents[1]

# Shared by the cross-surface contract test; this is a small DOM model, not a browser.
DOM = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let sideEffects = 0;
const forbidden = () => { sideEffects++; throw Error('Forbidden side effect'); };
function element(tag) {
  const node = {tag, children: [], attrs: {}, listeners: {}, textContent: '', className: '',
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); return child; },
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(key, callback) { this.listeners[key] = callback; },
    get childElementCount() { return this.children.length; },
    set innerHTML(value) { throw Error('HTML sink used'); }
  };
  node.classList = {add(value) { node.className += ' ' + value; }};
  return node;
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
vm.runInNewContext(input.source, context);
assert.deepEqual(Object.keys(window).sort(), [
  'renderDecompositionFlow', 'renderDecompositionHierarchy', 'renderDecompositionVisibility']);
'''


def run_node(script, **payload):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable: decomposition visibility renderer coverage not executed')
    source = (ROOT / 'app/static/decomposition-visibility.js').read_text(encoding='utf-8')
    result = subprocess.run(
        [node, '-e', DOM + script],
        input=json.dumps({'source': source, **payload}),
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_decomposition_visibility_view():
    fixture = json.loads((ROOT / 'tests/fixtures/decomposition_visibility_v1.json').read_text(encoding='utf-8'))
    run_node(r'''
freeze(input.fixture);
freeze(input.teaching);
const before = JSON.stringify(input.fixture);
const teachingBefore = JSON.stringify(input.teaching);
const hostile = '<img src=x onerror=alert(1)>';
for (const render of [window.renderDecompositionHierarchy, window.renderDecompositionFlow]) {
  for (const sample of input.fixture.cases) {
    const calls = [];
    const host = element('div');
    host.className = 'original-host';
    const child = element('button');
    child.textContent = 'Original control';
    const originalListener = () => calls.push('original');
    child.addEventListener('click', originalListener);
    host.append(child);
    const root = render({hostNode: host, visibility: sample.expected,
      teaching: input.teaching, onNavigate: id => calls.push(id)});
    assert.equal(root.children[0], host);
    assert.equal(host.className, 'original-host');
    assert.deepEqual(host.children, [child]);
    assert.equal(child.listeners.click, originalListener);
    assert.ok(texts(root).includes(input.teaching.explanation));
    assert.ok(texts(root).includes('Source (supplied): ' + input.teaching.source));
    const panel = root.children[1];
    const buttons = nodes(panel).filter(n => n.tag === 'button');
    assert.deepEqual(buttons.map(n => n.textContent), sample.expected.tickets.map(r => r.id));
    assert.deepEqual(calls, []);
    // Native button semantics provide Enter/Space activation; do not double-fire
    // by synthesizing a second callback in a custom keydown handler.
    buttons.forEach(button => {
      assert.equal(button.type, 'button');
      assert.equal(button.attrs.tabindex, undefined);
      assert.equal(button.listeners.keydown, undefined);
      assert.ok(button.attrs['aria-label'].includes(button.textContent));
      button.listeners.click();
    });
    assert.deepEqual(calls, sample.expected.tickets.map(r => r.id));
    const inert = render({visibility: sample.expected});
    assert.equal(nodes(inert).filter(n => n.tag === 'button').length, 0);
    assert.ok(texts(inert).includes('Canonical rule help unavailable.'));
    assert.ok(!nodes(root).some(n => n.tag === 'img'));
  }
  const hostileProjection = {schema_version: 1, tickets: [{id: hostile,
    parent_id: null, child_ids: [], title: hostile, status: 'unknown',
    reasons: ['coverage_incomplete']}]};
  const calls = [];
  const view = render({visibility: hostileProjection,
    teaching: {...input.teaching, explanation: hostile}, onNavigate: id => calls.push(id)});
  assert.ok(texts(view).includes(hostile));
  nodes(view).find(n => n.tag === 'button').listeners.click();
  assert.deepEqual(calls, [hostile]);
  assert.ok(!nodes(view).some(n => n.tag === 'img'));
  for (const teaching of [null, {}, {...input.teaching, source: 'other'},
      {...input.teaching, version: 2}, {...input.teaching, rules: {HIGH: [7]}}]) {
    const root = render({visibility: hostileProjection, teaching});
    assert.ok(texts(root).includes('Canonical rule help unavailable.'));
    assert.ok(texts(root).includes('coverage_incomplete'));
  }
  for (const visibility of [null, {}, {schema_version: 2, tickets: []},
      {schema_version: 1, tickets: [hostileProjection.tickets[0], hostileProjection.tickets[0]]},
      {schema_version: 1, tickets: [{...hostileProjection.tickets[0], reasons: ['split_valid']}]},
      {schema_version: 1, tickets: [{...hostileProjection.tickets[0], status: '__proto__'}]}]) {
    const view = render({visibility});
    assert.ok(texts(view).includes('Decomposition visibility unavailable.'));
    assert.equal(nodes(view).filter(n => n.attrs['data-ticket-id']).length, 0);
  }
  assert.ok(texts(render(null)).includes('Decomposition visibility unavailable.'));
  assert.ok(texts(render()).includes('Decomposition visibility unavailable.'));
  assert.ok(texts(render({visibility: {schema_version: 1, tickets: []}})).includes('No tickets supplied.'));
}
assert.equal(JSON.stringify(input.fixture), before);
assert.equal(JSON.stringify(input.teaching), teachingBefore);
const fallback = window.renderDecompositionFlow({});
assert.equal(fallback.children[0].className, 'ticket-flow');
assert.ok(texts(fallback).includes('Task flow unavailable.'));
vm.runInNewContext(input.flow, context);
const originalFlow = window.renderTicketFlow;
const flowOptions = {currentId: 'A', lineage: {root_id: 'A', items: [
  {id: 'A', parent_id: null, title: hostile},
  {id: 'B', parent_id: 'A', title: 'Child'}]},
  detailsById: {A: {complexity: 'HIGH', events: [
    {kind: 'created', actor: 'NOT_AN_ASSIGNEE'},
    {kind: 'followup_confirmed', actor: 'ALSO_NOT_ASSIGNED', data: {}}]},
    B: {events: [{kind: 'followup_confirmed', actor: 'actor', data: {assigned_agent: 'Explicit'}}]}},
  visibility: input.fixture.cases[0].expected, teaching: input.teaching};
freeze(flowOptions);
const flowBefore = JSON.stringify(flowOptions);
const calls = [];
const view = window.renderDecompositionFlow({...flowOptions, onNavigate: id => calls.push(id)});
assert.equal(window.renderTicketFlow, originalFlow);
const host = view.children[0];
assert.equal(host.className, 'ticket-flow');
assert.equal(host.attrs['aria-label'], 'Task flow');
const cards = nodes(host).filter(n => n.className.split(' ').includes('flow-card'));
assert.equal(cards.length, 2);
assert.equal(cards[0].attrs['aria-current'], 'page');
assert.ok(texts(host).some(t => t.includes('Assigned: Unknown')));
assert.ok(texts(host).some(t => t.includes('Assigned: Explicit')));
assert.ok(!texts(host).some(t => t.includes('NOT_AN_ASSIGNEE') || t.includes('ALSO_NOT_ASSIGNED')));
cards[0].listeners.click();
assert.deepEqual(calls, ['A']);
assert.equal(JSON.stringify(flowOptions), flowBefore);
assert.equal(sideEffects, 0);
''', fixture=fixture, teaching=build_teaching(),
             flow=(ROOT / 'app/static/flow.js').read_text(encoding='utf-8'))
